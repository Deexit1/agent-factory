"""T-104 / SPEC-103: the Delivery Manager agent — batch LLM assignment proposals,
enforced end-to-end against a real apps/api (deps-done, budget, profile capacity).

T-105 / SPEC-104 adds real profiles to capability_registry.yaml (dev-generalist,
dev-frontend, dev-backend, dev-devops), so an untagged task (required_skills=[])
now matches ALL FOUR profiles by skill, not just dev-generalist — every
`considered` assertion below reflects that real, larger eligible set."""

import json
import re
import urllib.request

import pytest
from schemas import DEFAULT_REPO

from orchestrator.agents import delivery_manager as delivery_manager_module
from orchestrator.agents.delivery_manager import run_delivery_manager_agent
from orchestrator.api_client import ApiClient

from .conftest import SERVICE_TOKEN

_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}
_ALL_PROFILES = ["dev-backend", "dev-devops", "dev-frontend", "dev-generalist"]


class _FakeRouteResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model = "claude-sonnet-5"
        self.provider = "anthropic"
        self.tokens_in = 200
        self.tokens_out = 100
        self.cost_usd = 0.0015


def _assign_all_to(profile: str):
    """A fake `route()` that reads the task ids the DM actually put in its user
    message and proposes assigning every one of them to `profile` — so the test
    doesn't need to guess server-generated ticket ids up front."""

    def _route(
        role: str,
        *,
        credentials: object,
        system: str,
        messages: list[dict[str, str]],
        max_tokens: int,
    ):
        user_message = messages[0]["content"]
        task_ids = re.findall(r"- id: (\S+)", user_message)
        assignments = [
            {"task_id": tid, "profile": profile, "reason": "fits the queue", "alternatives": []}
            for tid in task_ids
        ]
        return _FakeRouteResult(json.dumps({"assignments": assignments, "deferred": []}))

    return _route


def _dev_login(running_api: str, email: str, role: str) -> str:
    request = urllib.request.Request(
        f"{running_api}/auth/dev-login",
        method="POST",
        headers={"Content-Type": "application/json"},
        data=json.dumps({"email": email, "role": role}).encode(),
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())["token"]  # type: ignore[no-any-return]


def _approve_budget(running_api: str, ticket_id: str, token: str) -> None:
    request = urllib.request.Request(
        f"{running_api}/tickets/{ticket_id}/approve",
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
        data=json.dumps({"gate": "budget", "decision": "approved"}).encode(),
    )
    urllib.request.urlopen(request)


def _get_events(running_api: str, ticket_id: str) -> list[dict[str, object]]:
    request = urllib.request.Request(
        f"{running_api}/tickets/{ticket_id}/events?limit=100", headers=_AUTH_HEADERS
    )
    with urllib.request.urlopen(request) as response:
        body: dict[str, object] = json.loads(response.read())
        items = body["items"]
        assert isinstance(items, list)
        return items


def _finish_task(api: ApiClient, ticket_id: str) -> None:
    """Drives an in_progress ticket to done, freeing whatever profile/repo capacity
    it held — the registry's dev-generalist max_parallel is a real, shared, session-
    wide resource (tests run against one long-lived Postgres), so tests that
    deliberately fill capacity must release it or later tests in this file would
    see stale utilisation. T-106: in_review -> in_qa now requires a review-agent or
    human actor, not just anyone. T-107: CI-green only enqueues a merge-queue slot
    now — done requires actually resolving it, standing in for a real merge_queue.py
    run since these tests don't need real git/gh mechanics, just the end state."""
    api.transition(ticket_id, to_state="in_review")
    api.transition(ticket_id, to_state="in_qa", actor="agent:review-1")
    api.report_ci_result(ticket_id, conclusion="success")
    entries = api.list_merge_queue_entries(repo=DEFAULT_REPO)
    entry = next(e for e in entries if e["ticket_id"] == ticket_id)
    api.resolve_merge_success(entry["id"], actor="system:merge-queue")


