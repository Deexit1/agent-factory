"""T-206 (SPEC-206 AC5): "A struck org's tickets are blocked, not deleted; appeal flow
reactivates them." Real Postgres. Mechanism tests reuse
test_billing_dunning.py's exact "in-flight ticket via direct service calls" precedent;
router tests prove the auth gating (staff-only strike/resolve, owner-only appeal
request) over real HTTP."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.db.models import Ticket, TicketState, TicketType
from api.repositories import org_repository
from api.repositories import ticket_repository as repo
from api.services import abuse_service, ticket_service
from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth
from .test_tickets_api import _dev_login


def _make_in_progress_ticket(session: Session, *, org_id: str) -> Ticket:
    ticket = repo.create_ticket(
        session,
        org_id=org_id,
        ticket_type=TicketType.TASK,
        title="In-flight work",
        parent_id=None,
        spec=None,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        assignee_agent=None,
        budget_usd=10.0,
        created_by="human:alice",
    )
    session.commit()
    ticket_service.request_transition(
        session, ticket.id, TicketState.IN_PROGRESS, "human:alice", org_id=org_id
    )
    return ticket


def test_strike_force_blocks_in_flight_tickets_without_deleting_them(
    db_session: Session,
) -> None:
    org = org_repository.create_org(db_session, name="Strike Org")
    ticket = _make_in_progress_ticket(db_session, org_id=org.id)

    strike, blocked = abuse_service.strike_org(
        db_session, org_id=org.id, reason="scraping farm", actor="human:staff@example.com"
    )
    db_session.commit()

    assert strike.status == "active"
    assert [t.id for t in blocked] == [ticket.id]
    stored = repo.get_ticket(db_session, ticket.id, org_id=org.id)
    assert stored is not None
    assert stored.state == TicketState.BLOCKED  # not deleted — still queryable


def test_blocked_to_ready_is_refused_for_a_non_human_actor(db_session: Session) -> None:
    """Regression: before T-206, BLOCKED had no whitelisted exit at all for ANY actor.
    This proves the new edge exists but is still refused for a system actor."""
    org = org_repository.create_org(db_session, name="Refuse Org")
    ticket = _make_in_progress_ticket(db_session, org_id=org.id)
    abuse_service.strike_org(
        db_session, org_id=org.id, reason="spam infra", actor="human:staff@example.com"
    )
    db_session.commit()

    try:
        ticket_service.request_transition(
            db_session, ticket.id, TicketState.READY, "system", org_id=org.id
        )
        raised = False
    except ticket_service.TransitionRefused:
        raised = True
    assert raised


def test_appeal_reinstatement_transitions_blocked_tickets_back_to_ready(
    db_session: Session,
) -> None:
    org = org_repository.create_org(db_session, name="Reinstate Org")
    ticket = _make_in_progress_ticket(db_session, org_id=org.id)
    strike, _blocked = abuse_service.strike_org(
        db_session, org_id=org.id, reason="malware", actor="human:staff@example.com"
    )
    db_session.commit()

    abuse_service.request_appeal(
        db_session,
        strike.id,
        org_id=org.id,
        note="this was a false positive",
        actor="human:owner@example.com",
    )
    db_session.commit()

    resolved, reactivated = abuse_service.resolve_appeal(
        db_session, strike.id, decision="reinstate", actor="human:staff@example.com"
    )
    db_session.commit()

    assert resolved.status == "reinstated"
    assert [t.id for t in reactivated] == [ticket.id]
    stored = repo.get_ticket(db_session, ticket.id, org_id=org.id)
    assert stored is not None
    assert stored.state == TicketState.READY


def test_appeal_denial_leaves_tickets_blocked(db_session: Session) -> None:
    org = org_repository.create_org(db_session, name="Deny Appeal Org")
    ticket = _make_in_progress_ticket(db_session, org_id=org.id)
    strike, _blocked = abuse_service.strike_org(
        db_session, org_id=org.id, reason="credential stuffing", actor="human:staff@example.com"
    )
    db_session.commit()
    abuse_service.request_appeal(
        db_session, strike.id, org_id=org.id, note="please review", actor="human:owner@example.com"
    )
    db_session.commit()

    resolved, reactivated = abuse_service.resolve_appeal(
        db_session, strike.id, decision="deny", actor="human:staff@example.com"
    )
    db_session.commit()

    assert resolved.status == "denied"
    assert reactivated == []
    stored = repo.get_ticket(db_session, ticket.id, org_id=org.id)
    assert stored is not None
    assert stored.state == TicketState.BLOCKED


# --- Router-level auth gating (real HTTP) ---


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


def _staff_token(client: TestClient, monkeypatch: Any, email: str) -> str:
    monkeypatch.setenv("PLATFORM_STAFF_EMAILS", email)
    return _dev_login(client, email, "viewer")


def test_non_staff_cannot_impose_a_strike(client: TestClient) -> None:
    org_id, owner_org_token = _owner_org_token(client, "strike-nonstaff@example.com", "Nonstaff")
    response = client.post(
        f"/admin/orgs/{org_id}/strikes",
        json={"reason": "test"},
        headers=_auth(owner_org_token),
    )
    assert response.status_code == 403


def test_staff_can_strike_and_owner_can_request_appeal_but_not_resolve_it(
    client: TestClient, monkeypatch: Any
) -> None:
    org_id, owner_org_token = _owner_org_token(client, "strike-owner@example.com", "Strike HTTP")
    staff_token = _staff_token(client, monkeypatch, "strike-staff@example.com")

    strike_response = client.post(
        f"/admin/orgs/{org_id}/strikes",
        json={"reason": "malware"},
        headers=_auth(staff_token),
    )
    assert strike_response.status_code == 201, strike_response.text
    strike_id = strike_response.json()["id"]

    appeal_response = client.post(
        f"/orgs/{org_id}/strikes/{strike_id}/appeal",
        json={"note": "false positive"},
        headers=_auth(owner_org_token),
    )
    assert appeal_response.status_code == 200, appeal_response.text
    assert appeal_response.json()["status"] == "appealed"

    owner_resolve_attempt = client.post(
        f"/admin/strikes/{strike_id}/resolve-appeal",
        json={"decision": "reinstate"},
        headers=_auth(owner_org_token),
    )
    assert owner_resolve_attempt.status_code == 403

    staff_resolve = client.post(
        f"/admin/strikes/{strike_id}/resolve-appeal",
        json={"decision": "reinstate"},
        headers=_auth(staff_token),
    )
    assert staff_resolve.status_code == 200, staff_resolve.text
    assert staff_resolve.json()["status"] == "reinstated"


def test_staff_can_list_a_non_member_orgs_strikes(client: TestClient, monkeypatch: Any) -> None:
    org_id, owner_org_token = _owner_org_token(
        client, "strike-list-owner@example.com", "Strike List Org"
    )
    staff_token = _staff_token(client, monkeypatch, "strike-list-staff@example.com")
    client.post(
        f"/admin/orgs/{org_id}/strikes", json={"reason": "spam"}, headers=_auth(staff_token)
    )

    staff_view = client.get(f"/orgs/{org_id}/strikes", headers=_auth(staff_token))
    assert staff_view.status_code == 200, staff_view.text
    assert len(staff_view.json()["items"]) == 1

    owner_view = client.get(f"/orgs/{org_id}/strikes", headers=_auth(owner_org_token))
    assert owner_view.status_code == 200
    assert len(owner_view.json()["items"]) == 1


def test_non_owner_cannot_request_an_appeal(client: TestClient, monkeypatch: Any) -> None:
    org_id, owner_org_token = _owner_org_token(
        client, "strike-viewer-owner@example.com", "Strike Viewer Org"
    )
    staff_token = _staff_token(client, monkeypatch, "strike-staff2@example.com")
    strike_id = client.post(
        f"/admin/orgs/{org_id}/strikes",
        json={"reason": "spam"},
        headers=_auth(staff_token),
    ).json()["id"]

    invite = client.post(
        f"/orgs/{org_id}/invites",
        json={"email": "strike-viewer@example.com", "role": "viewer"},
        headers=_auth(owner_org_token),
    ).json()
    viewer_session = _dev_login(client, "strike-viewer@example.com", "viewer")
    client.post(f"/orgs/invites/{invite['token']}/accept", headers=_auth(viewer_session))
    viewer_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(viewer_session)
    ).json()["token"]

    response = client.post(
        f"/orgs/{org_id}/strikes/{strike_id}/appeal",
        json={"note": "let us back in"},
        headers=_auth(viewer_org_token),
    )
    assert response.status_code == 403
