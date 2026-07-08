#!/usr/bin/env python3
"""T-009 pilot runner. NOT part of the product — a one-off ops script that drives real
tickets through the real loop: create ticket -> real Claude Code dev agent -> real PR
(`gh pr create`) -> real CI on GitHub Actions -> relay the result to the local webhook
(since GitHub Actions can't reach this machine's apps/api) -> ticket lands in done/
escalated/bounced. See tasks/CHANGELOG.md's T-009 entry for exactly what's real here vs.
simplified for the pilot, and the plan at the top of this file's sibling docs for context.

Usage:
    python scripts/run_pilot.py --tickets PILOT-01          # one ticket, by index or id
    python scripts/run_pilot.py --all                       # every ticket in pilot_tickets.py
    python scripts/run_pilot.py --all --start-at 3          # resume from the 3rd ticket

Known limitation: if a ticket bounces (CI fails), this script does NOT attempt an
automated retry — run_dev_agent unconditionally calls github.open_pr() on a successful
run, which would fail on a second attempt against a branch that already has an open PR.
Bounced tickets are reported and left for manual follow-up rather than guessed at.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import httpx  # noqa: E402
from pilot_tickets import PILOT_TICKETS  # noqa: E402

from orchestrator.agents.dev import run_dev_agent  # noqa: E402
from orchestrator.api_client import ApiClient  # noqa: E402
from orchestrator.claude_runner import ClaudeCodeRunner, SubprocessClaudeCodeRunner  # noqa: E402
from orchestrator.config import DevAgentConfig  # noqa: E402
from orchestrator.github_client import GhCliGitHubClient  # noqa: E402
from orchestrator.sandbox_runner import SandboxClaudeCodeRunner  # noqa: E402

API_URL = "http://localhost:8000"
REPO_URL = "git@github.com:Deexit1/agent-factory.git"
DEV_AGENT_TIMEOUT_S = 15 * 60
CI_POLL_INTERVAL_S = 20
CI_POLL_TIMEOUT_S = 30 * 60
WORKFLOW_NAME = "Agent PR Gate"


@dataclass
class PilotOutcome:
    task_spec_id: str
    real_ticket_id: str
    final_state: str
    pr_url: str | None = None
    cost_usd: float = 0.0
    note: str | None = None


def _service_token() -> str:
    import os

    token = os.environ.get("AGENT_FACTORY_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("AGENT_FACTORY_SERVICE_TOKEN must be set (source .env first)")
    return token


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_service_token()}"}


def create_ticket(title: str, budget_usd: float, acceptance_criteria: list[dict[str, str]]) -> str:
    response = httpx.post(
        f"{API_URL}/tickets",
        headers=_headers(),
        json={
            "type": "task",
            "title": title,
            "created_by": "system:pilot-runner",
            "budget_usd": budget_usd,
            "acceptance_criteria": acceptance_criteria,
        },
        timeout=10.0,
    )
    response.raise_for_status()
    return response.json()["id"]


def transition(ticket_id: str, to_state: str) -> None:
    response = httpx.post(
        f"{API_URL}/tickets/{ticket_id}/transition",
        headers=_headers(),
        json={"to_state": to_state, "actor": "system:pilot-runner"},
        timeout=10.0,
    )
    response.raise_for_status()


def get_ticket(ticket_id: str) -> dict[str, object]:
    response = httpx.get(f"{API_URL}/tickets/{ticket_id}", headers=_headers(), timeout=10.0)
    response.raise_for_status()
    return response.json()


def fresh_clone(tmp_root: Path, ticket_id: str) -> Path:
    dest = tmp_root / ticket_id
    subprocess.run(
        ["git", "clone", REPO_URL, str(dest)], check=True, capture_output=True, text=True
    )
    return dest


def pr_number_from_url(url: str) -> int:
    return int(url.rstrip("/").rsplit("/", 1)[-1])


def run_one_ticket(task_spec, tmp_root: Path, claude_runner: ClaudeCodeRunner) -> PilotOutcome:
    print(f"\n=== {task_spec.id}: {task_spec.title} ===")

    real_ticket_id = create_ticket(
        task_spec.title,
        task_spec.budget_usd,
        [ac.model_dump() for ac in task_spec.acceptance_criteria],
    )
    print(f"  created {real_ticket_id}")
    transition(real_ticket_id, "in_progress")

    workspace = fresh_clone(tmp_root, real_ticket_id)
    api = ApiClient(API_URL, actor=f"system:pilot-{real_ticket_id}", service_token=_service_token())
    config = DevAgentConfig(api_url=API_URL, timeout_s=DEV_AGENT_TIMEOUT_S)

    result = run_dev_agent(
        ticket_id=real_ticket_id,
        task_spec=task_spec.model_copy(update={"id": real_ticket_id}),
        workspace_dir=workspace,
        api=api,
        claude_runner=claude_runner,
        github=GhCliGitHubClient(),
        config=config,
    )
    api.close()
    shutil.rmtree(workspace, ignore_errors=True)

    print(f"  dev agent status={result.status} cost=${result.cost_usd:.4f}")

    if result.status != "completed":
        ticket = get_ticket(real_ticket_id)
        return PilotOutcome(
            task_spec.id,
            real_ticket_id,
            ticket["state"],
            cost_usd=result.cost_usd,
            note=result.reason,
        )

    assert result.pr_url is not None
    return PilotOutcome(
        task_spec.id, real_ticket_id, "in_qa", pr_url=result.pr_url, cost_usd=result.cost_usd
    )


def poll_ci(outcome: PilotOutcome) -> None:
    """Blocks until the Agent PR Gate run for this ticket's PR concludes, then relays the
    real result to the local webhook — standing in for GitHub POSTing to a public URL."""
    if outcome.pr_url is None:
        return

    branch = f"agent/{outcome.real_ticket_id}"
    print(f"  polling CI for {outcome.pr_url} (branch {branch})...")

    deadline = time.monotonic() + CI_POLL_TIMEOUT_S
    run: dict[str, object] | None = None
    while time.monotonic() < deadline:
        result = subprocess.run(
            [
                "gh", "run", "list",
                "--repo", "Deexit1/agent-factory",
                "--workflow", WORKFLOW_NAME,
                "--branch", branch,
                "--limit", "1",
                "--json", "databaseId,status,conclusion",
            ],
            capture_output=True, text=True,
        )
        runs = json.loads(result.stdout or "[]")
        if runs and runs[0]["status"] == "completed":
            run = runs[0]
            break
        time.sleep(CI_POLL_INTERVAL_S)

    if run is None:
        outcome.note = "CI did not conclude within the poll timeout"
        print(f"  {outcome.note}")
        return

    conclusion = "success" if run["conclusion"] == "success" else "failure"
    raw_log = ""
    if conclusion == "failure":
        log_result = subprocess.run(
            [
                "gh", "run", "view", str(run["databaseId"]),
                "--repo", "Deexit1/agent-factory", "--log-failed",
            ],
            capture_output=True, text=True,
        )
        raw_log = log_result.stdout[-20000:]  # webhook payload doesn't need the whole thing

    webhook_response = httpx.post(
        f"{API_URL}/webhooks/ci-result",
        json={
            "ticket_id": outcome.real_ticket_id,
            "conclusion": conclusion,
            "suite": "agent-pr-gate",
            "raw_log": raw_log,
        },
        timeout=30.0,
    )
    webhook_response.raise_for_status()
    outcome.final_state = webhook_response.json()["state"]
    print(f"  CI concluded {conclusion} -> ticket is now {outcome.final_state}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickets", nargs="*", help="TaskSpec ids to run, e.g. PILOT-01")
    parser.add_argument("--all", action="store_true", help="run every ticket in pilot_tickets.py")
    parser.add_argument(
        "--start-at", type=int, default=0, help="skip the first N tickets with --all"
    )
    parser.add_argument(
        "--sandbox",
        action="store_true",
        help=(
            "T-204: run the dev agent inside an isolated apps/sandbox Docker container "
            "instead of as a bare host subprocess (default). Requires Docker."
        ),
    )
    args = parser.parse_args()

    if args.all:
        specs = PILOT_TICKETS[args.start_at :]
    elif args.tickets:
        specs = [t for t in PILOT_TICKETS if t.id in args.tickets]
    else:
        parser.error("pass --tickets ID [ID ...] or --all")
        return

    # T-204: one shared runner across every ticket in this run — SandboxClaudeCodeRunner
    # owns a pre-warmed pool whose value only shows up when it's reused across tickets,
    # not reconstructed fresh per ticket.
    claude_runner: ClaudeCodeRunner = (
        SandboxClaudeCodeRunner(
            api=ApiClient(API_URL, actor="system:pilot-sandbox", service_token=_service_token())
        )
        if args.sandbox
        else SubprocessClaudeCodeRunner()
    )

    with tempfile.TemporaryDirectory(prefix="pilot-") as tmp:
        tmp_root = Path(tmp)
        outcomes: list[PilotOutcome] = []
        for spec in specs:
            outcome = run_one_ticket(spec, tmp_root, claude_runner)
            outcomes.append(outcome)
            if outcome.pr_url is not None:
                poll_ci(outcome)

    print("\n=== summary ===")
    for o in outcomes:
        line = f"{o.task_spec_id} ({o.real_ticket_id}): {o.final_state} cost=${o.cost_usd:.4f}"
        if o.pr_url:
            line += f" pr={o.pr_url}"
        if o.note:
            line += f" note={o.note}"
        print(line)


if __name__ == "__main__":
    main()
