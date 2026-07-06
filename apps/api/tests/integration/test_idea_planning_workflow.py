"""T-103 / SPEC-102: idea -> planning -> epics/tasks -> ready workflow, and the
questions -> escalated -> planning round trip."""

from typing import Any

from fastapi.testclient import TestClient

from .test_tickets_api import _dev_login, _transition


def _create_idea(client: TestClient, *, budget_usd: float | None = 100.0) -> dict[str, Any]:
    payload = {
        "type": "idea",
        "title": "Automate ticket triage",
        "created_by": "human:alice",
        "budget_usd": budget_usd,
    }
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _create_epic(client: TestClient, *, parent_id: str, budget_usd: float = 60.0) -> dict[str, Any]:
    payload = {
        "type": "epic",
        "title": "Epic 1",
        "parent_id": parent_id,
        "created_by": "agent:planner-1",
        "budget_usd": budget_usd,
    }
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _create_task(
    client: TestClient,
    *,
    parent_id: str,
    task_id: str,
    depends_on: list[str] | None = None,
    budget_usd: float = 20.0,
) -> dict[str, Any]:
    payload = {
        "type": "task",
        "title": f"Task {task_id}",
        "parent_id": parent_id,
        "created_by": "agent:planner-1",
        "budget_usd": budget_usd,
        "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
        "spec": {"id": task_id, "depends_on": depends_on or []},
    }
    response = client.post("/tickets", json=payload)
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _approve_budget(client: TestClient, ticket_id: str, token: str) -> Any:
    return client.post(
        f"/tickets/{ticket_id}/approve",
        json={"gate": "budget", "decision": "approved"},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_idea_creation_requires_positive_budget(client: TestClient) -> None:
    response = client.post(
        "/tickets",
        json={"type": "idea", "title": "No budget", "created_by": "human:alice"},
    )
    assert response.status_code == 422


def test_idea_enters_directly_at_approved(client: TestClient) -> None:
    idea = _create_idea(client)
    assert idea["state"] == "approved"


def test_approved_to_planning_then_epic_and_task_inherit_planning_state(
    client: TestClient,
) -> None:
    idea = _create_idea(client)
    assert _transition(client, idea["id"], "planning").status_code == 200

    epic = _create_epic(client, parent_id=idea["id"])
    assert epic["state"] == "planning"

    task = _create_task(client, parent_id=epic["id"], task_id="task-1")
    assert task["state"] == "planning"

    descendants = client.get(f"/tickets/{idea['id']}/descendants").json()["items"]
    assert {d["id"] for d in descendants} == {epic["id"], task["id"]}


def test_planning_to_ready_blocked_without_budget_approval(client: TestClient) -> None:
    idea = _create_idea(client, budget_usd=100.0)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"])
    _create_task(client, parent_id=epic["id"], task_id="task-1", budget_usd=20.0)

    response = _transition(client, idea["id"], "ready")
    assert response.status_code == 409
    assert "approved budget gate" in response.json()["detail"]


def test_planning_to_ready_blocked_when_task_budgets_exceed_idea_budget(
    client: TestClient,
) -> None:
    idea = _create_idea(client, budget_usd=50.0)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"])
    _create_task(client, parent_id=epic["id"], task_id="task-1", budget_usd=60.0)

    approver_token = _dev_login(client, "approver@example.com", "approver")
    assert _approve_budget(client, idea["id"], approver_token).status_code == 200

    response = _transition(client, idea["id"], "ready")
    assert response.status_code == 409
    assert "exceeds" in response.json()["detail"]


def test_planning_to_ready_blocked_by_a_cyclic_dependency_graph(client: TestClient) -> None:
    idea = _create_idea(client, budget_usd=100.0)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"])
    _create_task(
        client, parent_id=epic["id"], task_id="task-1", depends_on=["task-2"], budget_usd=20.0
    )
    _create_task(
        client, parent_id=epic["id"], task_id="task-2", depends_on=["task-1"], budget_usd=20.0
    )

    approver_token = _dev_login(client, "approver2@example.com", "approver")
    assert _approve_budget(client, idea["id"], approver_token).status_code == 200

    response = _transition(client, idea["id"], "ready")
    assert response.status_code == 409
    assert "cycle" in response.json()["detail"]


def test_planning_to_ready_succeeds_and_cascades_children_to_ready(client: TestClient) -> None:
    idea = _create_idea(client, budget_usd=100.0)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"], budget_usd=40.0)
    task = _create_task(client, parent_id=epic["id"], task_id="task-1", budget_usd=40.0)

    approver_token = _dev_login(client, "approver3@example.com", "approver")
    assert _approve_budget(client, idea["id"], approver_token).status_code == 200

    response = _transition(client, idea["id"], "ready")
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "ready"

    descendants = {
        d["id"]: d["state"]
        for d in client.get(f"/tickets/{idea['id']}/descendants").json()["items"]
    }
    assert descendants[epic["id"]] == "ready"
    assert descendants[task["id"]] == "ready"


def test_planning_questions_round_trip_to_escalated_and_back(client: TestClient) -> None:
    idea = _create_idea(client)
    _transition(client, idea["id"], "planning")

    escalate = _transition(client, idea["id"], "escalated", actor="agent:planner-1")
    assert escalate.status_code == 200
    assert escalate.json()["state"] == "escalated"

    approver_token = _dev_login(client, "approver4@example.com", "approver")
    response = client.post(
        f"/tickets/{idea['id']}/answer-planning-questions",
        json={"answers": "The target user is an internal support engineer."},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "planning"

    events = client.get(f"/tickets/{idea['id']}/events").json()["items"]
    messages = [e for e in events if e["kind"] == "message"]
    assert any(e["payload"].get("conclusion") == "planning_questions_answered" for e in messages)


def test_update_task_versions_an_edit_event_with_before_and_after(client: TestClient) -> None:
    idea = _create_idea(client)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"])
    task = _create_task(client, parent_id=epic["id"], task_id="task-1", budget_usd=15.0)

    approver_token = _dev_login(client, "approver5@example.com", "approver")
    response = client.patch(
        f"/tickets/{task['id']}",
        json={"title": "Renamed task", "budget_usd": 25.0},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["title"] == "Renamed task"
    assert response.json()["budget_usd"] == 25.0

    events = client.get(f"/tickets/{task['id']}/events").json()["items"]
    edit_events = [e for e in events if e["kind"] == "edit"]
    assert len(edit_events) == 1
    assert edit_events[0]["payload"]["before"]["title"] == "Task task-1"
    assert edit_events[0]["payload"]["after"]["title"] == "Renamed task"
    assert edit_events[0]["payload"]["before"]["budget_usd"] == 15.0
    assert edit_events[0]["payload"]["after"]["budget_usd"] == 25.0


def test_update_task_requires_approver_role(client: TestClient) -> None:
    idea = _create_idea(client)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"])
    task = _create_task(client, parent_id=epic["id"], task_id="task-1")

    viewer_token = _dev_login(client, "viewer5@example.com", "viewer")
    response = client.patch(
        f"/tickets/{task['id']}",
        json={"title": "nope"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert response.status_code == 403