def _ready_task(
    api: ApiClient,
    running_api: str,
    *,
    task_id: str,
    depends_on: list[str] | None = None,
    budget_usd: float = 20.0,
    required_skills: list[str] | None = None,
) -> dict[str, object]:
    """Drives a fresh idea -> planning -> approved -> ready task all the way to
    `ready`, mirroring apps/api's own test_delivery_manager_gates.py::_ready_task."""
    idea = api.create_ticket(
        ticket_type="idea", title="Automate triage", created_by="human:test", budget_usd=100.0
    )
    api.transition(idea["id"], to_state="planning", actor="human:test")
    epic = api.create_ticket(
        ticket_type="epic",
        title="Epic",
        created_by="agent:planner-1",
        parent_id=idea["id"],
        budget_usd=90.0,
    )
    task = api.create_ticket(
        ticket_type="task",
        title=f"Task {task_id}",
        created_by="agent:planner-1",
        parent_id=epic["id"],
        budget_usd=budget_usd,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        spec={
            "id": task_id,
            "depends_on": depends_on or [],
            "required_skills": required_skills or [],
        },
    )
    token = _dev_login(running_api, f"approver-{task_id}@example.com", "approver")
    _approve_budget(running_api, idea["id"], token)
    api.transition(idea["id"], to_state="ready", actor="human:test")
    return task


