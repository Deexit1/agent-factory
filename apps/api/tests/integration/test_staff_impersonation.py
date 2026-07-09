"""T-201 AC5: platform-staff "view as org" impersonation — a short-lived, read-mostly
session, watermarked by the frontend (not exercised here) and audited on the backend
for every impersonation start plus every page view the frontend reports."""

import pytest
from fastapi.testclient import TestClient

from api.tenancy import DEFAULT_ORG_ID
from api.tos import CURRENT_TOS_VERSION

from .test_tenant_isolation import _create_task_as
from .test_tickets_api import _dev_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_non_staff_cannot_impersonate(client: TestClient) -> None:
    owner_token = _dev_login(client, "not-staff@example.com", "owner")

    response = client.post(
        f"/admin/orgs/{DEFAULT_ORG_ID}/impersonate", headers=_auth(owner_token)
    )

    assert response.status_code == 403


def test_platform_staff_can_impersonate_and_it_is_audited(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PLATFORM_STAFF_EMAILS", "staff@example.com")
    staff_token = _dev_login(client, "staff@example.com", "viewer")

    bob_token = _dev_login(client, "bob-impersonated@example.com", "owner")
    org_b = client.post(
        "/orgs",
        json={"name": "Impersonated org", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(bob_token),
    ).json()
    bob_org_b_token = client.post(
        "/auth/switch-org", json={"org_id": org_b["id"]}, headers=_auth(bob_token)
    ).json()["token"]
    task = _create_task_as(client, bob_org_b_token)

    impersonate = client.post(
        f"/admin/orgs/{org_b['id']}/impersonate", headers=_auth(staff_token)
    )
    assert impersonate.status_code == 200, impersonate.text
    body = impersonate.json()
    assert body["actor"] == "staff:staff@example.com"
    assert body["role"] == "viewer"
    assert body["org_id"] == org_b["id"]
    impersonation_token = body["token"]

    # Read access into the impersonated org works...
    read = client.get(f"/tickets/{task['id']}", headers=_auth(impersonation_token))
    assert read.status_code == 200

    # ...but an impersonation session is never treated as a human actor — it cannot
    # approve, even though its role is nominally "viewer" (who couldn't anyway) or
    # even if staff happened to be an owner elsewhere; is_human_actor() only matches
    # "human:" actors, and impersonation always mints "staff:".
    approve = client.post(
        f"/tickets/{task['id']}/approve",
        json={"gate": "budget", "decision": "approved"},
        headers=_auth(impersonation_token),
    )
    assert approve.status_code == 403

    page_view = client.post(
        "/admin/audit/page-view", json={"path": "/board"}, headers=_auth(impersonation_token)
    )
    assert page_view.status_code == 201

    # A non-impersonating session can't post page-view audits on behalf of anyone.
    rejected = client.post(
        "/admin/audit/page-view", json={"path": "/board"}, headers=_auth(bob_org_b_token)
    )
    assert rejected.status_code == 403
