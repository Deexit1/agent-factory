"""T-206: GET /orgs/{id}/onboarding-status is derived live from existing rows (no
wizard-progress table) — each flag flips true as the real underlying row appears."""

import pytest
from fastapi.testclient import TestClient

from api.services import provider_key_service
from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth
from .test_tickets_api import _dev_login


@pytest.fixture(autouse=True)
def _no_real_provider_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_key_service, "validate_key", lambda **kwargs: None)


def test_onboarding_status_flips_true_as_wizard_steps_complete(
    client: TestClient, vault_addr: str
) -> None:
    owner_token = _dev_login(client, "onboarding-status@example.com", "owner")
    org = client.post(
        "/orgs",
        json={"name": "Status Org", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(owner_token),
    ).json()
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]

    status = client.get(
        f"/orgs/{org_id}/onboarding-status", headers=_auth(owner_org_token)
    ).json()
    assert status == {
        "org_id": org_id,
        "tos_accepted": True,  # bundled into org creation
        "has_provider_key": False,
        "has_repo": False,
        "has_idea_ticket": False,
    }

    add_key = client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "sk-ant-fake-key-1234"},
        headers=_auth(owner_org_token),
    )
    assert add_key.status_code == 201, add_key.text
    status = client.get(
        f"/orgs/{org_id}/onboarding-status", headers=_auth(owner_org_token)
    ).json()
    assert status["has_provider_key"] is True
    assert status["has_repo"] is False

    idea = client.post(
        "/tickets",
        json={
            "type": "idea",
            "title": "First idea",
            "budget_usd": 25.0,
            "created_by": "human:owner",
        },
        headers=_auth(owner_org_token),
    )
    assert idea.status_code == 201, idea.text

    status = client.get(
        f"/orgs/{org_id}/onboarding-status", headers=_auth(owner_org_token)
    ).json()
    assert status["has_idea_ticket"] is True


def test_onboarding_status_is_cross_tenant_404(client: TestClient) -> None:
    owner_token = _dev_login(client, "onboarding-status2@example.com", "owner")
    org = client.post(
        "/orgs",
        json={"name": "Status Org 2", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(owner_token),
    ).json()

    other_owner_token = _dev_login(client, "onboarding-status3@example.com", "owner")
    other_org = client.post(
        "/orgs",
        json={"name": "Status Org 3", "tos_version": CURRENT_TOS_VERSION},
        headers=_auth(other_owner_token),
    ).json()
    other_org_token = client.post(
        "/auth/switch-org", json={"org_id": other_org["id"]}, headers=_auth(other_owner_token)
    ).json()["token"]

    response = client.get(f"/orgs/{org['id']}/onboarding-status", headers=_auth(other_org_token))
    assert response.status_code == 404