def test_dependent_task_is_refused_by_the_api_and_recorded_not_crashed(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: `ready` does not mean unblocked — the DM may propose assigning a task
    whose dependency isn't done; the API refuses it and the DM records the refusal
    instead of crashing."""
    idea = api.create_ticket(
        ticket_type="idea", title="Idea", created_by="human:test", budget_usd=100.0
    )
    api.transition(idea["id"], to_state="planning", actor="human:test")
    epic = api.create_ticket(
        ticket_type="epic",
        title="Epic",
        created_by="agent:planner-1",
        parent_id=idea["id"],
        budget_usd=90.0,
    )
    task_a = api.create_ticket(
        ticket_type="task",
        title="Task A",
        created_by="agent:planner-1",
        parent_id=epic["id"],
        budget_usd=20.0,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        spec={"id": "task-a", "depends_on": []},
    )
    task_b = api.create_ticket(
        ticket_type="task",
        title="Task B",
        created_by="agent:planner-1",
        parent_id=epic["id"],
        budget_usd=20.0,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        spec={"id": "task-b", "depends_on": ["task-a"]},
    )
    token = _dev_login(running_api, "approver-chain@example.com", "approver")
    _approve_budget(running_api, idea["id"], token)
    api.transition(idea["id"], to_state="ready", actor="human:test")

    monkeypatch.setattr(
        delivery_manager_module, "route", _assign_all_to("dev-generalist")
    )

    result = run_delivery_manager_agent(api=api)
    outcomes = {o.ticket_id: o for o in result.outcomes}

    assert outcomes[task_a["id"]].decision == "assigned"
    assert outcomes[task_b["id"]].decision == "refused"
    assert "dependencies are not done" in outcomes[task_b["id"]].reason

    ticket_b_after = api.get_ticket(task_b["id"])
    assert ticket_b_after["state"] == "ready"

    events = _get_events(running_api, task_b["id"])
    assignment_events = [e for e in events if e["kind"] == "assignment"]
    assert len(assignment_events) == 1
    assert assignment_events[0]["payload"]["decision"] == "refused"
    assert assignment_events[0]["payload"]["considered"] == _ALL_PROFILES

    # Finish A, freeing its capacity slot, and prove the gate lifts once the
    # dependency is actually done — also leaves no in_progress/ready residue behind
    # for later tests in this file, which share one session-wide Postgres.
    _finish_task(api, task_a["id"])
    result_after_dep_done = run_delivery_manager_agent(api=api)
    outcome_b_after = next(
        o for o in result_after_dep_done.outcomes if o.ticket_id == task_b["id"]
    )
    assert outcome_b_after.decision == "assigned"
    _finish_task(api, task_b["id"])


def test_task_deferred_to_human_when_profile_already_at_capacity(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC2: with dev-frontend already at its registry max_parallel (2), a third
    frontend-tagged task has no eligible profile at all (dev-generalist etc. don't
    have the "frontend" skill, so they were never candidates) — the DM must never
    even call the LLM for it, and must leave it `ready` with a human_only decision
    recorded, distinct from a skill-mismatch human_only."""

    def _fail_if_called(role: str, *, system: str, messages: list[dict[str, str]], max_tokens: int):
        raise AssertionError("route() should not be called when no profile is eligible")

    occupant_1 = _ready_task(
        api, running_api, task_id="occupant-1", required_skills=["frontend"]
    )
    occupant_2 = _ready_task(
        api, running_api, task_id="occupant-2", required_skills=["frontend"]
    )
    api.transition(occupant_1["id"], to_state="in_progress", assignee_agent="dev-frontend")
    api.transition(occupant_2["id"], to_state="in_progress", assignee_agent="dev-frontend")

    waiting = _ready_task(api, running_api, task_id="waiting", required_skills=["frontend"])
    monkeypatch.setattr(delivery_manager_module, "route", _fail_if_called)

    result = run_delivery_manager_agent(api=api)

    outcome = next(o for o in result.outcomes if o.ticket_id == waiting["id"])
    assert outcome.decision == "human_only"
    assert outcome.profile is None

    ticket_after = api.get_ticket(waiting["id"])
    assert ticket_after["state"] == "ready"

    events = _get_events(running_api, waiting["id"])
    assignment_events = [e for e in events if e["kind"] == "assignment"]
    assert len(assignment_events) == 1
    assert assignment_events[0]["payload"]["decision"] == "human_only"
    assert assignment_events[0]["payload"]["reason"] == "no eligible profile has free capacity"
    assert assignment_events[0]["payload"]["considered"] == []

    # Free both occupants' capacity and prove `waiting` eventually gets assigned —
    # also leaves no in_progress residue for later tests in this shared-Postgres file.
    _finish_task(api, occupant_1["id"])
    _finish_task(api, occupant_2["id"])
    monkeypatch.setattr(delivery_manager_module, "route", _assign_all_to("dev-frontend"))
    result_after_capacity_freed = run_delivery_manager_agent(api=api)
    outcome_after = next(
        o for o in result_after_capacity_freed.outcomes if o.ticket_id == waiting["id"]
    )
    assert outcome_after.decision == "assigned"
    _finish_task(api, waiting["id"])


def test_frontend_tagged_task_is_never_proposed_to_a_non_matching_profile(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC1: a task tagged required_skills=["frontend"] is only ever eligible for
    dev-frontend — never dev-backend/dev-devops/dev-generalist — even when those
    other profiles have free capacity. `dev-backend` has plenty of free capacity
    here, so if skill-matching were left to the LLM alone (as it was pre-T-105),
    a misbehaving/hallucinating response proposing dev-backend would sail straight
    through the API (skill-match has no apps/api hard gate — see the module
    docstring). The DM itself must reject an out-of-eligible-set proposal before
    ever calling transition() with it."""
    task = _ready_task(api, running_api, task_id="fe-task", required_skills=["frontend"])
    monkeypatch.setattr(delivery_manager_module, "route", _assign_all_to("dev-backend"))

    result = run_delivery_manager_agent(api=api)

    outcome = next(o for o in result.outcomes if o.ticket_id == task["id"])
    assert outcome.decision == "refused"
    assert "was not in the eligible set" in outcome.reason

    ticket_after = api.get_ticket(task["id"])
    assert ticket_after["state"] == "ready"
    assert ticket_after["assignee_agent"] is None

    # Leaves no ready residue behind — a still-ready task would resurface in every
    # later test in this shared-Postgres file's system-wide ready-task query.
    monkeypatch.setattr(delivery_manager_module, "route", _assign_all_to("dev-frontend"))
    result_after = run_delivery_manager_agent(api=api)
    outcome_after = next(o for o in result_after.outcomes if o.ticket_id == task["id"])
    assert outcome_after.decision == "assigned"
    _finish_task(api, task["id"])


def test_skill_mismatched_task_is_human_only_without_calling_the_llm(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A task tagged with a skill no profile has (e.g. "mobile") is left `ready`
    with a human_only decision and a reason distinct from the capacity-exhaustion
    case — and never even reaches the LLM call, since the skill filter runs before
    the batch prompt is built."""

    def _fail_if_called(role: str, *, system: str, messages: list[dict[str, str]], max_tokens: int):
        raise AssertionError("route() should not be called when no profile has the skill")

    task = _ready_task(api, running_api, task_id="mobile-task", required_skills=["mobile"])
    monkeypatch.setattr(delivery_manager_module, "route", _fail_if_called)

    result = run_delivery_manager_agent(api=api)

    outcome = next(o for o in result.outcomes if o.ticket_id == task["id"])
    assert outcome.decision == "human_only"
    assert outcome.profile is None
    assert outcome.reason == "no profile has the required skills"

    ticket_after = api.get_ticket(task["id"])
    assert ticket_after["state"] == "ready"

    events = _get_events(running_api, task["id"])
    assignment_events = [e for e in events if e["kind"] == "assignment"]
    assert len(assignment_events) == 1
    assert assignment_events[0]["payload"]["reason"] == "no profile has the required skills"
    assert assignment_events[0]["payload"]["considered"] == []


def test_reassignment_over_budget_is_refused_not_crashed(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC4: even though this task's only eligible profile is proposed again by the
    LLM, the API refuses reassignment once the task's own spend already met its
    budget — the DM must record the refusal, not crash or silently retry."""
    task = _ready_task(api, running_api, task_id="spent", budget_usd=10.0)
    api.transition(task["id"], to_state="in_progress", assignee_agent="dev-generalist")

    run = api.create_agent_run(task["id"], agent_role="dev", model="sonnet")
    api.complete_agent_run(
        task["id"], run["id"], status="completed", tokens_in=0, tokens_out=0, cost_usd=10.0
    )
    api.transition(task["id"], to_state="escalated", actor="human:test")
    api.transition(task["id"], to_state="ready", actor="human:test")

    monkeypatch.setattr(delivery_manager_module, "route", _assign_all_to("dev-generalist"))

    result = run_delivery_manager_agent(api=api)

    outcome = next(o for o in result.outcomes if o.ticket_id == task["id"])
    assert outcome.decision == "refused"
    assert "already spent its budget" in outcome.reason

    ticket_after = api.get_ticket(task["id"])
    assert ticket_after["state"] == "ready"


def test_successful_assignment_event_always_records_reason_and_considered(
    api: ApiClient, running_api: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC3: every assignment decision — including a clean success — is recorded as
    an event carrying both the model's reason and the profiles considered."""
    task = _ready_task(api, running_api, task_id="solo")
    monkeypatch.setattr(delivery_manager_module, "route", _assign_all_to("dev-generalist"))

    result = run_delivery_manager_agent(api=api)

    outcome = next(o for o in result.outcomes if o.ticket_id == task["id"])
    assert outcome.decision == "assigned"
    assert outcome.profile == "dev-generalist"

    ticket_after = api.get_ticket(task["id"])
    assert ticket_after["state"] == "in_progress"
    assert ticket_after["assignee_agent"] == "dev-generalist"

    events = _get_events(running_api, task["id"])
    assignment_events = [e for e in events if e["kind"] == "assignment"]
    assert len(assignment_events) == 1
    payload = assignment_events[0]["payload"]
    assert payload["decision"] == "assigned"
    assert payload["reason"]
    assert payload["considered"] == _ALL_PROFILES

    # Cost is attributed to whichever ready task the batch call considered first
    # (a disclosed simplification — agent_runs has no "not tied to one ticket"
    # concept), not necessarily this ticket, so assert on the batch result itself
    # rather than this ticket's own cost-summary.
    assert result.cost_usd == 0.0015

    _finish_task(api, task["id"])
