"""T-203 (SPEC-203): real github_app_client.py HTTP calls, fault-injected at the HTTP
boundary via respx — zero live GitHub App exists in this environment (same T-202
packages/llm_router/test_fallover.py precedent)."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from api.github_app_client import (
    GitHubApiError,
    TokenExpiryTooLong,
    create_repo_from_template,
    get_branch_protection,
    get_repo_archive_url,
    list_installation_repositories,
    mint_installation_token,
    transfer_repo_ownership,
)

_TOKEN_URL = "https://api.github.com/app/installations/42/access_tokens"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@respx.mock
def test_mint_installation_token_returns_a_real_token_and_expiry() -> None:
    expires_at = datetime.now(UTC) + timedelta(minutes=55)
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(
            201,
            json={
                "token": "ghs_fake_installation_token",
                "expires_at": _iso(expires_at),
                "permissions": {"contents": "write"},
                "repositories": [{"id": 111}],
            },
        )
    )

    result = mint_installation_token(
        app_jwt="fake.app.jwt", installation_id=42, repository_ids=[111]
    )

    assert result.token == "ghs_fake_installation_token"
    assert result.repository_ids == [111]


@respx.mock
def test_mint_installation_token_rejects_an_expiry_beyond_one_hour() -> None:
    """AC2's "introspection test": a token minted with a >1h expiry is refused before
    it's ever handed to a caller — proves the ceiling is enforced, not just documented."""
    expires_at = datetime.now(UTC) + timedelta(hours=2)
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(
            201,
            json={
                "token": "ghs_fake_too_long_lived",
                "expires_at": _iso(expires_at),
                "permissions": {"contents": "write"},
                "repositories": [{"id": 111}],
            },
        )
    )

    with pytest.raises(TokenExpiryTooLong):
        mint_installation_token(app_jwt="fake.app.jwt", installation_id=42, repository_ids=[111])


@respx.mock
def test_mint_installation_token_raises_on_a_github_error() -> None:
    respx.post(_TOKEN_URL).mock(
        return_value=httpx.Response(404, json={"message": "Not Found"})
    )

    with pytest.raises(GitHubApiError):
        mint_installation_token(app_jwt="fake.app.jwt", installation_id=42, repository_ids=[111])


@respx.mock
def test_get_branch_protection_returns_not_protected_on_404() -> None:
    respx.get(
        "https://api.github.com/repos/acme/widgets/branches/main/protection"
    ).mock(return_value=httpx.Response(404, json={"message": "Branch not protected"}))

    result = get_branch_protection(token="ghs_fake", owner="acme", repo="widgets", branch="main")

    assert result.exists is False
    assert result.blocks_direct_push is False


@respx.mock
def test_get_branch_protection_detects_required_reviews() -> None:
    respx.get(
        "https://api.github.com/repos/acme/widgets/branches/main/protection"
    ).mock(
        return_value=httpx.Response(
            200,
            json={
                "required_pull_request_reviews": {"required_approving_review_count": 1},
                "restrictions": None,
            },
        )
    )

    result = get_branch_protection(token="ghs_fake", owner="acme", repo="widgets", branch="main")

    assert result.exists is True
    assert result.blocks_direct_push is True


@respx.mock
def test_list_installation_repositories_paginates() -> None:
    first_page = [
        {"id": i, "full_name": f"acme/r{i}", "clone_url": "u", "default_branch": "main"}
        for i in range(100)
    ]
    second_page = [
        {"id": 999, "full_name": "acme/last", "clone_url": "u", "default_branch": "main"}
    ]
    route = respx.get("https://api.github.com/installation/repositories")
    route.side_effect = [
        httpx.Response(200, json={"repositories": first_page}),
        httpx.Response(200, json={"repositories": second_page}),
    ]

    repos = list_installation_repositories(token="ghs_fake")

    assert len(repos) == 101
    assert repos[-1].full_name == "acme/last"


@respx.mock
def test_create_repo_from_template() -> None:
    respx.post("https://api.github.com/repos/acme/template/generate").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 555,
                "full_name": "acme/new-repo",
                "clone_url": "https://github.com/acme/new-repo.git",
                "default_branch": "main",
            },
        )
    )

    repo = create_repo_from_template(
        token="ghs_fake",
        template_owner="acme",
        template_repo="template",
        owner="acme",
        name="new-repo",
    )

    assert repo.full_name == "acme/new-repo"


@respx.mock
def test_transfer_repo_ownership_raises_on_failure() -> None:
    respx.post("https://api.github.com/repos/acme/widgets/transfer").mock(
        return_value=httpx.Response(422, json={"message": "cannot transfer"})
    )

    with pytest.raises(GitHubApiError):
        transfer_repo_ownership(
            token="ghs_fake", owner="acme", repo="widgets", new_owner="customer-org"
        )


@respx.mock
def test_get_repo_archive_url_returns_the_redirect_location() -> None:
    respx.get("https://api.github.com/repos/acme/widgets/tarball/main").mock(
        return_value=httpx.Response(
            302, headers={"location": "https://codeload.github.com/acme/widgets/tar.gz/main"}
        )
    )

    url = get_repo_archive_url(token="ghs_fake", owner="acme", repo="widgets", ref="main")

    assert url == "https://codeload.github.com/acme/widgets/tar.gz/main"
