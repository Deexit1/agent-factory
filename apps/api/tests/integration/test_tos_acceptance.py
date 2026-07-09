"""T-206 (SPEC-206 AC3): ToS acceptance is recorded with version + timestamp at org
creation, and an org whose latest acceptance goes stale (a real ToS version bump) is
re-prompted — ticket creation is blocked until it re-accepts. Orgs with NO acceptance
record at all (pre-T-206 orgs, every other test fixture in this suite) are
grandfathered, not retroactively broken — see ticket_service._is_org_tos_current."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api import tos
from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth
from .test_tickets_api import _dev_login


def test_get_tos_returns_the_current_version_and_policy_text(client: TestClient) -> None:
    owner_token = _dev_login(client, "tos-get@example.com", "owner")
    response = client.get("/tos", headers=_auth(owner_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == CURRENT_TOS_VERSION
    assert len(body["policy_text"]) > 0


def _owner_org_token(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    owner_token = _dev_login(client, email, "owner")
    org = client.post(
        "/orgs",
        json={"name": org_name, "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(owner_token),
    ).json()
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    return org_id, owner_org_token


def _submit_idea(client: TestClient, token: str) -> Any:
    return client.post(
        "/tickets",
        json={
            "type": "idea",
            "title": "A perfectly ordinary idea",
            "budget_usd": 50.0,
            "created_by": "human:submitter",
        },
        headers=_auth(token),
    )


def test_org_creation_records_tos_acceptance_with_version_and_timestamp(
    client: TestClient, db_session: Session
) -> None:
    owner_token = _dev_login(client, "tos-create@example.com", "owner")
    org = client.post(
        "/orgs",
        json={"name": "ToS Org", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(owner_token),
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["id"]

    row = db_session.execute(
        text(
            "SELECT tos_version, accepted_by, accepted_at FROM tos_acceptances "
            "WHERE org_id = :id"
        ),
        {"id": org_id},
    ).one()
    assert row.tos_version == CURRENT_TOS_VERSION
    assert row.accepted_by == "tos-create@example.com"
    assert row.accepted_at is not None


def test_org_creation_rejects_a_stale_tos_version(client: TestClient) -> None:
    owner_token = _dev_login(client, "tos-stale@example.com", "owner")
    response = client.post(
        "/orgs",
        json={"name": "Stale Org", "tos_version": "2020-01-01"},
        headers=_auth(owner_token),
    )
    assert response.status_code == 422


def test_org_with_no_acceptance_record_is_grandfathered_and_can_create_tickets(
    client: TestClient,
) -> None:
    """The seeded default org (and every pre-T-206 org) has zero tos_acceptances rows —
    it must keep working exactly as before, not be retroactively blocked."""
    # Use the shared service-token client (DEFAULT_ORG_ID, no ToS row at all).
    response = client.post(
        "/tickets",
        json={
            "type": "idea",
            "title": "Default org idea",
            "budget_usd": 25.0,
            "created_by": "human:default-org-user",
        },
    )
    assert response.status_code == 201, response.text


def test_org_is_reprompted_after_a_tos_version_bump_and_unblocked_after_reaccepting(
    client: TestClient, db_session: Session, monkeypatch: Any
) -> None:
    org_id, owner_org_token = _owner_org_token(client, "tos-reprompt@example.com", "Reprompt Org")

    # Sanity: fresh org, current version, ticket creation works.
    assert _submit_idea(client, owner_org_token).status_code == 201

    # Simulate a real ToS version bump.
    new_version = "2027-01-01"
    monkeypatch.setattr(tos, "CURRENT_TOS_VERSION", new_version)

    blocked = _submit_idea(client, owner_org_token)
    assert blocked.status_code == 403, blocked.text

    # Re-accepting the (now current) version unblocks it.
    accept = client.post(
        f"/orgs/{org_id}/tos/accept",
        json={"tos_version": new_version},
        headers=_auth(owner_org_token),
    )
    assert accept.status_code == 204, accept.text

    unblocked = _submit_idea(client, owner_org_token)
    assert unblocked.status_code == 201, unblocked.text


def test_only_approver_or_owner_may_accept_tos(client: TestClient, monkeypatch: Any) -> None:
    org_id, owner_org_token = _owner_org_token(client, "tos-viewer@example.com", "Viewer Org")
    invite = client.post(
        f"/orgs/{org_id}/invites",
        json={"email": "tos-viewer-member@example.com", "role": "viewer"},
        headers=_auth(owner_org_token),
    ).json()
    viewer_session = _dev_login(client, "tos-viewer-member@example.com", "viewer")
    client.post(f"/orgs/invites/{invite['token']}/accept", headers=_auth(viewer_session))
    viewer_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(viewer_session)
    ).json()["token"]

    response = client.post(
        f"/orgs/{org_id}/tos/accept",
        json={"tos_version": CURRENT_TOS_VERSION},
        headers=_auth(viewer_org_token),
    )
    assert response.status_code == 403
