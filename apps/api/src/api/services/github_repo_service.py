"""T-203 (SPEC-203): connect/provision/export/disconnect orchestration — combines
github_app_client.py's real HTTP calls with repo_repository.py's DB rows and
vault_client.py's platform-secret storage. Mirrors provider_key_service.py's shape.

No live GitHub App is registered in this environment; GITHUB_APP_ID etc. are unset in
local/CI by default (docs/06-tech-stack.md's implementation-status note) — calling any
function here without them configured raises GitHubAppNotConfigured rather than
silently no-op'ing.
"""

import os
from dataclasses import dataclass
from typing import Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from api import github_app_client
from api.auth import session_secret
from api.db.models import Repo, RepoCIMode, RepoMode, RepoStatus, Ticket, TicketState
from api.repositories import repo_repository as repo_repo
from api.repositories import ticket_repository
from api.services import ticket_service
from api.vault_client import VaultClient

GITHUB_SYSTEM_ACTOR = "system:github"

# SPEC-203's connect flow is a browser redirect (GitHub App "Setup URL" callback) — the
# `state` token doubles as this flow's CSRF protection, same purpose OIDC's `state`
# param serves in api/oidc.py, just signed+timed instead of session-stored.
_CONNECT_STATE_MAX_AGE_S = 600
_CONNECT_STATE_SALT = "github-connect-state"

_PRIVATE_KEY_SECRET_NAME = "github/app-private-key"


class GitHubRepoServiceError(Exception):
    pass


class GitHubAppNotConfigured(GitHubRepoServiceError):
    def __init__(self) -> None:
        super().__init__(
            "GitHub App not configured (GITHUB_APP_ID/private key/GITHUB_APP_SLUG) — "
            "see docs/06-tech-stack.md's implementation-status note"
        )


class InvalidConnectState(GitHubRepoServiceError):
    pass


class RepoNotFound(GitHubRepoServiceError):
    def __init__(self, repo_id: int) -> None:
        self.repo_id = repo_id
        super().__init__(f"repo {repo_id} not found")


class RepoNotActive(GitHubRepoServiceError):
    def __init__(self, repo_id: int) -> None:
        self.repo_id = repo_id
        super().__init__(f"repo {repo_id} is not active")


class TicketHasNoRepo(GitHubRepoServiceError):
    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"ticket {ticket_id} has no connected repo_id")


def _app_id() -> str:
    return os.environ.get("GITHUB_APP_ID", "")


def _app_slug() -> str:
    return os.environ.get("GITHUB_APP_SLUG", "")


def _template_repo() -> str:
    return os.environ.get("GITHUB_APP_TEMPLATE_REPO", "")


def _platform_installation_id() -> int:
    raw = os.environ.get("GITHUB_APP_PLATFORM_INSTALLATION_ID", "")
    return int(raw) if raw else 0


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(session_secret(), salt=_CONNECT_STATE_SALT)


def _mint_app_jwt(vault: VaultClient) -> str:
    app_id = _app_id()
    private_key = vault.get_platform_secret(name=_PRIVATE_KEY_SECRET_NAME)
    if not app_id or not private_key:
        raise GitHubAppNotConfigured()
    return github_app_client.mint_app_jwt(app_id=app_id, private_key_pem=private_key)


def build_connect_url(*, org_id: str, actor: str) -> tuple[str, str]:
    slug = _app_slug()
    if not slug:
        raise GitHubAppNotConfigured()
    state = _state_serializer().dumps({"org_id": org_id, "actor": actor})
    url = f"https://github.com/apps/{slug}/installations/new?state={state}"
    return url, state


def _decode_state(state: str) -> dict[str, str]:
    try:
        data: dict[str, str] = _state_serializer().loads(state, max_age=_CONNECT_STATE_MAX_AGE_S)
    except (BadSignature, SignatureExpired) as exc:
        raise InvalidConnectState(str(exc)) from exc
    return data


