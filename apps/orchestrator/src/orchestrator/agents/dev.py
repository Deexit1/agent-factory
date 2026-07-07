import time
from dataclasses import dataclass
from pathlib import Path

from schemas import FailureReport, TaskSpec

from orchestrator import git_ops
from orchestrator.agents.prompt import build_prompt
from orchestrator.api_client import ApiClient
from orchestrator.capability_registry import Profile
from orchestrator.claude_runner import DEFAULT_DEV_AGENT_PROMPT_PATH, ClaudeCodeRunner
from orchestrator.config import DevAgentConfig
from orchestrator.github_client import GitHubClient
from orchestrator.prompt_version import parse_prompt_version


@dataclass(frozen=True)
class DevAgentResult:
    run_id: int
    status: str  # "completed" | "budget_exceeded" | "timed_out" | "failed"
    pr_url: str | None
    cost_usd: float
    reason: str | None = None


def run_dev_agent(
    *,
    ticket_id: str,
    task_spec: TaskSpec,
    workspace_dir: Path,
    api: ApiClient,
    claude_runner: ClaudeCodeRunner,
    github: GitHubClient,
    config: DevAgentConfig,
    failure_report: FailureReport | None = None,
    attempt_no: int = 1,
    base_branch: str = "main",
    profile: Profile | None = None,
) -> DevAgentResult:
    model = config.model_for(task_spec.complexity, profile)
    prompt = build_prompt(task_spec, failure_report, attempt_no)
    actor = f"agent:dev-{ticket_id}"

    agent_role = profile.id if profile is not None else "dev"
    prompt_version = parse_prompt_version(
        DEFAULT_DEV_AGENT_PROMPT_PATH.read_text(encoding="utf-8")
    )
    run = api.create_agent_run(
        ticket_id, agent_role=agent_role, model=model, prompt_version=prompt_version
    )
    run_id = run["id"]

    budget_usd = task_spec.budget_usd
    cumulative_cost = 0.0
    tokens_in = 0
    tokens_out = 0
    status = "completed"
    reason: str | None = None
    deadline = time.monotonic() + config.timeout_s

    for event in claude_runner.run(
        prompt=prompt,
        cwd=workspace_dir,
        model=model,
        budget_usd=budget_usd,
        timeout_s=config.timeout_s,
    ):
        api.append_event(ticket_id, actor=actor, kind=event.kind, payload=event.payload)

        if event.kind == "cost":
            cumulative_cost = _as_number(event.payload.get("total_cost_usd"), cumulative_cost)
            tokens_in = int(_as_number(event.payload.get("tokens_in"), tokens_in))
            tokens_out = int(_as_number(event.payload.get("tokens_out"), tokens_out))

        if cumulative_cost > budget_usd:
            status = "budget_exceeded"
            reason = f"cumulative cost ${cumulative_cost:.4f} exceeded budget ${budget_usd:.4f}"
            break

        if time.monotonic() > deadline:
            status = "timed_out"
            reason = f"exceeded wall-clock timeout of {config.timeout_s:.0f}s"
            break

    if status == "completed" and not git_ops.has_uncommitted_changes(workspace_dir):
        status = "failed"
        reason = "agent produced no changes"

    api.complete_agent_run(
        ticket_id,
        run_id,
        status=status,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=cumulative_cost,
    )

    if status != "completed":
        api.transition(ticket_id, to_state="escalated")
        return DevAgentResult(
            run_id=run_id, status=status, pr_url=None, cost_usd=cumulative_cost, reason=reason
        )

    branch = f"agent/{ticket_id}"
    git_ops.commit_all(workspace_dir, message=f"{ticket_id}: {task_spec.title}")
    git_ops.push(workspace_dir, branch)
    pr = github.open_pr(
        branch=branch,
        base=base_branch,
        title=f"{ticket_id}: {task_spec.title}",
        body=_pr_body(task_spec),
    )

    # T-106: the dev agent's job ends at in_review — the Review agent
    # (agents/review.py) now actually holds the ticket there and decides
    # in_qa (approve) vs bounced (block); apps/api enforces that only a review
    # agent or human actor may move a ticket out of in_review.
    api.transition(ticket_id, to_state="in_review")
    return DevAgentResult(
        run_id=run_id, status="completed", pr_url=pr.url, cost_usd=cumulative_cost
    )


def _as_number(value: object, default: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return default


def _pr_body(task_spec: TaskSpec) -> str:
    checklist = "\n".join(
        f"- [ ] {c.description} (`{c.verification}`)" for c in task_spec.acceptance_criteria
    )
    return f"Closes {task_spec.id}.\n\n## Acceptance criteria\n{checklist}"
