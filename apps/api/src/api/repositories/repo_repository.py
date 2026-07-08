from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import Repo, RepoCIMode, RepoMode, RepoStatus


def create_repo(
    session: Session,
    *,
    org_id: str,
    mode: RepoMode,
    github_installation_id: int,
    github_repo_id: int | None = None,
    github_full_name: str | None = None,
    clone_url: str | None = None,
    default_branch: str | None = None,
    ci_mode: RepoCIMode = RepoCIMode.PLATFORM_RUNNERS,
    protected_branch_rules_verified: bool = False,
    created_by: str,
) -> Repo:
    repo = Repo(
        org_id=org_id,
        mode=mode,
        github_installation_id=github_installation_id,
        github_repo_id=github_repo_id,
        github_full_name=github_full_name,
        clone_url=clone_url,
        default_branch=default_branch,
        ci_mode=ci_mode,
        protected_branch_rules_verified=protected_branch_rules_verified,
        protected_branch_rules_verified_at=datetime.now(UTC),
        status=RepoStatus.ACTIVE,
        created_at=datetime.now(UTC),
        created_by=created_by,
    )
    session.add(repo)
    session.flush()
    return repo


def get_repo(session: Session, repo_id: int, *, org_id: str) -> Repo | None:
    return session.execute(
        select(Repo).where(Repo.id == repo_id, Repo.org_id == org_id)
    ).scalar_one_or_none()


def list_repos(session: Session, *, org_id: str) -> list[Repo]:
    return list(
        session.execute(select(Repo).where(Repo.org_id == org_id).order_by(Repo.id))
        .scalars()
        .all()
    )


def list_by_installation(session: Session, *, installation_id: int) -> list[Repo]:
    # Deliberately no org_id param: a GitHub webhook only ever gives us an
    # installation_id, never an org_id — add to check_tenant_scope_gate.py's
    # _ALLOWLIST, mirroring org_repository.list_orgs_for_user's precedent.
    return list(
        session.execute(
            select(Repo).where(Repo.github_installation_id == installation_id)
        )
        .scalars()
        .all()
    )


def mark_branch_protection_verified(
    session: Session, repo_id: int, *, org_id: str, verified: bool
) -> Repo | None:
    repo = get_repo(session, repo_id, org_id=org_id)
    if repo is None:
        return None
    repo.protected_branch_rules_verified = verified
    repo.protected_branch_rules_verified_at = datetime.now(UTC)
    session.flush()
    return repo


def mark_disconnected(session: Session, repo_id: int, *, org_id: str, reason: str) -> Repo | None:
    repo = get_repo(session, repo_id, org_id=org_id)
    if repo is None:
        return None
    repo.status = RepoStatus.DISCONNECTED
    repo.disconnected_at = datetime.now(UTC)
    repo.disconnected_reason = reason
    session.flush()
    return repo


def mark_exported(session: Session, repo_id: int, *, org_id: str, reason: str) -> Repo | None:
    repo = get_repo(session, repo_id, org_id=org_id)
    if repo is None:
        return None
    repo.status = RepoStatus.EXPORTED
    repo.disconnected_at = datetime.now(UTC)
    repo.disconnected_reason = reason
    session.flush()
    return repo
