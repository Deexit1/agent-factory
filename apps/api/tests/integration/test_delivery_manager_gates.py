"""T-104 / SPEC-103: the ready -> in_progress assignment gates enforced in
apps/api (dependency-done, spent-vs-budget, profile/repo capacity), and the
escalated -> ready requeue-for-reassignment transition."""

from typing import Any

from fastapi.testclient import TestClient

from .test_idea_planning_workflow import _approve_budget, _create_epic, _create_idea, _create_task
from .test_tickets_api import _dev_login, _transition


def _ready_task(
    client: TestClient,
    *,
    task_id: str,
    depends_on: list[str] | None = None,
    budget_usd: float = 20.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Drives one idea -> planning -> approved -> ready task all the way to `ready`,
    returning (idea, task)."""
    idea = _create_idea(client, budget_usd=100.0)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"], budget_usd=90.0)
    task = _create_task(
        client, parent_id=epic["id"], task_id=task_id, depends_on=depends_on, budget_usd=budget_usd
    )

    approver_token = _dev_login(client, f"approver-{task_id}@example.com", "approver")
    assert _approve_budget(client, idea["id"], approver_token).status_code == 200
    assert _transition(client, idea["id"], "ready").status_code == 200
    return idea, task


def _record_spend(client: TestClient, ticket_id: str, cost_usd: float) -> None:
    run = client.post(
        f"/tickets/{ticket_id}/agent-runs", json={"agent_role": "dev", "model": "sonnet"}
    ).json()
    resp = client.post(
        f"/tickets/{ticket_id}/agent-runs/{run['id']}/complete",
        json={"status": "completed", "cost_usd": cost_usd},
    )
    assert resp.status_code == 200, resp.text


def test_dependent_task_cannot_start_before_its_dependency_is_done(client: TestClient) -> None:
    idea = _create_idea(client, budget_usd=100.0)
    _transition(client, idea["id"], "planning")
    epic = _create_epic(client, parent_id=idea["id"], budget_usd=90.0)
    task_a = _create_task(client, parent_id=epic["id"], task_id="task-a", budget_usd=20.0)
    task_b = _create_task(
        client, parent_id=epic["id"], task_id="task-b", depends_on=["task-a"], budget_usd=20.0
    )

    approver_token = _dev_login(client, "approver-chain@example.com", "approver")
    assert _approve_budget(client, idea["id"], approver_token).status_code == 200
    assert _transition(client, idea["id"], "ready").status_code == 200

    # B is refused while A isn't done yet.
    response = _transition(client, task_b["id"], "in_progress")
    assert response.status_code == 409
    assert "dependencies are not done" in response.json()["detail"]

    # Drive A to done.
    assert _transition(client, task_a["id"], "in_progress").status_code == 200
    assert _transition(client, task_a["id"], "in_review").status_code == 200
    assert _transition(client, task_a["id"], "in_qa").status_code == 200
    assert _transition(client, task_a["id"], "done").status_code == 200

    # Now B can start.
    assert _transition(client, task_b["id"], "in_progress").status_code == 200


def test_profile_max_parallel_defers_a_third_assignment(client: TestClient) -> None:
    _, task1 = _ready_task(client, task_id="task-cap-1")
    _, task2 = _ready_task(client, task_id="task-cap-2")
    _, task3 = _ready_task(client, task_id="task-cap-3")

    def _assign(task_id: str) -> Any:
        return client.post(
            f"/tickets/{task_id}/transition",
            json={
                "to_state": "in_progress",
                "actor": "agent:delivery-manager",
                "assignee_agent": "dev-generalist",
            },
        )

    # Registry seeds dev-generalist at max_parallel=2.
    assert _assign(task1["id"]).status_code == 200
    assert _assign(task2["id"]).status_code == 200

    third = _assign(task3["id"])
    assert third.status_code == 409
    assert "max_parallel capacity" in third.json()["detail"]


def test_reassignment_refused_once_task_has_already_spent_its_budget(client: TestClient) -> None:
    _, task = _ready_task(client, task_id="task-spent", budget_usd=10.0)

    assert _transition(client, task["id"], "in_progress").status_code == 200
    _record_spend(client, task["id"], 10.0)
    assert _transition(client, task["id"], "escalated").status_code == 200

    approver_token = _dev_login(client, "approver-requeue@example.com", "approver")
    requeue = client.post(
        f"/tickets/{task['id']}/transition",
        json={"to_state": "ready", "actor": "human:approver"},
        headers={"Authorization": f"Bearer {approver_token}"},
    )
    assert requeue.status_code == 200, requeue.text

    # The Delivery Manager (or anyone) proposes reassigning it anyway — the API
    # refuses regardless, since its own cost_ledger spend already met its budget.
    response = client.post(
        f"/tickets/{task['id']}/transition",
        json={
            "to_state": "in_progress",
            "actor": "agent:delivery-manager",
            "assignee_agent": "dev-generalist",
        },
    )
    assert response.status_code == 409
    assert "already spent its budget" in response.json()["detail"]


def test_utilisation_endpoint_matches_real_in_progress_counts(client: TestClient) -> None:
    _, task1 = _ready_task(client, task_id="task-util-1")
    _, task2 = _ready_task(client, task_id="task-util-2")

    def _assign(task_id: str) -> Any:
        return client.post(
            f"/tickets/{task_id}/transition",
            json={
                "to_state": "in_progress",
                "actor": "agent:delivery-manager",
                "assignee_agent": "dev-generalist",
            },
        )

    assert _assign(task1["id"]).status_code == 200
    assert _assign(task2["id"]).status_code == 200

    response = client.get("/capability-registry/utilisation")
    assert response.status_code == 200, response.text
    items = {row["profile"]: row for row in response.json()["items"]}
    assert items["dev-generalist"]["in_progress_count"] == 2
    assert items["dev-generalist"]["max_parallel"] == 2


def test_escalated_to_ready_requires_human_actor(client: TestClient) -> None:
    _, task = _ready_task(client, task_id="task-requeue-auth")
    assert _transition(client, task["id"], "in_progress").status_code == 200
    assert _transition(client, task["id"], "escalated").status_code == 200

    agent_attempt = _transition(client, task["id"], "ready", actor="agent:delivery-manager")
    assert agent_attempt.status_code == 409

    assert _transition(client, task["id"], "ready", actor="human:alice").status_code == 200
