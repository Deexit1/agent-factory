import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from api.auth import SERVICE_ACTOR, ActorContext, get_actor_context
from api.contracts import (
    ConnectUrlOut,
    ExportRepoOut,
    ExportRepoRequest,
    GitHubInstallTokenOut,
    ProvisionRepoRequest,
    RepoListOut,
    RepoOut,
)
from api.db.session import get_db
from api.repositories import repo_repository
from api.services import github_repo_service, ticket_service
from api.vault_client import VaultClient, get_vault_client

router = APIRouter(
    prefix="/orgs/{org_id}/repos", tags=["repos"], dependencies=[Depends(get_actor_context)]
)

# No org_id in the path: GitHub App "Setup URL" callback constraint — org_id round-trips
# through the signed `state` token instead. Not behind get_actor_context (a GitHub
# browser redirect carries no bearer token) — same carve-out shape as /webhooks/*.
connect_callback_router = APIRouter(tags=["repos"])

# Service-token-only route mirroring provider_keys.py's runtime_router split.
install_token_router = APIRouter(
    prefix="/tickets/{ticket_id}", tags=["repos"], dependencies=[Depends(get_actor_context)]
)


def _actor_email(actor_context: ActorContext) -> str:
    return actor_context.actor.removeprefix("human:").removeprefix("staff:")


def _require_member(org_id: str, actor_context: ActorContext) -> None:
    # Cross-tenant reads 404, not 403 (T-201 AC1 convention).
    if actor_context.org_id != org_id:
        raise HTTPException(status_code=404, detail="org not found")


def _require_owner(org_id: str, actor_context: ActorContext) -> None:
    _require_member(org_id, actor_context)
    if actor_context.role != "owner":
        raise HTTPException(status_code=403, detail="only the org owner may manage repos")


@router.get("", response_model=RepoListOut)
def list_repos(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> RepoListOut:
    _require_member(org_id, actor_context)
    repos = repo_repository.list_repos(db, org_id=org_id)
    return RepoListOut(items=[RepoOut.model_validate(r) for r in repos])


@router.get("/connect-url", response_model=ConnectUrlOut)
def connect_url(
    org_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
) -> ConnectUrlOut:
    _require_owner(org_id, actor_context)
    try:
        url, _state = github_repo_service.build_connect_url(
            org_id=org_id, actor=actor_context.actor
        )
    except github_repo_service.GitHubAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ConnectUrlOut(url=url)


@router.post("/provisioned", response_model=RepoOut, status_code=201)
def provision_repo(
    org_id: str,
    request: ProvisionRepoRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> RepoOut:
    _require_owner(org_id, actor_context)
    try:
        repo = github_repo_service.provision_repo(
            db, vault, org_id=org_id, name=request.name, actor=_actor_email(actor_context)
        )
    except github_repo_service.GitHubAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RepoOut.model_validate(repo)


@router.post("/{repo_id}/export", response_model=ExportRepoOut)
def export_repo(
    org_id: str,
    repo_id: int,
    request: ExportRepoRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> ExportRepoOut:
    _require_owner(org_id, actor_context)
    try:
        result = github_repo_service.export_repo(
            db,
            vault,
            org_id=org_id,
            repo_id=repo_id,
            mode=request.mode,
            new_owner=request.new_owner,
            actor=_actor_email(actor_context),
        )
    except github_repo_service.RepoNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except github_repo_service.RepoNotActive as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except github_repo_service.GitHubAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ExportRepoOut(mode=result.mode, download_url=result.download_url)


@router.delete("/{repo_id}", response_model=RepoOut)
def disconnect_repo(
    org_id: str,
    repo_id: int,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> RepoOut:
    _require_owner(org_id, actor_context)
    existing = repo_repository.get_repo(db, repo_id, org_id=org_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="repo not found")
    github_repo_service.disconnect_repo(
        db,
        org_id=org_id,
        repo_id=repo_id,
        reason=f"manually disconnected by {_actor_email(actor_context)}",
        actor=f"human:{_actor_email(actor_context)}",
    )
    db.refresh(existing)
    return RepoOut.model_validate(existing)


@connect_callback_router.get("/repos/connect-callback")
def connect_callback(
    installation_id: int,
    state: str,
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> RedirectResponse:
    success_url = os.environ.get("WEB_REPOS_SUCCESS_URL", "http://localhost:5173")
    try:
        github_repo_service.handle_connect_callback(
            db, vault, installation_id=installation_id, state=state
        )
    except github_repo_service.InvalidConnectState as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except github_repo_service.GitHubAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RedirectResponse(url=f"{success_url}#connected=1")


@install_token_router.get("/github-install-token", response_model=GitHubInstallTokenOut)
def github_install_token(
    ticket_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
    vault: VaultClient = Depends(get_vault_client),
) -> GitHubInstallTokenOut:
    if actor_context.actor != SERVICE_ACTOR:
        raise HTTPException(
            status_code=403, detail="install-token resolution is service-principal only"
        )
    try:
        install_token = github_repo_service.mint_install_token_for_ticket(
            db, vault, ticket_id=ticket_id, org_id=actor_context.org_id
        )
    except github_repo_service.TicketHasNoRepo as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except github_repo_service.RepoNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except github_repo_service.RepoNotActive as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except github_repo_service.GitHubAppNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    ticket = ticket_service.get_ticket(db, ticket_id, org_id=actor_context.org_id)
    assert ticket.repo_id is not None
    repo = repo_repository.get_repo(db, ticket.repo_id, org_id=actor_context.org_id)
    assert repo is not None
    return GitHubInstallTokenOut(
        token=install_token.token,
        expires_at=install_token.expires_at,
        default_branch=repo.default_branch or "main",
    )


__all__ = ["router", "connect_callback_router", "install_token_router"]
