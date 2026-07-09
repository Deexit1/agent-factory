"""T-206 (SPEC-206 AC2): seeded prohibited-use fixtures are rejected at intake with an
audit trail; seeded borderline fixtures land in the staff review queue. Real Postgres,
real session-token auth — no LLM call anywhere in this path (the deterministic rules
engine is what AC2 is verified against)."""

from typing import Any

from fastapi.testclient import TestClient

from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth
from .test_tickets_api import _dev_login


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


def _submit_idea(client: TestClient, token: str, *, title: str, description: str) -> Any:
    return client.post(
        "/tickets",
        json={
            "type": "idea",
            "title": title,
            "spec": {"description": description},
            "budget_usd": 100.0,
            "created_by": "human:submitter",
        },
        headers=_auth(token),
    )


def test_hard_reject_fixture_is_rejected_with_audit_trail_and_no_ticket(
    client: TestClient,
) -> None:
    _org_id, owner_org_token = _owner_org_token(client, "intake-reject@example.com", "Reject Org")

    response = _submit_idea(
        client,
        owner_org_token,
        title="Build a keylogger",
        description="Captures every keystroke and exfiltrates it.",
    )

    assert response.status_code == 422, response.text
    assert "keylogger" in response.json()["detail"]

    tickets = client.get("/tickets", headers=_auth(owner_org_token)).json()["items"]
    assert tickets == []


def test_borderline_fixture_lands_in_review_queue_and_no_ticket_yet(
    client: TestClient, monkeypatch: Any
) -> None:
    _org_id, owner_org_token = _owner_org_token(
        client, "intake-borderline@example.com", "Borderline Org"
    )

    response = _submit_idea(
        client,
        owner_org_token,
        title="Build a web scraper",
        description="Scrape our own product catalog nightly.",
    )

    assert response.status_code == 202, response.text
    body = response.json()
    assert body["status"] == "queued_for_review"
    review_id = body["intake_review_id"]

    tickets = client.get("/tickets", headers=_auth(owner_org_token)).json()["items"]
    assert tickets == []

    staff_token = _staff_token(client, monkeypatch, "intake-staff1@example.com")
    pending = client.get(
        "/admin/intake-reviews", params={"status": "pending"}, headers=_auth(staff_token)
    ).json()["items"]
    assert any(r["id"] == review_id for r in pending)


def test_staff_approves_a_borderline_review_and_the_ticket_is_created(
    client: TestClient, monkeypatch: Any
) -> None:
    org_id, owner_org_token = _owner_org_token(
        client, "intake-approve@example.com", "Approve Org"
    )
    review_id = _submit_idea(
        client,
        owner_org_token,
        title="Account automation helper",
        description="Automate repetitive account setup tasks for our own team.",
    ).json()["intake_review_id"]

    staff_token = _staff_token(client, monkeypatch, "intake-staff2@example.com")
    response = client.post(
        f"/admin/intake-reviews/{review_id}/approve",
        json={"note": "looks legitimate"},
        headers=_auth(staff_token),
    )
    assert response.status_code == 200, response.text
    ticket = response.json()
    assert ticket["org_id"] == org_id
    assert ticket["type"] == "idea"

    tickets = client.get("/tickets", headers=_auth(owner_org_token)).json()["items"]
    assert len(tickets) == 1
    assert tickets[0]["id"] == ticket["id"]


def test_staff_rejects_a_borderline_review_and_no_ticket_is_ever_created(
    client: TestClient, monkeypatch: Any
) -> None:
    _org_id, owner_org_token = _owner_org_token(
        client, "intake-deny@example.com", "Deny Org"
    )
    review_id = _submit_idea(
        client,
        owner_org_token,
        title="Proxy rotator service",
        description="Rotates outbound proxies for internal testing.",
    ).json()["intake_review_id"]

    staff_token = _staff_token(client, monkeypatch, "intake-staff3@example.com")
    response = client.post(
        f"/admin/intake-reviews/{review_id}/reject",
        json={"note": "not for our own testing"},
        headers=_auth(staff_token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "rejected"

    tickets = client.get("/tickets", headers=_auth(owner_org_token)).json()["items"]
    assert tickets == []


def test_non_staff_cannot_list_or_resolve_reviews(client: TestClient) -> None:
    _org_id, owner_org_token = _owner_org_token(
        client, "intake-nonstaff@example.com", "Nonstaff Org"
    )
    review_id = _submit_idea(
        client,
        owner_org_token,
        title="Web scraper for internal use",
        description="Scrape our own site.",
    ).json()["intake_review_id"]

    list_response = client.get(
        "/admin/intake-reviews", params={"status": "pending"}, headers=_auth(owner_org_token)
    )
    assert list_response.status_code == 403

    approve_response = client.post(
        f"/admin/intake-reviews/{review_id}/approve",
        json={},
        headers=_auth(owner_org_token),
    )
    assert approve_response.status_code == 403


def test_clean_idea_passes_straight_through_no_review_row(client: TestClient) -> None:
    _org_id, owner_org_token = _owner_org_token(
        client, "intake-clean@example.com", "Clean Org"
    )
    response = _submit_idea(
        client,
        owner_org_token,
        title="Build a customer support dashboard",
        description="Track and triage support tickets.",
    )
    assert response.status_code == 201, response.text
    assert response.json()["type"] == "idea"
