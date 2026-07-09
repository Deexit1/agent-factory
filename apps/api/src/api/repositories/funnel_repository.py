from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import (
    MergeQueueEntry,
    MergeQueueStatus,
    Org,
    ProviderKey,
    Repo,
    Ticket,
    TicketType,
    TosAcceptance,
)


def list_orgs_created_between(session: Session, *, start: datetime, end: datetime) -> list[str]:
    """T-206 (SPEC-206 AC4): the funnel dashboard's one legitimate cross-tenant sweep —
    a platform-wide cohort report visits every org created in the window, so there is
    no single org_id to scope this query by. Same shape as
    billing_repository.list_all_org_ids."""
    return list(
        session.execute(
            select(Org.id)
            .where(Org.created_at >= start, Org.created_at < end)
            .order_by(Org.id)
        )
        .scalars()
        .all()
    )


def org_ids_with_tos_acceptance(session: Session, org_ids: list[str]) -> set[str]:
    return set(
        session.execute(
            select(TosAcceptance.org_id.distinct()).where(TosAcceptance.org_id.in_(org_ids))
        )
        .scalars()
        .all()
    )


def org_ids_with_provider_key(session: Session, org_ids: list[str]) -> set[str]:
    return set(
        session.execute(
            select(ProviderKey.org_id.distinct()).where(ProviderKey.org_id.in_(org_ids))
        )
        .scalars()
        .all()
    )


def org_ids_with_repo(session: Session, org_ids: list[str]) -> set[str]:
    return set(
        session.execute(select(Repo.org_id.distinct()).where(Repo.org_id.in_(org_ids)))
        .scalars()
        .all()
    )


def org_ids_with_idea_ticket(session: Session, org_ids: list[str]) -> set[str]:
    return set(
        session.execute(
            select(Ticket.org_id.distinct()).where(
                Ticket.org_id.in_(org_ids), Ticket.type == TicketType.IDEA
            )
        )
        .scalars()
        .all()
    )


def org_ids_with_merged_pr(session: Session, org_ids: list[str]) -> set[str]:
    return set(
        session.execute(
            select(MergeQueueEntry.org_id.distinct()).where(
                MergeQueueEntry.org_id.in_(org_ids),
                MergeQueueEntry.status == MergeQueueStatus.MERGED,
            )
        )
        .scalars()
        .all()
    )


__all__ = [
    "list_orgs_created_between",
    "org_ids_with_tos_acceptance",
    "org_ids_with_provider_key",
    "org_ids_with_repo",
    "org_ids_with_idea_ticket",
    "org_ids_with_merged_pr",
]
