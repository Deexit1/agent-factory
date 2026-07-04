import csv
import io
import statistics
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from .test_tickets_api import _create_task, _transition


def _backdate_created_at(db_session: Session, ticket_id: str, hours_ago: float) -> None:
    db_session.execute(
        text("UPDATE tickets SET created_at = :ts WHERE id = :id"),
        {"ts": datetime.now(UTC) - timedelta(hours=hours_ago), "id": ticket_id},
    )
    db_session.commit()


def _record_cost(client: TestClient, ticket_id: str, cost_usd: float) -> None:
    run = client.post(
        f"/tickets/{ticket_id}/agent-runs", json={"agent_role": "dev", "model": "sonnet"}
    ).json()
    resp = client.post(
        f"/tickets/{ticket_id}/agent-runs/{run['id']}/complete",
        json={"status": "completed", "cost_usd": cost_usd},
    )
    assert resp.status_code == 200, resp.text


def _close_ticket(
    client: TestClient, db_session: Session, *, bounces: int, cost_usd: float, hours_ago: float
) -> str:
    ticket = _create_task(client)
    ticket_id = ticket["id"]
    _backdate_created_at(db_session, ticket_id, hours_ago)

    assert _transition(client, ticket_id, "in_progress").status_code == 200
    for _ in range(bounces):
        assert _transition(client, ticket_id, "in_qa").status_code == 200
        assert _transition(client, ticket_id, "bounced").status_code == 200
        assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "in_qa").status_code == 200
    assert _transition(client, ticket_id, "done").status_code == 200

    _record_cost(client, ticket_id, cost_usd)
    return ticket_id


def _escalate_ticket(client: TestClient) -> str:
    ticket = _create_task(client)
    ticket_id = ticket["id"]
    assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "escalated").status_code == 200
    return ticket_id


def _seed_golden_dataset(client: TestClient, db_session: Session) -> dict[str, str]:
    ticket_a = _close_ticket(client, db_session, bounces=0, cost_usd=3.0, hours_ago=10.0)
    ticket_b = _close_ticket(client, db_session, bounces=1, cost_usd=5.0, hours_ago=5.0)
    ticket_c = _close_ticket(client, db_session, bounces=2, cost_usd=1.0, hours_ago=2.0)
    ticket_d = _escalate_ticket(client)
    _create_task(client)  # ticket E: still in_progress-less "ready", excluded entirely

    for ticket_id, note in [(ticket_a, "defect on A"), (ticket_c, "defect on C")]:
        response = client.post(
            "/dashboard/escaped-defects", json={"ticket_id": ticket_id, "note": note}
        )
        assert response.status_code == 201, response.text

    return {"a": ticket_a, "b": ticket_b, "c": ticket_c, "d": ticket_d}


def test_dashboard_metrics_match_seeded_fixture_exactly(
    client: TestClient, db_session: Session
) -> None:
    _seed_golden_dataset(client, db_session)

    response = client.get("/dashboard/metrics")
    assert response.status_code == 200, response.text
    metrics = response.json()

    assert metrics["tickets_closed"] == 3
    assert metrics["tickets_escalated"] == 1
    # first-pass = done AND bounce_count <= 1 (docs/00-vision.md): A(0) and B(1) qualify,
    # C(2) doesn't; rate is out of every terminal (done+escalated) ticket -> 2/4.
    assert metrics["first_pass_qa_rate"] == 0.5
    assert metrics["median_cost_per_closed_ticket_usd"] == 3.0
    assert metrics["escaped_defects"] == 2
    assert abs(metrics["median_cycle_time_hours"] - 5.0) < 0.05


def test_csv_export_reproduces_the_dashboard_dataset(
    client: TestClient, db_session: Session
) -> None:
    _seed_golden_dataset(client, db_session)

    metrics = client.get("/dashboard/metrics").json()
    csv_response = client.get("/dashboard/export.csv")

    assert csv_response.status_code == 200
    assert csv_response.headers["content-type"].startswith("text/csv")

    rows = list(csv.DictReader(io.StringIO(csv_response.text)))
    done_rows = [r for r in rows if r["state"] == "done"]
    escalated_rows = [r for r in rows if r["state"] == "escalated"]

    assert len(done_rows) == metrics["tickets_closed"]
    assert len(escalated_rows) == metrics["tickets_escalated"]
    assert sum(int(r["escaped_defects"]) for r in rows) == metrics["escaped_defects"]
    assert statistics.median(float(r["cost_usd"]) for r in done_rows) == (
        metrics["median_cost_per_closed_ticket_usd"]
    )
    assert statistics.median(float(r["cycle_time_hours"]) for r in done_rows) == (
        metrics["median_cycle_time_hours"]
    )


def test_escaped_defect_404_for_missing_ticket(client: TestClient) -> None:
    response = client.post(
        "/dashboard/escaped-defects", json={"ticket_id": "does-not-exist", "note": "x"}
    )
    assert response.status_code == 404


def test_dashboard_metrics_are_null_when_no_terminal_tickets_exist(client: TestClient) -> None:
    _create_task(client)

    metrics = client.get("/dashboard/metrics").json()

    assert metrics["tickets_closed"] == 0
    assert metrics["tickets_escalated"] == 0
    assert metrics["first_pass_qa_rate"] is None
    assert metrics["median_cost_per_closed_ticket_usd"] is None
    assert metrics["median_cycle_time_hours"] is None
    assert metrics["escaped_defects"] == 0
