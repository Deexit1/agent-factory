import json

import pytest

from orchestrator.agents import planner as planner_module
from orchestrator.agents.planner import run_planner_agent
from orchestrator.api_client import ApiClient

from .conftest import SERVICE_TOKEN

_AUTH_HEADERS = {"Authorization": f"Bearer {SERVICE_TOKEN}"}


class _FakeRouteResult:
    def __init__(self, text: str) -> None:
        self.text = text
        self.model = "claude-opus-4-8"
        self.provider = "anthropic"
        self.tokens_in = 500
        self.tokens_out = 300
        self.cost_usd = 0.03


def _create_idea(api: ApiClient, *, budget_usd: float = 100.0) -> dict[str, object]:
    idea = api.create_ticket(
        ticket_type="idea",
        title="Automate ticket triage",
        created_by="human:test",
        budget_usd=budget_usd,
    )
    api.transition(idea["id"], to_state="planning", actor="human:test")
    return idea


def test_seeded_idea_yields_a_valid_plan_with_epics_and_tasks(
    api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_json = json.dumps(
        {
            "epics": [
                {"id": "epic-1", "title": "Foundations", "description": "d", "budget_usd": 60.0}
            ],
            "tasks": [
                {
                    "id": "task-1",
                    "title": "Add triage endpoint",
                    "context": "ctx",
                    "acceptance_criteria": [
                        {"id": "AC-1", "description": "d", "verification": "v"}
                    ],
                    "complexity": "low",
                    "budget_usd": 20.0,
                    "depends_on": [],
                    "estimate_days": 0.5,
                    "epic_id": "epic-1",
                }
            ],
        }
    )
    monkeypatch.setattr(planner_module, "route", lambda *a, **k: _FakeRouteResult(plan_json))

    idea = _create_idea(api)
    result = run_planner_agent(
        ticket_id=idea["id"],
        idea_title=idea["title"],
        idea_description="",
        idea_budget_usd=100.0,
        api=api,
    )

    assert result.status == "planned"
    assert result.plan is not None
    assert result.cost_usd == 0.03

    descendants = api.descendants(idea["id"])
    epics = [d for d in descendants if d["type"] == "epic"]
    tasks = [d for d in descendants if d["type"] == "task"]
    assert len(epics) == 1
    assert len(tasks) == 1
    assert tasks[0]["parent_id"] == epics[0]["id"]
    assert tasks[0]["spec"]["depends_on"] == []
    assert epics[0]["state"] == "planning"
    assert tasks[0]["state"] == "planning"

    summary = api.cost_summary(idea["id"])
    assert summary["agent_runs_total_usd"] == 0.03


def test_under_specified_idea_yields_questions_and_escalates(
    api: ApiClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    questions_json = json.dumps({"questions": ["Who is the target user for this idea?"]})
    monkeypatch.setattr(planner_module, "route", lambda *a, **k: _FakeRouteResult(questions_json))

    idea = _create_idea(api)
    result = run_planner_agent(
        ticket_id=idea["id"],
        idea_title=idea["title"],
        idea_description="",
        idea_budget_usd=100.0,
        api=api,
    )

    assert result.status == "questions"
    assert result.questions == ["Who is the target user for this idea?"]

    ticket_after = api.get_ticket(idea["id"])
    assert ticket_after["state"] == "escalated"
