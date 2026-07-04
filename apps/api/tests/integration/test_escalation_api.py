from fastapi.testclient import TestClient

from .test_tickets_api import _create_task, _dev_login, _transition


def _escalated_ticket(client: TestClient) -> str:
    ticket = _create_task(client, budget_usd=0.01)
    ticket_id = ticket["id"]
    assert _transition(client, ticket_id, "in_progress").status_code == 200
    assert _transition(client, ticket_id, "escalated").status_code == 200
    return ticket_id


def test_approver_returns_escalated_ticket_to_dev(client: TestClient) -> None:
    ticket_id = _escalated_ticket(client)
    approver_token = _dev_login(client, "approver@example.com", "approver")

    response = client.post(
        f"/tickets/{ticket_id}/return-to-dev",
        json={"note": "Looked at the transcript, retry with a smaller diff."},
        headers={"Authorization": f"Bearer {approver_token}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["state"] == "in_progress"

    events = client.get(f"/tickets/{ticket_id}/events").json()["items"]
    bounce_events = [e for e in events if e["kind"] == "test_result"]
    assert len(bounce_events) == 1
    assert bounce_events[0]["payload"]["conclusion"] == "returned_by_human"
    report = bounce_events[0]["payload"]["failure_report"]
    assert "smaller diff" in report["expected_vs_actual"]


def test_viewer_cannot_return_ticket_to_dev(client: TestClient) -> None:
    ticket_id = _escalated_ticket(client)
    viewer_token = _dev_login(client, "viewer@example.com", "viewer")

    response = client.post(
        f"/tickets/{ticket_id}/return-to-dev",
        json={"note": "nope"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )

    assert response.status_code == 403


def test_return_to_dev_404_for_missing_ticket(client: TestClient) -> None:
    approver_token = _dev_login(client, "approver2@example.com", "approver")

    response = client.post(
        "/tickets/does-not-exist/return-to-dev",
        json={"note": "x"},
        headers={"Authorization": f"Bearer {approver_token}"},
    )

    assert response.status_code == 404
