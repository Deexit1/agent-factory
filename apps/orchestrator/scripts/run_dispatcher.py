#!/usr/bin/env python3
"""T-211: ops script that drives agent dispatch across EVERY org, not just the single
seeded default org run_pilot.py is hardwired to. NOT part of the product — a manually
invoked loop, matching run_pilot.py's own "one-off ops script" framing, not a daemon.

Mechanically, this is what makes cross-org dispatch possible at all: it calls
GET /admin/dispatch/ready-tickets (service-principal-only, deliberately not scoped to
any one org) to discover which (ticket_id, org_id) pairs need an agent run, then
constructs a fresh org-scoped ApiClient (Authorization: service token + X-Org-Id: that
org) per ticket before calling into the same run_planner_agent/run_delivery_manager_agent
every existing agent integration test already exercises against the default org — those
functions needed zero changes, since org-locking only ever lived in how apps/api resolved
the caller's ActorContext.org_id (api.auth.get_actor_context), not in the agents
themselves or in get_runtime_keys/resolve_dispatch (already correctly multi-org, proven
by test_byok_attribution.py's own cross-org test).

Scope, disclosed: covers the Planner and Delivery Manager stages only — both are
git-workspace-free (they read/write ticket state via the API, no repo clone needed).
The dev-agent and review-agent stages additionally need a real per-ticket git clone and
a GitHub App installation token (run_pilot.py's fresh_clone/GhCliGitHubClient), which is
real, already-built machinery for a SINGLE known ticket/repo — assembling it into a
generic "loop over every org's ready tasks" dispatcher is a separate integration task,
not an auth/dispatch-lock problem. The lock itself (the actual three-times-disclosed
gap) is fully closed by this script's existence: nothing about wiring dev/review in
later needs any further apps/api change.

Usage:
    python scripts/run_dispatcher.py            # one pass over every org's ready work
    python scripts/run_dispatcher.py --loop 30   # repeat every 30s until Ctrl-C
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orchestrator.agents.delivery_manager import run_delivery_manager_agent  # noqa: E402
from orchestrator.agents.planner import run_planner_agent  # noqa: E402
from orchestrator.api_client import ApiClient  # noqa: E402

API_URL = os.environ.get("AGENT_FACTORY_API_URL", "http://localhost:8000")


def _service_token() -> str:
    token = os.environ.get("AGENT_FACTORY_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("AGENT_FACTORY_SERVICE_TOKEN must be set (source .env first)")
    return token


def dispatch_once() -> None:
    discovery = ApiClient(API_URL, actor="system:dispatcher", service_token=_service_token())
    try:
        ready = discovery.list_dispatchable_tickets()
    finally:
        discovery.close()

    ideas = [t for t in ready if t["type"] == "idea"]
    orgs_with_ready_tasks = {t["org_id"] for t in ready if t["type"] == "task"}

    for idea in ideas:
        org_id = idea["org_id"]
        api = ApiClient(
            API_URL,
            actor=f"system:dispatcher-{idea['id']}",
            service_token=_service_token(),
            org_id=org_id,
        )
        try:
            ticket = api.get_ticket(idea["id"])
            print(f"[planner] org={org_id} ticket={idea['id']} {ticket['title']!r}")
            result = run_planner_agent(
                ticket_id=idea["id"],
                idea_title=ticket["title"],
                idea_description=(ticket.get("spec") or {}).get("description", ""),
                idea_budget_usd=ticket["budget_usd"],
                api=api,
            )
            print(f"  -> {result.status}")
        finally:
            api.close()

    for org_id in orgs_with_ready_tasks:
        api = ApiClient(
            API_URL, actor="system:dispatcher-dm", service_token=_service_token(), org_id=org_id
        )
        try:
            print(f"[delivery-manager] org={org_id}")
            result = run_delivery_manager_agent(api=api)
            for outcome in result.outcomes:
                print(f"  {outcome.ticket_id} -> {outcome.decision} ({outcome.reason})")
        finally:
            api.close()

    if not ideas and not orgs_with_ready_tasks:
        print("nothing to dispatch")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--loop", type=int, metavar="SECONDS", help="repeat every N seconds until Ctrl-C"
    )
    args = parser.parse_args()

    if args.loop is None:
        dispatch_once()
        return

    while True:
        dispatch_once()
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
