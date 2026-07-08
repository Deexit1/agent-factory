"""T-203 (SPEC-203 AC3/AC4): native GitHub App webhook handling — deliberately separate
from webhook_service.py, which stays scoped to the pre-existing custom /webhooks/ci-result
route (fired by this repo's own agent-pr-gate GitHub Actions workflow, not by GitHub's
native webhook delivery). Both now share webhook_service.apply_ci_result for the actual
CI-result transition logic, so there's one code path, not two independently-drifting ones.
"""

import logging
import os

from schemas.branches import ticket_id_from_branch
from sqlalchemy.orm import Session

from api.db.models import Ticket
from api.github_app_client import verify_webhook_signature as _verify_hmac
from api.repositories import repo_repository
from api.services import github_repo_service, webhook_service

logger = logging.getLogger(__name__)

GITHUB_SYSTEM_ACTOR = github_repo_service.GITHUB_SYSTEM_ACTOR


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    secret = os.environ.get("GITHUB_APP_WEBHOOK_SECRET", "")
    if not secret:
        # Dev/local convenience, same as webhook_service.verify_signature's rule — but
        # this route is genuinely internet-facing in a real deployment, so every skip
        # is logged, not silent.
        logger.warning(
            "GITHUB_APP_WEBHOOK_SECRET unset; skipping GitHub webhook signature "
            "verification (local/dev only)"
        )
        return True
    return _verify_hmac(raw_body, signature_header, secret=secret)


def handle_installation_deleted(session: Session, *, installation_id: int) -> list[Ticket]:
    """AC4: fully synchronous, same request/response as GitHub's webhook delivery — no
    polling, no background job, so "within 60s" holds by construction."""
    repos = repo_repository.list_by_installation(session, installation_id=installation_id)
    blocked: list[Ticket] = []
    for repo in repos:
        blocked.extend(
            github_repo_service.disconnect_repo(
                session,
                org_id=repo.org_id,
                repo_id=repo.id,
                reason=f"GitHub App uninstalled from {repo.github_full_name or repo.id}",
                actor=GITHUB_SYSTEM_ACTOR,
            )
        )
    return blocked


def handle_check_run_completed(
    session: Session,
    *,
    installation_id: int,
    repo_full_name: str,
    head_branch: str,
    conclusion: str,
) -> Ticket | None:
    ticket_id = ticket_id_from_branch(head_branch)
    if ticket_id is None:
        return None  # not one of ours (not an agent/* branch)

    repos = repo_repository.list_by_installation(session, installation_id=installation_id)
    matching_repo = next((r for r in repos if r.github_full_name == repo_full_name), None)
    if matching_repo is None:
        return None  # a repo we don't have a `repos` row for

    try:
        return webhook_service.apply_ci_result(
            session,
            ticket_id,
            org_id=matching_repo.org_id,
            conclusion="success" if conclusion == "success" else "failure",
            suite="github-check-run",
            raw_log="",
            actor=webhook_service.CI_ACTOR,
        )
    except webhook_service.TicketNotInQA:
        return None  # stale/duplicate delivery — ignore, matching the CI-result route


__all__ = [
    "GITHUB_SYSTEM_ACTOR",
    "handle_check_run_completed",
    "handle_installation_deleted",
    "verify_signature",
]
