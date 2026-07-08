import pytest
from fastapi.testclient import TestClient

from .test_tickets_api import _create_task, _dev_login


def test_health_needs_no_auth(client: TestClient) -> None:
    response = client.get("/health", headers={"Authorization": ""})
    assert response.status_code == 200


def test_unauthenticated_ticket_access_returns_401(client: TestClient) -> None:
    no_auth = client.get("/tickets", headers={"Authorization": ""})
    assert no_auth.status_code == 401

    ticket = _create_task(client)
    no_auth_get = client.get(f"/tickets/{ticket['id']}", headers={"Authorization": ""})
    assert no_auth_get.status_code == 401


def test_garbage_bearer_token_returns_401(client: TestClient) -> None:
    response = client.get("/tickets", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


def test_dev_login_mints_a_working_session_token(client: TestClient) -> None:
    token = _dev_login(client, "dana@example.com", "viewer")

    me = client.get("/tickets", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_auth_me_reflects_the_bearer_token(client: TestClient) -> None:
    token = _dev_login(client, "erin@example.com", "owner")

    response = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert body["actor"] == "human:erin@example.com"
    assert body["role"] == "owner"


def test_dev_login_404_when_auth_dev_mode_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AUTH_DEV_MODE", "false")

    response = client.post("/auth/dev-login", json={"email": "x@example.com"})

    assert response.status_code == 404


def test_login_and_callback_501_when_oidc_not_configured(client: TestClient) -> None:
    assert client.get("/auth/login", follow_redirects=False).status_code == 501
    assert client.get("/auth/callback", follow_redirects=False).status_code == 501
