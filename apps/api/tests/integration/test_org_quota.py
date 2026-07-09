"""T-201 (SPEC-201 AC3): exceeding the org's parallel-ticket quota leaves the extra
task `ready` with a quota event — real end-to-end, not a unit test with a mocked
count. No self-serve API exists yet to configure org quotas (a real, disclosed gap —
see tasks/CHANGELOG.md); this test sets `orgs.max_parallel_tickets` directly, the way
an ops action would today."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.tos import CURRENT_TOS_VERSION

from .test_tickets_api import _dev_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_task_as(client: TestClient, token: str, title: str) -> dict[str, Any]:
    response = client.post(
        "/tickets",
        headers=_auth(token),
        json={
            "type": "task",
            "title": title,
            "created_by": "human:bob",
            "budget_usd": 20.0,
            "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _transition_as(client: TestClient, token: str, ticket_id: str, to_state: str) -> Any:
    return client.post(
        f"/tickets/{ticket_id}/transition",
        json={"to_state": to_state, "actor": "human:bob"},
        headers=_auth(token),
    )


def test_exceeding_the_org_quota_leaves_the_extra_task_ready_with_a_quota_event(
    client: TestClient, db_session: Session
) -> None:
    bob_token = _dev_login(client, "bob-quota@example.com", "owner")
    org_b = client.post(
        "/orgs",
        json={"name": "Quota org", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(bob_token),
    ).json()
    bob_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(bob_token)
    ).json()["token"]

    db_session.execute(
        text("UPDATE orgs SET max_parallel_tickets = 1 WHERE id = :id"), {"id": org_b["id"]}
    )
    db_session.commit()

    task_1 = _create_task_as(client, bob_org_b_token, "First task")
    task_2 = _create_task_as(client, bob_org_b_token, "Second task")

    first = _transition_as(client, bob_org_b_token, task_1["id"], "in_progress")
    assert first.status_code == 200, first.text

    second = _transition_as(client, bob_org_b_token, task_2["id"], "in_progress")
    assert second.status_code == 409, second.text
    assert "quota" in second.json()["detail"].lower()

    ticket_after = client.get(f"/tickets/{task_2['id']}", headers=_auth(bob_org_b_token)).json()
    assert ticket_after["state"] == "ready"

    events = client.get(
        f"/tickets/{task_2['id']}/events?limit=100", headers=_auth(bob_org_b_token)
    ).json()["items"]
    rejected = [e for e in events if e["kind"] == "transition" and e["payload"].get("rejected")]
    assert len(rejected) == 1
    assert "quota" in rejected[0]["payload"]["reason"].lower()


def test_org_with_no_quota_configured_is_unaffected(client: TestClient) -> None:
    """max_parallel_tickets is nullable (unlimited) by default — every existing org
    (including the seeded default org every other test in this suite runs against)
    must be completely unaffected by this feature."""
    bob_token = _dev_login(client, "bob-no-quota@example.com", "owner")
    org_b = client.post(
        "/orgs",
        json={"name": "No quota org", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(bob_token),
    ).json()
    bob_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(bob_token)
    ).json()["token"]

    for i in range(3):
        task = _create_task_as(client, bob_org_b_token, f"Task {i}")
        result = _transition_as(client, bob_org_b_token, task["id"], "in_progress")
        assert result.status_code == 200, result.text
