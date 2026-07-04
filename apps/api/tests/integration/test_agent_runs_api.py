from fastapi.testclient import TestClient

from .test_tickets_api import _create_task


def test_create_and_complete_agent_run(client: TestClient) -> None:
    ticket = _create_task(client)

    created = client.post(
        f"/tickets/{ticket['id']}/agent-runs",
        json={"agent_role": "dev", "model": "sonnet", "trace_id": "trace-1"},
    )
    assert created.status_code == 201, created.text
    run = created.json()
    assert run["status"] == "running"
    assert run["cost_usd"] == 0

    completed = client.post(
        f"/tickets/{ticket['id']}/agent-runs/{run['id']}/complete",
        json={"status": "completed", "tokens_in": 1000, "tokens_out": 200, "cost_usd": 0.42},
    )
    assert completed.status_code == 200, completed.text
    body = completed.json()
    assert body["status"] == "completed"
    assert body["cost_usd"] == 0.42
    assert body["ended_at"] is not None


def test_complete_agent_run_rejects_running_status(client: TestClient) -> None:
    ticket = _create_task(client)
    run = client.post(
        f"/tickets/{ticket['id']}/agent-runs",
        json={"agent_role": "dev", "model": "sonnet"},
    ).json()

    response = client.post(
        f"/tickets/{ticket['id']}/agent-runs/{run['id']}/complete",
        json={"status": "running", "cost_usd": 0},
    )

    assert response.status_code == 422


def test_agent_run_404_for_missing_ticket(client: TestClient) -> None:
    response = client.post(
        "/tickets/does-not-exist/agent-runs",
        json={"agent_role": "dev", "model": "sonnet"},
    )

    assert response.status_code == 404


def test_complete_agent_run_404_for_wrong_ticket(client: TestClient) -> None:
    ticket_a = _create_task(client)
    ticket_b = _create_task(client)
    run = client.post(
        f"/tickets/{ticket_a['id']}/agent-runs",
        json={"agent_role": "dev", "model": "sonnet"},
    ).json()

    response = client.post(
        f"/tickets/{ticket_b['id']}/agent-runs/{run['id']}/complete",
        json={"status": "completed", "cost_usd": 0},
    )

    assert response.status_code == 404


def test_cost_ledger_total_equals_sum_of_agent_run_costs(client: TestClient) -> None:
    ticket = _create_task(client)

    costs = [1.5, 0.25, 3.0]
    for cost in costs:
        run = client.post(
            f"/tickets/{ticket['id']}/agent-runs",
            json={"agent_role": "dev", "model": "sonnet"},
        ).json()
        client.post(
            f"/tickets/{ticket['id']}/agent-runs/{run['id']}/complete",
            json={"status": "completed", "cost_usd": cost},
        )

    runs = client.get(f"/tickets/{ticket['id']}/agent-runs").json()
    ledger = client.get(f"/tickets/{ticket['id']}/cost-ledger").json()
    summary = client.get(f"/tickets/{ticket['id']}/cost-summary").json()

    assert len(runs) == 3
    assert len(ledger) == 3
    assert summary["agent_runs_total_usd"] == sum(costs)
    assert summary["cost_ledger_total_usd"] == sum(costs)
    assert summary["agent_runs_total_usd"] == summary["cost_ledger_total_usd"]


def test_zero_cost_run_does_not_create_ledger_entry(client: TestClient) -> None:
    ticket = _create_task(client)
    run = client.post(
        f"/tickets/{ticket['id']}/agent-runs",
        json={"agent_role": "dev", "model": "sonnet"},
    ).json()
    client.post(
        f"/tickets/{ticket['id']}/agent-runs/{run['id']}/complete",
        json={"status": "failed", "cost_usd": 0},
    )

    ledger = client.get(f"/tickets/{ticket['id']}/cost-ledger").json()
    assert ledger == []