def handle_connect_callback(
    session: Session, vault: VaultClient, *, installation_id: int, state: str
) -> list[Repo]:
    """AC1: enumerate every repo selected for this installation, verify each one's
    default-branch protection at connect time, and register a `repos` row per repo.

    Resolved product decision: warn-and-allow — an unprotected default branch does NOT
    block the connect (protected_branch_rules_verified=False, persistent UI banner);
    our own code-level guard (git_ops.py's agent/*-only push refusal) holds regardless.
    """
    decoded = _decode_state(state)
    org_id = decoded["org_id"]
    actor = decoded["actor"]

    app_jwt = _mint_app_jwt(vault)
    # repository_ids=None: this installation's already-selected repos, all of them —
    # we don't know their ids yet, that's what list_installation_repositories is for.
    install_token = github_app_client.mint_installation_token(
        app_jwt=app_jwt, installation_id=installation_id, repository_ids=None
    )
    remote_repos = github_app_client.list_installation_repositories(token=install_token.token)

    created: list[Repo] = []
    for remote in remote_repos:
        protection = github_app_client.get_branch_protection(
            token=install_token.token,
            owner=remote.full_name.split("/")[0],
            repo=remote.full_name.split("/")[1],
            branch=remote.default_branch,
        )
        created.append(
            repo_repo.create_repo(
                session,
                org_id=org_id,
                mode=RepoMode.CONNECTED,
                github_installation_id=installation_id,
                github_repo_id=remote.id,
                github_full_name=remote.full_name,
                clone_url=remote.clone_url,
                default_branch=remote.default_branch,
                ci_mode=RepoCIMode.CUSTOMER_CI,
                protected_branch_rules_verified=protection.blocks_direct_push,
                created_by=actor,
            )
        )
    session.commit()
    return created


def _fixture_provisioning_enabled() -> bool:
    """Onboarding-gate enforcement needs `has_repo` to be reachable without a live
    GitHub App registered (none exists in this environment — see
    docs/06-tech-stack.md's repeated disclosure since T-203). Same precedent as
    AUTH_DEV_MODE/PROVIDER_KEY_VALIDATION_SKIP: explicit, default-off, and additionally
    requires AUTH_DEV_MODE=true. Never set both in production."""
    return (
        os.environ.get("FIXTURE_REPO_PROVISIONING", "").lower() == "true"
        and os.environ.get("AUTH_DEV_MODE", "").lower() == "true"
    )


def _provision_fixture_repo(session: Session, *, org_id: str, name: str, actor: str) -> Repo:
    """No real github.com round-trip — a `Repo` row standing in for a provisioned repo,
    clearly marked (`fixture/` prefix) so it can never be mistaken for a real one.
    `github_installation_id=0` is a sentinel: real installation ids are always positive."""
    repo = repo_repo.create_repo(
        session,
        org_id=org_id,
        mode=RepoMode.PROVISIONED,
        github_installation_id=0,
        github_repo_id=None,
        github_full_name=f"fixture/{name}",
        clone_url=f"https://example.invalid/fixture/{name}.git",
        default_branch="main",
        ci_mode=RepoCIMode.PLATFORM_RUNNERS,
        protected_branch_rules_verified=False,
        created_by=actor,
    )
    session.commit()
    return repo


def provision_repo(
    session: Session, vault: VaultClient, *, org_id: str, name: str, actor: str
) -> Repo:
    """Creates a repo under the platform's own org from GITHUB_APP_TEMPLATE_REPO, using
    the platform's OWN installation (never a customer's) — the only installation that
    ever requests PLATFORM_INSTALLATION_PERMISSIONS (adds administration:write, needed
    for export_repo(mode="transfer") later — architecture decision 5)."""
    template = _template_repo()
    installation_id = _platform_installation_id()
    if not template or not installation_id:
        if _fixture_provisioning_enabled():
            return _provision_fixture_repo(session, org_id=org_id, name=name, actor=actor)
        raise GitHubAppNotConfigured()

    app_jwt = _mint_app_jwt(vault)
    install_token = github_app_client.mint_installation_token(
        app_jwt=app_jwt,
        installation_id=installation_id,
        repository_ids=None,
        permissions=github_app_client.PLATFORM_INSTALLATION_PERMISSIONS,
    )
    template_owner, template_name = template.split("/", 1)
    remote = github_app_client.create_repo_from_template(
        token=install_token.token,
        template_owner=template_owner,
        template_repo=template_name,
        owner=template_owner,
        name=name,
    )
    repo = repo_repo.create_repo(
        session,
        org_id=org_id,
        mode=RepoMode.PROVISIONED,
        github_installation_id=installation_id,
        github_repo_id=remote.id,
        github_full_name=remote.full_name,
        clone_url=remote.clone_url,
        default_branch=remote.default_branch,
        ci_mode=RepoCIMode.PLATFORM_RUNNERS,
        protected_branch_rules_verified=False,
        created_by=actor,
    )
    session.commit()
    return repo


@dataclass(frozen=True)
class ExportResult:
    mode: Literal["transfer", "archive"]
    download_url: str | None = None


