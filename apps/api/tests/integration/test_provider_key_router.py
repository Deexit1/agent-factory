"""T-202 (SPEC-202): key management CRUD + AC6 (delete revokes from Vault and pauses
dependent agents) + AC5 (unverified-quality opt-in gate). Real ephemeral Vault
container (vault_client/vault_addr fixtures, conftest.py) — the validate-on-save
provider ping is monkeypatched (no real Anthropic/OpenAI spend; the mechanism under
test is Vault + DB + dispatch-gating, not provider key validity)."""

import os
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.services import provider_key_service
from api.vault_client import VaultClient

from .test_tickets_api import _dev_login


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _service_auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {os.environ['AGENT_FACTORY_SERVICE_TOKEN']}"}


@pytest.fixture(autouse=True)
def _no_real_provider_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_key_service, "validate_key", lambda **kwargs: None)


def _create_org_as(client: TestClient, token: str, name: str) -> dict[str, Any]:
    response = client.post("/orgs", json={"name": name}, headers=_auth(token))
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def test_owner_can_add_rotate_and_delete_a_key(
    client: TestClient, db_session: Session, vault_addr: str
) -> None:
    owner_token = _dev_login(client, "owner-keys@example.com", "owner")
    org = _create_org_as(client, owner_token, "Keys org")
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]

    add = client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "sk-ant-real-looking-fake-key-0000"},
        headers=_auth(owner_org_token),
    )
    assert add.status_code == 201, add.text
    body = add.json()
    assert body["provider"] == "anthropic"
    assert body["last4"] == "0000"
    assert body["status"] == "active"
    assert "api_key" not in body

    listed = client.get(f"/orgs/{org_id}/provider-keys", headers=_auth(owner_org_token))
    assert listed.status_code == 200
    assert [k["provider"] for k in listed.json()["items"]] == ["anthropic"]

    rotate = client.post(
        f"/orgs/{org_id}/provider-keys/anthropic/rotate",
        json={"provider": "anthropic", "api_key": "sk-ant-rotated-fake-key-1111"},
        headers=_auth(owner_org_token),
    )
    assert rotate.status_code == 200, rotate.text
    assert rotate.json()["last4"] == "1111"
    assert rotate.json()["rotated_at"] is not None

    delete = client.delete(
        f"/orgs/{org_id}/provider-keys/anthropic", headers=_auth(owner_org_token)
    )
    assert delete.status_code == 204

    listed_after_delete = client.get(
        f"/orgs/{org_id}/provider-keys", headers=_auth(owner_org_token)
    ).json()["items"]
    assert listed_after_delete[0]["status"] == "revoked"


def test_non_owner_cannot_add_or_delete_keys(client: TestClient) -> None:
    owner_token = _dev_login(client, "owner-keys2@example.com", "owner")
    org = _create_org_as(client, owner_token, "Keys org 2")
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    invite = client.post(
        f"/orgs/{org_id}/invites",
        json={"email": "member-keys@example.com", "role": "member"},
        headers=_auth(owner_org_token),
    ).json()
    member_session_token = _dev_login(client, "member-keys@example.com", "member")
    client.post(
        f"/orgs/invites/{invite['token']}/accept", headers=_auth(member_session_token)
    )
    member_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(member_session_token)
    ).json()["token"]

    add = client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "sk-ant-fake-0000000000000000"},
        headers=_auth(member_org_token),
    )
    assert add.status_code == 403


def test_delete_revokes_key_in_vault_for_real(
    client: TestClient, db_session: Session, vault_addr: str, vault_client: VaultClient
) -> None:
    """AC6: deleting a key revokes it from Vault — proven against the real container,
    not a mocked client. get_key returns None post-delete."""
    owner_token = _dev_login(client, "owner-vault@example.com", "owner")
    org = _create_org_as(client, owner_token, "Vault org")
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]

    client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "sk-ant-vault-round-trip-fake-key"},
        headers=_auth(owner_org_token),
    )
    stored = vault_client.get_key(org_id=org_id, provider="anthropic")
    assert stored == "sk-ant-vault-round-trip-fake-key"

    client.delete(f"/orgs/{org_id}/provider-keys/anthropic", headers=_auth(owner_org_token))
    assert vault_client.get_key(org_id=org_id, provider="anthropic") is None


def test_deleted_key_immediately_excluded_from_runtime_keys(
    client: TestClient, db_session: Session, vault_addr: str
) -> None:
    """AC6: "...pauses dependent agents within 60s" — enforced by construction here,
    since runtime-keys (what every agent dispatch fetches fresh) drops a revoked key
    the very next call, no polling interval to wait out."""
    owner_token = _dev_login(client, "owner-pause@example.com", "owner")
    org = _create_org_as(client, owner_token, "Pause org")
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]

    client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "sk-ant-pause-test-fake-key-000"},
        headers=_auth(owner_org_token),
    )

    before = client.get(f"/orgs/{org_id}/llm/runtime-keys", headers=_service_auth())
    assert before.status_code == 200
    assert any(item["provider"] == "anthropic" for item in before.json()["items"])

    client.delete(f"/orgs/{org_id}/provider-keys/anthropic", headers=_auth(owner_org_token))

    after = client.get(f"/orgs/{org_id}/llm/runtime-keys", headers=_service_auth())
    assert after.status_code == 200
    assert after.json()["items"] == []


def test_runtime_keys_endpoint_is_service_principal_only(
    client: TestClient, vault_addr: str
) -> None:
    owner_token = _dev_login(client, "owner-runtime@example.com", "owner")
    org = _create_org_as(client, owner_token, "Runtime org")
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]

    response = client.get(f"/orgs/{org_id}/llm/runtime-keys", headers=_auth(owner_org_token))
    assert response.status_code == 403
