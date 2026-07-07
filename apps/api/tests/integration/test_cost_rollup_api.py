"""T-108 AC1: idea drawer rollup equals the ledger sum of all descendants."""

from fastapi.testclient import TestClient

from .test_idea_planning_workflow import _create_epic, _create_idea
from .test_idea_planning_workflow import _create_task as _create_planned_task
from .test_tickets_api import _create_task


def _record_cost(client: TestClient, ticket_id: str, cost_usd: float) -> None:
    run = client.post(
        f"/tickets/{ticket_id}/agent-runs", json={"agent_role": "dev", "model": "sonnet"}
    ).json()
    resp = client.post(
        f"/tickets/{ticket_id}/agent-runs/{run['id']}/complete",
        json={"status": "completed", "cost_usd": cost_usd},
    )
    assert resp.status_code == 200, resp.text


def test_idea_rollup_equals_ledger_sum_of_all_descendants(client: TestClient) -> None:
    idea = _create_idea(client)
    epic = _create_epic(client, parent_id=idea["id"])
    task_a = _create_planned_task(client, parent_id=epic["id"], task_id="task-a")
    task_b = _create_planned_task(client, parent_id=epic["id"], task_id="task-b")

    _record_cost(client, task_a["id"], 3.0)
    _record_cost(client, task_a["id"], 1.5)
    _record_cost(client, task_b["id"], 2.25)
    _record_cost(client, epic["id"], 0.5)

    response = client.get(f"/tickets/{idea['id']}/cost-rollup")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["ticket_id"] == idea["id"]
    assert body["descendant_count"] == 3  # epic + task_a + task_b
    assert body["rollup_usd"] == 3.0 + 1.5 + 2.25 + 0.5


def test_epic_rollup_only_sums_its_own_descendants(client: TestClient) -> None:
    idea = _create_idea(client)
    epic = _create_epic(client, parent_id=idea["id"])
    task_a = _create_planned_task(client, parent_id=epic["id"], task_id="task-a")

    _record_cost(client, idea["id"], 10.0)  # cost on the idea itself, above the epic
    _record_cost(client, task_a["id"], 4.0)

    response = client.get(f"/tickets/{epic['id']}/cost-rollup")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["descendant_count"] == 1  # task_a only
    assert body["rollup_usd"] == 4.0


def test_leaf_task_rollup_is_just_its_own_cost(client: TestClient) -> None:
    task = _create_task(client)
    _record_cost(client, task["id"], 1.23)

    response = client.get(f"/tickets/{task['id']}/cost-rollup")
    assert response.status_code == 200, response.text
    body = response.json()

    assert body["descendant_count"] == 0
    assert body["rollup_usd"] == 1.23


def test_cost_rollup_404_for_missing_ticket(client: TestClient) -> None:
    response = client.get("/tickets/does-not-exist/cost-rollup")
    assert response.status_code == 404