def export_repo(
    session: Session,
    vault: VaultClient,
    *,
    org_id: str,
    repo_id: int,
    mode: Literal["transfer", "archive"],
    new_owner: str | None,
    actor: str,
) -> ExportResult:
    """AC5. `mode="archive"` (the recommended default — see docs/09-saas-model.md) has
    no live-verification gap. `mode="transfer"` is built and tested against GitHub's
    documented request/response shape but flagged as needing live-environment
    verification before first real use (architecture decision 5's disclosed
    uncertainty about whether an App installation token can call this endpoint)."""
    repo = repo_repo.get_repo(session, repo_id, org_id=org_id)
    if repo is None:
        raise RepoNotFound(repo_id)
    if repo.status is not RepoStatus.ACTIVE:
        raise RepoNotActive(repo_id)
    if repo.github_full_name is None:
        raise RepoNotActive(repo_id)

    app_jwt = _mint_app_jwt(vault)
    install_token = github_app_client.mint_installation_token(
        app_jwt=app_jwt,
        installation_id=repo.github_installation_id,
        repository_ids=[repo.github_repo_id] if repo.github_repo_id else None,
        permissions=github_app_client.PLATFORM_INSTALLATION_PERMISSIONS,
    )
    owner, name = repo.github_full_name.split("/", 1)

    if mode == "transfer":
        if not new_owner:
            raise GitHubRepoServiceError("mode='transfer' requires new_owner")
        github_app_client.transfer_repo_ownership(
            token=install_token.token, owner=owner, repo=name, new_owner=new_owner
        )
        repo_repo.mark_exported(
            session, repo_id, org_id=org_id, reason=f"transferred to {new_owner}"
        )
        session.commit()
        return ExportResult(mode="transfer")

    download_url = github_app_client.get_repo_archive_url(
        token=install_token.token, owner=owner, repo=name, ref=repo.default_branch or "main"
    )
    return ExportResult(mode="archive", download_url=download_url)


def disconnect_repo(
    session: Session, *, org_id: str, repo_id: int, reason: str, actor: str
) -> list[Ticket]:
    """Shared by BOTH the GitHub webhook's installation.deleted handler AND a manual
    DELETE route. AC4: force-transitions every in-flight ticket to BLOCKED,
    synchronously, in the same request — satisfies "within 60s" by construction, same
    design as BYOK's dispatch_gate (docs/09-saas-model.md)."""
    repo_repo.mark_disconnected(session, repo_id, org_id=org_id, reason=reason)
    session.commit()  # commit the disconnect even if there are zero in-flight tickets
    in_flight = ticket_repository.list_in_flight_by_repo(session, org_id=org_id, repo_id=repo_id)
    blocked: list[Ticket] = []
    for ticket in in_flight:
        updated = ticket_service.request_transition(
            session,
            ticket.id,
            TicketState.BLOCKED,
            actor,
            org_id=org_id,
            reason=reason,
        )
        blocked.append(updated)
    return blocked


def mint_install_token_for_ticket(
    session: Session, vault: VaultClient, *, ticket_id: str, org_id: str
) -> github_app_client.InstallationToken:
    """The orchestrator's ONLY way to get a usable GitHub token — never persisted
    anywhere but a local variable held for the duration of one dev-agent run (BYOK's
    "never persist" doctrine, docs/09-saas-model.md, extended verbatim here)."""
    ticket = ticket_service.get_ticket(session, ticket_id, org_id=org_id)
    if ticket.repo_id is None:
        raise TicketHasNoRepo(ticket_id)
    repo = repo_repo.get_repo(session, ticket.repo_id, org_id=org_id)
    if repo is None:
        raise RepoNotFound(ticket.repo_id)
    if repo.status is not RepoStatus.ACTIVE:
        raise RepoNotActive(ticket.repo_id)

    app_jwt = _mint_app_jwt(vault)
    permissions = (
        github_app_client.PLATFORM_INSTALLATION_PERMISSIONS
        if repo.mode is RepoMode.PROVISIONED
        else github_app_client.DEFAULT_INSTALLATION_PERMISSIONS
    )
    return github_app_client.mint_installation_token(
        app_jwt=app_jwt,
        installation_id=repo.github_installation_id,
        repository_ids=[repo.github_repo_id] if repo.github_repo_id else None,
        permissions=permissions,
    )


__all__ = [
    "GITHUB_SYSTEM_ACTOR",
    "ExportResult",
    "GitHubAppNotConfigured",
    "GitHubRepoServiceError",
    "InvalidConnectState",
    "RepoNotActive",
    "RepoNotFound",
    "TicketHasNoRepo",
    "build_connect_url",
    "disconnect_repo",
    "export_repo",
    "handle_connect_callback",
    "mint_install_token_for_ticket",
    "provision_repo",
]
