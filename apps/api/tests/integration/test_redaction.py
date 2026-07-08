"""T-202 (SPEC-202 AC2): a planted key string in a ticket event payload never
persists to the real DB — proven end-to-end through the real POST /events ->
ticket_repository.append_event -> real Postgres round trip, not a mocked session."""

from fastapi.testclient import TestClient

from .test_tickets_api import _dev_login

_FAKE_ANTHROPIC_KEY = "sk-ant-api03-FAKE00000000000000000000000000000000000000000000"
_FAKE_OPENAI_KEY = "sk-FAKE000000000000000000000000000000"


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_a_planted_key_in_an_event_payload_is_redacted_before_it_reaches_the_db(
    client: TestClient,
) -> None:
    owner_token = _dev_login(client, "redact-owner@example.com", "owner")
    ticket = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "Some task",
            "created_by": "human:redact-owner",
            "budget_usd": 10.0,
            "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
        },
        headers=_auth(owner_token),
    ).json()

    create_event = client.post(
        f"/tickets/{ticket['id']}/events",
        json={
            "actor": "agent:dev",
            "kind": "message",
            "payload": {
                "text": f"leaked anthropic key: {_FAKE_ANTHROPIC_KEY}",
                "nested": {"inner": f"leaked openai key: {_FAKE_OPENAI_KEY}"},
            },
        },
        headers=_auth(owner_token),
    )
    assert create_event.status_code == 201, create_event.text
    assert _FAKE_ANTHROPIC_KEY not in create_event.text
    assert _FAKE_OPENAI_KEY not in create_event.text
    assert "[REDACTED-KEY]" in create_event.text

    fetched = client.get(
        f"/tickets/{ticket['id']}/events?limit=100", headers=_auth(owner_token)
    )
    assert _FAKE_ANTHROPIC_KEY not in fetched.text
    assert _FAKE_OPENAI_KEY not in fetched.text
    assert "[REDACTED-KEY]" in fetched.text
