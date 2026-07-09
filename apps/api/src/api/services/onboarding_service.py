"""T-206 (SPEC-206): org-wizard progress (derived live from existing rows — no
wizard-progress table to drift out of sync) and the cross-org funnel cohort dashboard
(a derived aggregate, not an event log — see funnel_repository.py)."""

from datetime import datetime

from sqlalchemy.orm import Session

from api.db.models import TicketType
from api.repositories import (
    funnel_repository,
    provider_key_repository,
    repo_repository,
    tos_repository,
)
from api.repositories import ticket_repository as repo

FUNNEL_STAGES = (
    "signup",
    "tos_accepted",
    "key_added",
    "repo_connected",
    "first_idea_created",
    "first_pr_merged",
)


def get_onboarding_status(session: Session, *, org_id: str) -> dict[str, bool]:
    has_idea, _total = repo.list_tickets(
        session,
        org_id=org_id,
        state=None,
        ticket_type=TicketType.IDEA,
        assignee_agent=None,
        limit=1,
        offset=0,
    )
    return {
        "tos_accepted": tos_repository.get_latest_tos_acceptance(session, org_id=org_id)
        is not None,
        "has_provider_key": len(provider_key_repository.list_provider_keys(session, org_id=org_id))
        > 0,
        "has_repo": len(repo_repository.list_repos(session, org_id=org_id)) > 0,
        "has_idea_ticket": len(has_idea) > 0,
    }


def compute_funnel_cohort(
    session: Session, *, cohort_start: datetime, cohort_end: datetime
) -> list[tuple[str, int]]:
    """AC4: exactly reproducible from seeded fixture rows — each stage's count is
    "how many of the cohort's orgs have reached this stage, ever", not bounded by the
    cohort window itself (only signup/org-creation is)."""
    org_ids = funnel_repository.list_orgs_created_between(
        session, start=cohort_start, end=cohort_end
    )
    if not org_ids:
        return [(stage, 0) for stage in FUNNEL_STAGES]

    tos_ids = funnel_repository.org_ids_with_tos_acceptance(session, org_ids)
    key_ids = funnel_repository.org_ids_with_provider_key(session, org_ids)
    repo_ids = funnel_repository.org_ids_with_repo(session, org_ids)
    idea_ids = funnel_repository.org_ids_with_idea_ticket(session, org_ids)
    merged_ids = funnel_repository.org_ids_with_merged_pr(session, org_ids)

    return [
        ("signup", len(org_ids)),
        ("tos_accepted", len(tos_ids)),
        ("key_added", len(key_ids)),
        ("repo_connected", len(repo_ids)),
        ("first_idea_created", len(idea_ids)),
        ("first_pr_merged", len(merged_ids)),
    ]


__all__ = ["FUNNEL_STAGES", "get_onboarding_status", "compute_funnel_cohort"]
