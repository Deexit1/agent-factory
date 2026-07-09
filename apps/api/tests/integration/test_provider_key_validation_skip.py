"""Onboarding-gate enforcement: PROVIDER_KEY_VALIDATION_SKIP lets `has_provider_key`
become true without a live Anthropic/OpenAI account (none exists in this environment).

Deliberately does NOT use test_provider_key_router.py's `_no_real_provider_validation`
autouse fixture (that monkeypatches `validate_key` itself to a no-op unconditionally,
which would hide the very env-flag behavior this file exists to prove) — this file
monkeypatches the underlying SDK classes instead, one level lower, so `validate_key`'s
own flag-checking logic actually runs.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.services import provider_key_service
from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth
from .test_tickets_api import _dev_login


def _create_org_as(client: TestClient, token: str, name: str) -> dict[str, Any]:
    response = client.post(
        "/orgs", json={"name": name, "tos_version": CURRENT_TOS_VERSION}, headers=_auth(token)
    )
    assert response.status_code == 201, response.text
    return response.json()  # type: ignore[no-any-return]


def _owner_org_token(client: TestClient, email: str, org_name: str) -> tuple[str, str]:
    owner_token = _dev_login(client, email, "owner")
    org = _create_org_as(client, owner_token, org_name)
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    return org_id, owner_org_token


def test_flag_off_still_calls_the_real_sdk_and_rejects_a_bogus_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: the new flag must default to off (real validation), so a
    clearly-fake key is still rejected with 422 when PROVIDER_KEY_VALIDATION_SKIP is
    unset — proving the bypass didn't accidentally become the default behavior."""
    monkeypatch.delenv("PROVIDER_KEY_VALIDATION_SKIP", raising=False)
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.side_effect = RuntimeError("not a live key")
    monkeypatch.setattr(provider_key_service, "anthropic", fake_anthropic)

    org_id, owner_token = _owner_org_token(client, "owner-skip-off@example.com", "Skip-off org")
    response = client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "sk-ant-definitely-not-real"},
        headers=_auth(owner_token),
    )
    assert response.status_code == 422, response.text
    fake_anthropic.Anthropic.assert_called_once()


def test_flag_on_skips_the_real_sdk_call_entirely(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, vault_addr: str
) -> None:
    """AUTH_DEV_MODE is already 'true' for the whole test session (conftest.py) —
    setting PROVIDER_KEY_VALIDATION_SKIP=true is the only thing this test needs to
    flip to exercise the bypass."""
    monkeypatch.setenv("PROVIDER_KEY_VALIDATION_SKIP", "true")
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.side_effect = RuntimeError("should never be called")
    monkeypatch.setattr(provider_key_service, "anthropic", fake_anthropic)

    org_id, owner_token = _owner_org_token(client, "owner-skip-on@example.com", "Skip-on org")
    response = client.post(
        f"/orgs/{org_id}/provider-keys",
        json={"provider": "anthropic", "api_key": "not-a-real-key-but-that-is-fine"},
        headers=_auth(owner_token),
    )
    assert response.status_code == 201, response.text
    fake_anthropic.Anthropic.assert_not_called()


def test_flag_on_without_auth_dev_mode_still_validates_for_real(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: PROVIDER_KEY_VALIDATION_SKIP alone (without AUTH_DEV_MODE=true)
    must never be enough to bypass validation — the same 'never in a deployed
    environment' boundary AUTH_DEV_MODE itself relies on."""
    monkeypatch.setenv("PROVIDER_KEY_VALIDATION_SKIP", "true")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    fake_anthropic = MagicMock()
    fake_anthropic.Anthropic.side_effect = RuntimeError("not a live key")
    monkeypatch.setattr(provider_key_service, "anthropic", fake_anthropic)

    with pytest.raises(provider_key_service.InvalidProviderKey):
        provider_key_service.validate_key(provider="anthropic", api_key="sk-ant-nope")
    fake_anthropic.Anthropic.assert_called_once()
