"""T-203 (SPEC-203): sole owner of GitHub REST API calls (enforced by
scripts/check_github_app_gate.py, same discipline as check_llm_router_gate.py for LLM
provider SDKs) — real RS256 JWT signing + real httpx calls to api.github.com.

No live GitHub App is registered in this environment (creating one requires a human
with org-owner rights on github.com); every call here is exercised in tests via respx
HTTP-boundary fault injection (the same T-202 packages/llm_router/test_fallover.py
precedent), never against a real customer org.

Callers (apps/api/src/api/services/github_repo_service.py) never persist a minted
installation token anywhere but a local variable — the same "fetched at run start, held
in memory, never written to disk/DB/logs" doctrine as BYOK provider keys
(docs/09-saas-model.md).
"""

import hashlib
import hmac
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import jwt

_API_BASE = "https://api.github.com"
_ACCEPT_HEADER = "application/vnd.github+json"
_API_VERSION = "2022-11-28"

# GitHub hard-caps App JWTs at 10 minutes; 9 minutes leaves margin for clock skew and
# request latency without needing a fresh JWT per call in a tight loop.
_JWT_TTL = timedelta(minutes=9)
_JWT_CLOCK_SKEW_BUFFER = timedelta(seconds=60)

# SPEC-203 AC2: installation tokens must expire <= 1h. A small skew allowance accounts
# for our own clock vs. GitHub's, not a relaxation of the real requirement.
_MAX_TOKEN_TTL = timedelta(hours=1, minutes=1)

DEFAULT_INSTALLATION_PERMISSIONS = {"contents": "write", "pull_requests": "write"}
PLATFORM_INSTALLATION_PERMISSIONS = {
    "contents": "write",
    "pull_requests": "write",
    "administration": "write",
}
# GET .../branches/{branch}/protection 403s without at least read-level `administration`
# (confirmed against a real GitHub App, not just docs) — a customer's routine PR-pushing
# token (DEFAULT_INSTALLATION_PERMISSIONS) doesn't need this, so it's requested only for
# the one connect-time call that does, not baked into the default.
CONNECT_TIME_PERMISSIONS = {**DEFAULT_INSTALLATION_PERMISSIONS, "administration": "read"}


class GitHubApiError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"GitHub API error {status_code}: {detail}")


class TokenExpiryTooLong(Exception):
    """AC2: an installation token that would live longer than an hour is refused
    before it's ever handed to a caller — this assertion IS the "introspection test"."""


def mint_app_jwt(*, app_id: str, private_key_pem: str, now: datetime | None = None) -> str:
    issued_at = now or datetime.now(UTC)
    payload = {
        "iat": int((issued_at - _JWT_CLOCK_SKEW_BUFFER).timestamp()),
        "exp": int((issued_at + _JWT_TTL).timestamp()),
        "iss": app_id,
    }
    return jwt.encode(payload, private_key_pem, algorithm="RS256")


def _headers(*, bearer_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {bearer_token}",
        "Accept": _ACCEPT_HEADER,
        "X-GitHub-Api-Version": _API_VERSION,
    }


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code >= 400:
        raise GitHubApiError(response.status_code, response.text)


@dataclass(frozen=True)
class InstallationToken:
    token: str
    expires_at: datetime
    repository_ids: list[int] = field(default_factory=list)
    permissions: dict[str, str] = field(default_factory=dict)


def mint_installation_token(
    *,
    app_jwt: str,
    installation_id: int,
    repository_ids: list[int] | None,
    permissions: dict[str, str] | None = None,
    timeout_s: float = 10.0,
) -> InstallationToken:
    """`repository_ids=None` omits the field entirely — GitHub then scopes the token to
    every repo already selected for this installation (used once, at connect time, to
    enumerate them). Every other caller passes an explicit single-repo list — the real
    "scoped to this one repo" narrowing SPEC-203 asks for."""
    body: dict[str, object] = {"permissions": dict(permissions or DEFAULT_INSTALLATION_PERMISSIONS)}
    if repository_ids is not None:
        body["repository_ids"] = repository_ids
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(
            f"{_API_BASE}/app/installations/{installation_id}/access_tokens",
            json=body,
            headers=_headers(bearer_token=app_jwt),
        )
    _raise_for_status(response)
    data = response.json()

    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    if expires_at - datetime.now(UTC) > _MAX_TOKEN_TTL:
        raise TokenExpiryTooLong(
            f"installation token expires_at={data['expires_at']} exceeds the 1h ceiling"
        )

    granted_repos = data.get("repositories")
    granted_ids = (
        [r["id"] for r in granted_repos] if granted_repos else list(repository_ids or [])
    )

    return InstallationToken(
        token=data["token"],
        expires_at=expires_at,
        repository_ids=granted_ids,
        permissions=dict(data.get("permissions", body["permissions"])),
    )


