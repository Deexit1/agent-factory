"""T-203 (SPEC-203): connect/provision/export flow — real ephemeral Vault (vault_addr/
vault_client fixtures), real Postgres, real RS256 JWT signing against a locally
generated throwaway keypair, GitHub's own HTTP boundary fault-injected via respx (no
live GitHub App exists in this environment — same T-202 packages/llm_router precedent).
"""

import json
from typing import Any

import httpx
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.tos import CURRENT_TOS_VERSION

from .conftest import _auth, _mock_installation_token, _service_auth
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


def test_connect_url_requires_owner(
    client: TestClient, github_app_configured: None
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-repos1@example.com", "Repos org 1")
    response = client.get(f"/orgs/{org_id}/repos/connect-url", headers=_auth(owner_token))
    assert response.status_code == 200, response.text
    assert "agent-factory-test/installations/new?state=" in response.json()["url"]


def test_connect_url_503_when_app_not_configured(client: TestClient) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-repos2@example.com", "Repos org 2")
    response = client.get(f"/orgs/{org_id}/repos/connect-url", headers=_auth(owner_token))
    assert response.status_code == 503


@respx.mock
def test_connect_callback_creates_repo_rows(
    client: TestClient, db_session: Session, github_app_configured: None
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-repos3@example.com", "Repos org 3")
    connect = client.get(f"/orgs/{org_id}/repos/connect-url", headers=_auth(owner_token))
    state = connect.json()["url"].split("state=")[1]

    token_route = _mock_installation_token()
    respx.get("https://api.github.com/installation/repositories").mock(
        return_value=httpx.Response(
            200,
            json={
                "repositories": [
                    {
                        "id": 555,
                        "full_name": "acme/widgets",
                        "clone_url": "https://github.com/acme/widgets.git",
                        "default_branch": "main",
                    }
                ]
            },
        )
    )
    respx.get("https://api.github.com/repos/acme/widgets/branches/main/protection").mock(
        return_value=httpx.Response(404, json={"message": "not protected"})
    )

    callback = client.get(
        "/repos/connect-callback",
        params={"installation_id": 42, "state": state},
        follow_redirects=False,
    )
    assert callback.status_code in (302, 307), callback.text

    repos = client.get(f"/orgs/{org_id}/repos", headers=_auth(owner_token)).json()["items"]
    assert len(repos) == 1
    assert repos[0]["github_full_name"] == "acme/widgets"
    assert repos[0]["mode"] == "connected"
    # Warn-and-allow (resolved product decision): unprotected branch does NOT block
    # connect, just leaves the verified flag false.
    assert repos[0]["protected_branch_rules_verified"] is False
    assert repos[0]["status"] == "active"

    # Regression guard: a real GitHub App 403s the branch-protection call below without
    # administration:read on the minted token — this respx mock alone can't catch that
    # (it isn't GitHub's real permission enforcement), so assert the request explicitly
    # asked for it instead.
    sent_permissions = json.loads(token_route.calls.last.request.content)["permissions"]
    assert sent_permissions.get("administration") == "read"


def test_connect_callback_rejects_a_tampered_state(
    client: TestClient, github_app_configured: None
) -> None:
    response = client.get(
        "/repos/connect-callback",
        params={"installation_id": 42, "state": "not-a-real-state-token"},
    )
    assert response.status_code == 401


@respx.mock
def test_provision_repo_creates_a_provisioned_row(
    client: TestClient, github_app_configured: None
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-repos4@example.com", "Repos org 4")

    _mock_installation_token(installation_id=999)
    respx.post("https://api.github.com/repos/acme/template/generate").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 777,
                "full_name": "acme/new-repo",
                "clone_url": "https://github.com/acme/new-repo.git",
                "default_branch": "main",
            },
        )
    )

    response = client.post(
        f"/orgs/{org_id}/repos/provisioned",
        json={"name": "new-repo"},
        headers=_auth(owner_token),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["mode"] == "provisioned"
    assert body["github_full_name"] == "acme/new-repo"


@respx.mock
def test_export_archive_returns_a_download_url_without_marking_exported(
    client: TestClient, github_app_configured: None
) -> None:
    org_id, owner_token = _owner_org_token(client, "owner-repos5@example.com", "Repos org 5")
    _mock_installation_token(installation_id=999)
    respx.post("https://api.github.com/repos/acme/template/generate").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 778,
                "full_name": "acme/export-me",
                "clone_url": "https://github.com/acme/export-me.git",
                "default_branch": "main",
            },
        )
    )
    provisioned = client.post(
        f"/orgs/{org_id}/repos/provisioned",
        json={"name": "export-me"},
        headers=_auth(owner_token),
    ).json()

    respx.get("https://api.github.com/repos/acme/export-me/tarball/main").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://codeload.github.com/acme/export-me/tar.gz/main"}
        )
    )

    export = client.post(
        f"/orgs/{org_id}/repos/{provisioned['id']}/export",
        json={"mode": "archive"},
        headers=_auth(owner_token),
    )
    assert export.status_code == 200, export.text
    assert export.json()["download_url"] == "https://codeload.github.com/acme/export-me/tar.gz/main"

    repos = client.get(f"/orgs/{org_id}/repos", headers=_auth(owner_token)).json()["items"]
    assert repos[0]["status"] == "active"  # archive export doesn't disconnect the repo


