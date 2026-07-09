"""Onboarding-gate enforcement: FIXTURE_REPO_PROVISIONING lets `has_repo` become true
without a live GitHub App registered (none exists in this environment — see
docs/06-tech-stack.md's repeated disclosure since T-203). Deliberately does not use
the `github_app_configured` fixture (test_repo_router.py) — these tests exercise the
path where no real App is configured at all.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from api.services import github_repo_service
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


def test_flag_off_still_raises_when_no_app_is_configured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression guard: the new flag must default to off, so provisioning without a
    real GitHub App still 503s — proving the fixture path didn't become the default."""
    monkeypatch.delenv("FIXTURE_REPO_PROVISIONING", raising=False)
    org_id, owner_token = _owner_org_token(
        client, "owner-fixture-off@example.com", "Fixture-off org"
    )

    response = client.post(
        f"/orgs/{org_id}/repos/provisioned",
        json={"name": "should-fail"},
        headers=_auth(owner_token),
    )
    assert response.status_code == 503


def test_flag_on_provisions_a_clearly_marked_fixture_repo(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AUTH_DEV_MODE is already 'true' for the whole test session (conftest.py) —
    setting FIXTURE_REPO_PROVISIONING=true is the only thing this test needs to flip."""
    monkeypatch.setenv("FIXTURE_REPO_PROVISIONING", "true")
    org_id, owner_token = _owner_org_token(client, "owner-fixture-on@example.com", "Fixture-on org")

    response = client.post(
        f"/orgs/{org_id}/repos/provisioned", json={"name": "my-repo"}, headers=_auth(owner_token)
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "provisioned"
    assert body["github_full_name"] == "fixture/my-repo"
    assert body["status"] == "active"

    listed = client.get(f"/orgs/{org_id}/repos", headers=_auth(owner_token)).json()["items"]
    assert len(listed) == 1
    assert listed[0]["github_full_name"] == "fixture/my-repo"


def test_flag_on_without_auth_dev_mode_still_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: FIXTURE_REPO_PROVISIONING alone (without AUTH_DEV_MODE=true)
    must never be enough to bypass the real GitHub App requirement."""
    monkeypatch.setenv("FIXTURE_REPO_PROVISIONING", "true")
    monkeypatch.setenv("AUTH_DEV_MODE", "false")
    monkeypatch.delenv("GITHUB_APP_TEMPLATE_REPO", raising=False)
    monkeypatch.delenv("GITHUB_APP_PLATFORM_INSTALLATION_ID", raising=False)

    with pytest.raises(github_repo_service.GitHubAppNotConfigured):
        github_repo_service.provision_repo(
            None,  # type: ignore[arg-type]  # never reached — raises before touching the session
            None,  # type: ignore[arg-type]  # never reached — raises before touching vault
            org_id="does-not-matter",
            name="does-not-matter",
            actor="human:test@example.com",
        )