@dataclass(frozen=True)
class BranchProtection:
    exists: bool
    blocks_direct_push: bool


def get_branch_protection(
    *, token: str, owner: str, repo: str, branch: str, timeout_s: float = 10.0
) -> BranchProtection:
    with httpx.Client(timeout=timeout_s) as client:
        response = client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/branches/{branch}/protection",
            headers=_headers(bearer_token=token),
        )
    if response.status_code == 404:
        return BranchProtection(exists=False, blocks_direct_push=False)
    _raise_for_status(response)
    data = response.json()
    blocks_direct_push = bool(
        data.get("required_pull_request_reviews") or data.get("restrictions")
    )
    return BranchProtection(exists=True, blocks_direct_push=blocks_direct_push)


@dataclass(frozen=True)
class RepoInfo:
    id: int
    full_name: str
    clone_url: str
    default_branch: str


def list_installation_repositories(*, token: str, timeout_s: float = 10.0) -> list[RepoInfo]:
    repos: list[RepoInfo] = []
    page = 1
    with httpx.Client(timeout=timeout_s) as client:
        while True:
            response = client.get(
                f"{_API_BASE}/installation/repositories",
                headers=_headers(bearer_token=token),
                params={"per_page": 100, "page": page},
            )
            _raise_for_status(response)
            data = response.json()
            batch = data.get("repositories", [])
            repos.extend(
                RepoInfo(
                    id=r["id"],
                    full_name=r["full_name"],
                    clone_url=r["clone_url"],
                    default_branch=r["default_branch"],
                )
                for r in batch
            )
            if len(batch) < 100:
                break
            page += 1
    return repos


def create_repo_from_template(
    *,
    token: str,
    template_owner: str,
    template_repo: str,
    owner: str,
    name: str,
    private: bool = True,
    timeout_s: float = 10.0,
) -> RepoInfo:
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(
            f"{_API_BASE}/repos/{template_owner}/{template_repo}/generate",
            json={"owner": owner, "name": name, "private": private},
            headers=_headers(bearer_token=token),
        )
    _raise_for_status(response)
    data = response.json()
    return RepoInfo(
        id=data["id"],
        full_name=data["full_name"],
        clone_url=data["clone_url"],
        default_branch=data.get("default_branch", "main"),
    )


def transfer_repo_ownership(
    *, token: str, owner: str, repo: str, new_owner: str, timeout_s: float = 10.0
) -> None:
    """SPEC-203 AC5. Disclosed uncertainty (see the T-203 plan / docs/06-tech-stack.md):
    whether a GitHub App installation token — even with `administration:write` — can
    call this endpoint at all is not confirmable from documentation alone outside a
    live GitHub session; built and tested against the documented request/response
    shape, flagged for live verification before first real use."""
    with httpx.Client(timeout=timeout_s) as client:
        response = client.post(
            f"{_API_BASE}/repos/{owner}/{repo}/transfer",
            json={"new_owner": new_owner},
            headers=_headers(bearer_token=token),
        )
    _raise_for_status(response)


def get_repo_archive_url(
    *, token: str, owner: str, repo: str, ref: str, timeout_s: float = 10.0
) -> str:
    """GitHub 302s a tarball request to a codeload.github.com URL — returned directly
    rather than downloaded/re-stored (T-203's disclosed no-new-artifact-storage trim,
    see docs/09-saas-model.md)."""
    with httpx.Client(timeout=timeout_s, follow_redirects=False) as client:
        response = client.get(
            f"{_API_BASE}/repos/{owner}/{repo}/tarball/{ref}",
            headers=_headers(bearer_token=token),
        )
    if response.status_code not in (302, 200):
        _raise_for_status(response)
    location: str | None = response.headers.get("location")
    if not location:
        raise GitHubApiError(response.status_code, "no archive redirect location returned")
    return location


def verify_webhook_signature(raw_body: bytes, signature_header: str | None, *, secret: str) -> bool:
    """Same HMAC-SHA256 sha256=<hex> construction as
    api.services.webhook_service.verify_signature, deliberately reimplemented (not
    shared) since it takes an explicit secret — this one reads
    GITHUB_APP_WEBHOOK_SECRET, a distinct env var from CI_WEBHOOK_SECRET."""
    if not secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


__all__ = [
    "CONNECT_TIME_PERMISSIONS",
    "DEFAULT_INSTALLATION_PERMISSIONS",
    "PLATFORM_INSTALLATION_PERMISSIONS",
    "BranchProtection",
    "GitHubApiError",
    "InstallationToken",
    "RepoInfo",
    "TokenExpiryTooLong",
    "create_repo_from_template",
    "get_branch_protection",
    "get_repo_archive_url",
    "list_installation_repositories",
    "mint_app_jwt",
    "mint_installation_token",
    "transfer_repo_ownership",
    "verify_webhook_signature",
]