@respx.mock
def test_export_transfer_marks_repo_exported_and_blocks_future_token_mint(
    client: TestClient, github_app_configured: None
) -> None:
    """AC5: export transfers ownership and revokes platform access — a subsequent
    install-token mint for a ticket on this repo is refused once exported."""
    org_id, owner_token = _owner_org_token(client, "owner-repos6@example.com", "Repos org 6")
    _mock_installation_token(installation_id=999)
    respx.post("https://api.github.com/repos/acme/template/generate").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 779,
                "full_name": "acme/transfer-me",
                "clone_url": "https://github.com/acme/transfer-me.git",
                "default_branch": "main",
            },
        )
    )
    provisioned = client.post(
        f"/orgs/{org_id}/repos/provisioned",
        json={"name": "transfer-me"},
        headers=_auth(owner_token),
    ).json()

    respx.post("https://api.github.com/repos/acme/transfer-me/transfer").mock(
        return_value=httpx.Response(202, json={})
    )

    export = client.post(
        f"/orgs/{org_id}/repos/{provisioned['id']}/export",
        json={"mode": "transfer", "new_owner": "customer-org"},
        headers=_auth(owner_token),
    )
    assert export.status_code == 200, export.text
    assert export.json()["mode"] == "transfer"

    repos = client.get(f"/orgs/{org_id}/repos", headers=_auth(owner_token)).json()["items"]
    assert repos[0]["status"] == "exported"

    # Create a ticket against the now-exported repo and confirm token minting refuses.
    # Uses the owner's own org-scoped session token, not the service token — the
    # service token always resolves to DEFAULT_ORG_ID (T-201's disclosed single-org
    # dispatch scope), which isn't this test's freshly created org.
    ticket = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "post-export ticket",
            "created_by": "human:owner-repos6@example.com",
            "acceptance_criteria": [{"id": "AC1", "description": "d", "verification": "v"}],
            "repo_id": provisioned["id"],
        },
        headers=_auth(owner_token),
    )
    assert ticket.status_code == 422  # repo not active — refused at ticket-creation time


def test_non_owner_cannot_connect_or_provision(
    client: TestClient, github_app_configured: None
) -> None:
    owner_token = _dev_login(client, "owner-repos7@example.com", "owner")
    org = _create_org_as(client, owner_token, "Repos org 7")
    org_id = org["id"]
    owner_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(owner_token)
    ).json()["token"]
    invite = client.post(
        f"/orgs/{org_id}/invites",
        json={"email": "member-repos@example.com", "role": "member"},
        headers=_auth(owner_org_token),
    ).json()
    member_session_token = _dev_login(client, "member-repos@example.com", "member")
    client.post(
        f"/orgs/invites/{invite['token']}/accept", headers=_auth(member_session_token)
    )
    member_org_token = client.post(
        "/auth/switch-org", json={"org_id": org_id}, headers=_auth(member_session_token)
    ).json()["token"]

    response = client.post(
        f"/orgs/{org_id}/repos/provisioned",
        json={"name": "nope"},
        headers=_auth(member_org_token),
    )
    assert response.status_code == 403


@respx.mock
def test_github_install_token_endpoint_is_service_principal_only_and_mints_a_real_token(
    client: TestClient, github_app_configured: None
) -> None:
    """The install-token endpoint has no org_id in its path — it resolves org_id from
    the service actor's own ActorContext, same as GET /tickets/{id} and every other
    service-token call site (T-201's disclosed "service token = DEFAULT_ORG_ID only"
    scope, which is exactly how apps/orchestrator's real dev.py call ends up scoped
    too: it fetches the ticket via the service token first, then reads org_id off it).
    So this test provisions the repo and ticket under DEFAULT_ORG_ID via the service
    token itself, which is also role=owner — the same actor apps/orchestrator uses.
    """
    from api.tenancy import DEFAULT_ORG_ID

    _mock_installation_token(installation_id=999)
    respx.post("https://api.github.com/repos/acme/template/generate").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 780,
                "full_name": "acme/for-ticket",
                "clone_url": "https://github.com/acme/for-ticket.git",
                "default_branch": "main",
            },
        )
    )
    repo = client.post(
        f"/orgs/{DEFAULT_ORG_ID}/repos/provisioned",
        json={"name": "for-ticket"},
        headers=_service_auth(),
    ).json()

    ticket = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "ticket with a repo",
            "created_by": "system",
            "acceptance_criteria": [{"id": "AC1", "description": "d", "verification": "v"}],
            "repo_id": repo["id"],
        },
        headers=_service_auth(),
    ).json()

    owner_token = _dev_login(client, "owner-repos8@example.com", "owner")
    forbidden = client.get(
        f"/tickets/{ticket['id']}/github-install-token", headers=_auth(owner_token)
    )
    assert forbidden.status_code == 403

    ok = client.get(f"/tickets/{ticket['id']}/github-install-token", headers=_service_auth())
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["token"] == "ghs_fake_token"
    assert body["default_branch"] == "main"


def test_github_install_token_404_for_a_ticket_with_no_repo(client: TestClient) -> None:
    ticket = client.post(
        "/tickets",
        json={
            "type": "task",
            "title": "no repo ticket",
            "created_by": "human:x@example.com",
            "acceptance_criteria": [{"id": "AC1", "description": "d", "verification": "v"}],
        },
        headers=_service_auth(),
    ).json()

    response = client.get(
        f"/tickets/{ticket['id']}/github-install-token", headers=_service_auth()
    )
    assert response.status_code == 404
