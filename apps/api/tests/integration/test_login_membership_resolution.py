"""T-210: a brand-new real login with no org membership anywhere used to be
silently auto-joined into the shared seeded default org — every new signup landed
in the same org as every other one, skipping onboarding entirely the moment that
org was itself onboarded. These tests cover org_service.resolve_login_membership
directly (real OIDC is never mocked anywhere in this repo, so the service function
is the right unit boundary) plus the dev-login `org_id: null` capability that
exercises the identical path through a real HTTP round-trip.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.repositories import org_repository
from api.services import org_service, user_service
from api.tenancy import DEFAULT_ORG_ID, PENDING_ORG_ID


def test_new_non_admin_user_gets_an_unpersisted_pending_membership(
    db_session: Session,
) -> None:
    user_service.get_or_create_user(db_session, "brand-new@example.com")

    membership = org_service.resolve_login_membership(
        db_session, user_email="brand-new@example.com"
    )

    assert membership.org_id == PENDING_ORG_ID
    assert membership.role.value == "viewer"
    # Never written to the DB — org_repository.list_orgs_for_user must still see
    # nothing for this user, proving this doesn't silently create real state.
    assert org_repository.list_orgs_for_user(db_session, user_email="brand-new@example.com") == []


def test_new_admin_email_user_still_bootstraps_into_default_as_owner(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "staff-admin@example.com")
    user_service.get_or_create_user(db_session, "staff-admin@example.com")

    membership = org_service.resolve_login_membership(
        db_session, user_email="staff-admin@example.com"
    )

    assert membership.org_id == DEFAULT_ORG_ID
    assert membership.role.value == "owner"
    # This one IS real, persisted state — matches the pre-T-210 behavior exactly.
    assert org_repository.get_membership(
        db_session, org_id=DEFAULT_ORG_ID, user_email="staff-admin@example.com"
    ) is not None


def test_existing_membership_is_returned_unchanged(db_session: Session) -> None:
    user_service.get_or_create_user(db_session, "already-a-member@example.com")
    org_service.get_or_create_dev_membership(
        db_session,
        org_id=DEFAULT_ORG_ID,
        user_email="already-a-member@example.com",
        role_override=None,
    )

    membership = org_service.resolve_login_membership(
        db_session, user_email="already-a-member@example.com"
    )

    assert membership.org_id == DEFAULT_ORG_ID


def test_dev_login_org_id_null_reaches_the_same_pending_path(client: TestClient) -> None:
    response = client.post(
        "/auth/dev-login", json={"email": "pending-via-dev-login@example.com", "org_id": None}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["org_id"] == PENDING_ORG_ID
    assert body["role"] == "viewer"


def test_dev_login_omitted_org_id_still_defaults_to_default_org(client: TestClient) -> None:
    """Backward-compat guard: existing callers (e2e/api.ts's loginAs, every other
    dev-login call site) never send org_id: null explicitly — they either omit it or
    pass a real org id — and must keep landing in DEFAULT_ORG_ID exactly as before."""
    response = client.post("/auth/dev-login", json={"email": "omitted-org-id@example.com"})

    assert response.status_code == 200, response.text
    assert response.json()["org_id"] == DEFAULT_ORG_ID


def test_pending_session_onboarding_status_is_all_false_not_a_crash(client: TestClient) -> None:
    """The whole fix hinges on this: OnboardingGate.tsx must see a clean
    "nothing done yet" status for a session scoped to the "pending" sentinel, with
    no special-casing anywhere in the frontend."""
    login = client.post(
        "/auth/dev-login", json={"email": "pending-status-check@example.com", "org_id": None}
    )
    token = login.json()["token"]

    response = client.get(
        "/orgs/pending/onboarding-status", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["tos_accepted"] is False
    assert body["has_provider_key"] is False
    assert body["has_repo"] is False


def test_pending_session_can_complete_the_real_create_org_flow(client: TestClient) -> None:
    """End-to-end proof that CreateOrgStep.tsx's exact real API calls (POST /orgs
    then POST /auth/switch-org) work unmodified starting from a pending session —
    neither endpoint reads the caller's *current* org_id, only their proven email."""
    login = client.post(
        "/auth/dev-login", json={"email": "pending-to-real-org@example.com", "org_id": None}
    )
    pending_token = login.json()["token"]
    assert login.json()["org_id"] == PENDING_ORG_ID

    tos = client.get("/tos", headers={"Authorization": f"Bearer {pending_token}"}).json()

    create = client.post(
        "/orgs",
        json={"name": "Pending To Real Org", "tos_version": tos["version"]},
        headers={"Authorization": f"Bearer {pending_token}"},
    )
    assert create.status_code == 201, create.text
    new_org_id = create.json()["id"]
    assert new_org_id != PENDING_ORG_ID

    switch = client.post(
        "/auth/switch-org",
        json={"org_id": new_org_id},
        headers={"Authorization": f"Bearer {pending_token}"},
    )
    assert switch.status_code == 200, switch.text
    real_token = switch.json()["token"]
    assert switch.json()["org_id"] == new_org_id
    assert switch.json()["role"] == "owner"

    status = client.get(
        f"/orgs/{new_org_id}/onboarding-status", headers={"Authorization": f"Bearer {real_token}"}
    ).json()
    assert status["tos_accepted"] is True
    assert status["has_provider_key"] is False
    assert status["has_repo"] is False
