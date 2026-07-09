"""T-201 (SPEC-201 AC1, AC4): real multi-org cross-tenant isolation + invite flow —
a second org created for real via POST /orgs, not a synthetic org_id string (that
lower-level repo-layer check already exists in test_ticket_repository.py from T-102)."""

from typing import Any

from fastapi.testclient import TestClient

from api.tos import CURRENT_TOS_VERSION

from .test_tickets_api import _create_task, _dev_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _create_task_as(client: TestClient, token: str) -> dict[str, Any]:
    response = client.post(
        "/tickets",
        headers=_auth(token),
        json={
            "type": "task",
            "title": "Org B's ticket",
            "created_by": "human:bob",
            "budget_usd": 20.0,
            "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_owner_cannot_read_or_write_another_orgs_tickets(client: TestClient) -> None:
    """AC1: cross-tenant read/write attempts all fail (API 404) — the ticket API
    itself, not just the repository layer, via a real second org."""
    task_a = _create_task(client)  # default org, via the client fixture's service token

    bob_token = _dev_login(client, "bob@example.com", "owner")
    org_b = client.post(
        "/orgs",
        json={"name": "Org B", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(bob_token),
    ).json()
    switched = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(bob_token)
    )
    assert switched.status_code == 200, switched.text
    bob_org_b_token = switched.json()["token"]

    task_b = _create_task_as(client, bob_org_b_token)

    # Org B's owner cannot see org A's (default org's) ticket.
    assert client.get(f"/tickets/{task_a['id']}", headers=_auth(bob_org_b_token)).status_code == 404
    # The default org cannot see org B's ticket.
    assert client.get(f"/tickets/{task_b['id']}").status_code == 404
    # Each org can see its own.
    assert client.get(f"/tickets/{task_a['id']}").status_code == 200
    assert (
        client.get(f"/tickets/{task_b['id']}", headers=_auth(bob_org_b_token)).status_code == 200
    )


def test_invited_member_gets_role_appropriate_access_and_viewer_cannot_approve(
    client: TestClient,
) -> None:
    """AC4: an invited member gets role-appropriate access (a viewer can read but
    not approve — the existing 403 gate, now exercised via a real invite + accept
    round trip instead of dev-login's role param alone)."""
    bob_token = _dev_login(client, "bob-invites@example.com", "owner")
    org_b = client.post(
        "/orgs",
        json={"name": "Org B invites", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(bob_token),
    ).json()
    bob_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(bob_token)
    ).json()["token"]
    task_b = _create_task_as(client, bob_org_b_token)

    invite = client.post(
        f"/orgs/{org_b['id']}/invites",
        json={"email": "carol-viewer@example.com", "role": "viewer"},
        headers=_auth(bob_org_b_token),
    )
    assert invite.status_code == 201, invite.text
    invite_token = invite.json()["token"]

    # Carol must already be an authenticated identity (any org) before accepting —
    # dev-login as usual, into the default org, then accept lands her in org B too.
    carol_default_token = _dev_login(client, "carol-viewer@example.com", "viewer")
    accepted = client.post(
        f"/orgs/invites/{invite_token}/accept", headers=_auth(carol_default_token)
    )
    assert accepted.status_code == 201, accepted.text
    assert accepted.json()["role"] == "viewer"

    carol_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(carol_default_token)
    ).json()["token"]

    # Role-appropriate access: a viewer can read the org's ticket...
    read = client.get(f"/tickets/{task_b['id']}", headers=_auth(carol_org_b_token))
    assert read.status_code == 200

    # ...but cannot approve (existing gate, now reached via a real invite/accept path).
    approve = client.post(
        f"/tickets/{task_b['id']}/approve",
        json={"gate": "budget", "decision": "approved"},
        headers=_auth(carol_org_b_token),
    )
    assert approve.status_code == 403


def test_only_the_org_owner_may_invite_members(client: TestClient) -> None:
    bob_token = _dev_login(client, "bob-owner-only@example.com", "owner")
    org_b = client.post(
        "/orgs",
        json={"name": "Owner-only org", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(bob_token),
    ).json()
    bob_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(bob_token)
    ).json()["token"]

    invite = client.post(
        f"/orgs/{org_b['id']}/invites",
        json={"email": "dave@example.com", "role": "member"},
        headers=_auth(bob_org_b_token),
    )
    assert invite.status_code == 201

    dave_default_token = _dev_login(client, "dave@example.com", "member")
    accepted = client.post(
        f"/orgs/invites/{invite.json()['token']}/accept", headers=_auth(dave_default_token)
    )
    dave_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(dave_default_token)
    ).json()["token"]
    assert accepted.status_code == 201

    # A plain member cannot invite others into org B — only the owner can.
    denied = client.post(
        f"/orgs/{org_b['id']}/invites",
        json={"email": "eve@example.com", "role": "viewer"},
        headers=_auth(dave_org_b_token),
    )
    assert denied.status_code == 403
