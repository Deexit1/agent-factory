from fastapi.testclient import TestClient

from .test_tickets_api import _create_task, _transition


def test_transition_is_broadcast_over_websocket(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]

    with client.websocket_connect(f"/ws/tickets/{ticket_id}") as ws:
        response = _transition(client, ticket_id, "in_progress")
        assert response.status_code == 200

        message = ws.receive_json()

    assert message["ticket_id"] == ticket_id
    assert message["kind"] == "transition"
    assert message["payload"] == {"from": "ready", "to": "in_progress"}


def test_rejected_transition_is_also_broadcast(client: TestClient) -> None:
    ticket = _create_task(client)
    ticket_id = ticket["id"]

    with client.websocket_connect(f"/ws/tickets/{ticket_id}") as ws:
        response = _transition(client, ticket_id, "done")
        assert response.status_code == 409

        message = ws.receive_json()

    assert message["payload"]["rejected"] is True
    assert message["payload"]["to"] == "done"
