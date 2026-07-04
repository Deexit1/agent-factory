from fastapi.testclient import TestClient

from .test_tickets_api import _create_task


def test_create_event_appends_to_ticket_history(client: TestClient) -> None:
    ticket = _create_task(client)

    response = client.post(
        f"/tickets/{ticket['id']}/events",
        json={
            "actor": "agent:sandbox-runner",
            "kind": "tool_call",
            "payload": {"egress": "pypi.org", "allowed": True},
        },
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["ticket_id"] == ticket["id"]
    assert body["kind"] == "tool_call"
    assert body["payload"] == {"egress": "pypi.org", "allowed": True}

    events = client.get(f"/tickets/{ticket['id']}/events").json()
    assert any(e["id"] == body["id"] for e in events["items"])


def test_create_event_rejects_transition_kind(client: TestClient) -> None:
    ticket = _create_task(client)

    response = client.post(
        f"/tickets/{ticket['id']}/events",
        json={"actor": "agent:x", "kind": "transition", "payload": {}},
    )

    assert response.status_code == 422


def test_create_event_404_for_missing_ticket(client: TestClient) -> None:
    response = client.post(
        "/tickets/does-not-exist/events",
        json={"actor": "agent:x", "kind": "message", "payload": {}},
    )

    assert response.status_code == 404
