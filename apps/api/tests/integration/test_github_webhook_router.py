"""T-203 (SPEC-203 AC3/AC4): native GitHub App webhook delivery — signature
verification (AC3) and installation.deleted force-blocking in-flight tickets,
synchronously, within the same request (AC4)."""

import hashlib
import hmac
import json
import logging

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from api.tenancy import DEFAULT_ORG_ID

from .conftest import _mock_installation_token, _service_auth


def _sign(body: bytes, *, secret: str) -> str:
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _post_github_webhook(
    client: TestClient,
    payload: dict[str, object],
    *,
    event: str,
    secret: str | None = None,
) -> httpx.Response:
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-GitHub-Event": event}
    if secret is not None:
        headers["X-Hub-Signature-256"] = _sign(body, secret=secret)
    return client.post("/webhooks/github", content=body, headers=headers)


def test_forged_signature_is_rejected_and_logged(
    client: TestClient, webhook_secret_configured: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING):
        response = _post_github_webhook(
            client,
            {"action": "deleted", "installation": {"id": 1}},
            event="installation",
            secret="not-the-real-secret",
        )

    assert response.status_code == 401
    assert any("invalid signature" in record.message for record in caplog.records)


def test_missing_signature_header_is_rejected(
    client: TestClient, webhook_secret_configured: str
) -> None:
    response = _post_github_webhook(
        client, {"action": "deleted", "installation": {"id": 1}}, event="installation"
    )
    assert response.status_code == 401


def test_valid_signature_is_accepted(
    client: TestClient, webhook_secret_configured: str
) -> None:
    response = _post_github_webhook(
        client,
        {"action": "created", "installation": {"id": 1}},
        event="installation",
        secret=webhook_secret_configured,
    )
    assert response.status_code == 200


@respx.mock
def test_installation_deleted_blocks_in_flight_tickets_synchronously(
    client: TestClient, github_app_configured: None, webhook_secret_configured: str
) -> None:
    _mock_installation_token(installation_id=999)
    respx.post("https://api.github.com/repos/acme/template/generate").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 900,
                "full_name": "acme/uninstall-me",
                "clone_url": "https://github.com/acme/uninstall-me.git",
                "default_branch": "main",
            },
        )
    )
    repo = client.post(
        f"/orgs/{DEFAULT_ORG_ID}/repos/provisioned",
        json={"name": "uninstall-me"},
        headers=_service_auth(),
    ).json()

    ticket = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "in-flight ticket",
            "created_by": "system",
            "budget_usd": 100.0,
            "acceptance_criteria": [{"id": "AC-1", "description": "d", "verification": "v"}],
            "repo_id": repo["id"],
        },
        headers=_service_auth(),
    ).json()
    ticket_id = ticket["id"]
    assert ticket["state"] == "ready"
    client.post(
        f"/tickets/{ticket_id}/transition",
        json={"to_state": "in_progress", "actor": "system"},
    )

    response = _post_github_webhook(
        client,
        {"action": "deleted", "installation": {"id": 999}},
        event="installation",
        secret=webhook_secret_configured,
    )
    assert response.status_code == 200, response.text

    updated = client.get(f"/tickets/{ticket_id}", headers=_service_auth()).json()
    assert updated["state"] == "blocked"

    events = updated["recent_events"]
    block_event = next(e for e in events if e["payload"].get("to") == "blocked")
    assert block_event["actor"] == "system:github"
    assert "uninstalled" in block_event["payload"]["reason"]

    repos = client.get(
        f"/orgs/{DEFAULT_ORG_ID}/repos", headers=_service_auth()
    ).json()["items"]
    updated_repo = next(r for r in repos if r["id"] == repo["id"])
    assert updated_repo["status"] == "disconnected"


@respx.mock
def test_installation_deleted_is_a_noop_for_an_unknown_installation(
    client: TestClient, webhook_secret_configured: str
) -> None:
    response = _post_github_webhook(
        client,
        {"action": "deleted", "installation": {"id": 424242}},
        event="installation",
        secret=webhook_secret_configured,
    )
    assert response.status_code == 200
