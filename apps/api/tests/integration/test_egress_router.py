"""T-204 (SPEC-204 AC3): "org-specific egress addition works only after staff approval
and applies only to that org." Real Postgres (session_factory), real session-token
auth — no mocked HTTP boundary needed, this is pure DB + auth-gate logic."""

import pytest
from fastapi.testclient import TestClient

from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth, _service_auth
from .test_tickets_api import _dev_login


def _create_org_as(client: TestClient, token: str, name: str) -> dict[str, object]:
    response = client.post(
        "/orgs", json={"name": name, "tos_version": CURRENT_TOS_VERSION}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[return-value]


def _owner_org_token(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    owner_token = _dev_login(client, email, "owner")
    org = _create_org_as(client, owner_token, org_name)
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    return org_id, owner_org_token


def _staff_token_for_org(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, org_id: str
) -> str:
    monkeypatch.setenv("PLATFORM_STAFF_EMAILS", "staff-egress@example.com")
    staff_token = _dev_login(client, "staff-egress@example.com", "viewer")
    impersonate = client.post(
        f"/admin/orgs/{org_id}/impersonate", headers=_auth(staff_token)
    )
    assert impersonate.status_code == 200, impersonate.text
    return impersonate.json()["token"]  # type: ignore[no-any-return]


def test_owner_cannot_add_egress_rule_without_staff_approval(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-egress1@example.com", "Egress org 1")

    response = client.post(
        f"/orgs/{org_id}/egress-rules",
        json={"domain": "custom-registry.example.com"},
        headers=_auth(owner_token),
    )

    assert response.status_code == 403


def test_staff_can_add_and_remove_an_egress_rule(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-egress2@example.com", "Egress org 2")
    staff_token = _staff_token_for_org(client, monkeypatch, org_id)

    add = client.post(
        f"/orgs/{org_id}/egress-rules",
        json={"domain": "custom-registry.example.com"},
        headers=_auth(staff_token),
    )
    assert add.status_code == 201, add.text
    rule = add.json()
    assert rule["domain"] == "custom-registry.example.com"
    assert rule["approved_by"] == "staff-egress@example.com"

    listing = client.get(f"/orgs/{org_id}/egress-rules", headers=_auth(owner_token))
    assert listing.status_code == 200
    assert [r["domain"] for r in listing.json()["items"]] == ["custom-registry.example.com"]

    remove = client.delete(
        f"/orgs/{org_id}/egress-rules/{rule['id']}", headers=_auth(staff_token)
    )
    assert remove.status_code == 204

    listing_after = client.get(f"/orgs/{org_id}/egress-rules", headers=_auth(owner_token))
    assert listing_after.json()["items"] == []


def test_egress_addition_only_applies_to_its_own_org(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_a, _owner_a = _owner_org_token(client, "owner-egress3a@example.com", "Egress org 3a")
    org_b, owner_b = _owner_org_token(client, "owner-egress3b@example.com", "Egress org 3b")
    staff_token_a = _staff_token_for_org(client, monkeypatch, org_a)

    add = client.post(
        f"/orgs/{org_a}/egress-rules",
        json={"domain": "only-for-org-a.example.com"},
        headers=_auth(staff_token_a),
    )
    assert add.status_code == 201, add.text

    listing_b = client.get(f"/orgs/{org_b}/egress-rules", headers=_auth(owner_b))
    assert listing_b.json()["items"] == []


def test_effective_domains_is_service_principal_only(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-egress4@example.com", "Egress org 4")

    forbidden = client.get(
        f"/orgs/{org_id}/egress-rules/effective", headers=_auth(owner_token)
    )
    assert forbidden.status_code == 403

    allowed = client.get(f"/orgs/{org_id}/egress-rules/effective", headers=_service_auth())
    assert allowed.status_code == 200
    assert "api.anthropic.com" in allowed.json()["domains"]


def test_effective_domains_merges_base_and_org_rules(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    org_id, _owner_token = _owner_org_token(client, "owner-egress5@example.com", "Egress org 5")
    staff_token = _staff_token_for_org(client, monkeypatch, org_id)

    client.post(
        f"/orgs/{org_id}/egress-rules",
        json={"domain": "custom-registry.example.com"},
        headers=_auth(staff_token),
    )

    effective = client.get(
        f"/orgs/{org_id}/egress-rules/effective", headers=_service_auth()
    ).json()["domains"]
    assert "api.anthropic.com" in effective
    assert "custom-registry.example.com" in effective
