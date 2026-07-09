from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.db.models import IntakeReview


def create_intake_review(
    session: Session,
    *,
    org_id: str,
    ticket_type: str,
    title: str,
    parent_id: str | None,
    spec: dict[str, object] | None,
    acceptance_criteria: list[dict[str, object]],
    budget_usd: float | None,
    repo_id: int | None,
    submitted_by: str,
    submitted_at: datetime,
    status: str,
    screening_reason: str | None,
    decided_by: str | None = None,
    decided_at: datetime | None = None,
) -> IntakeReview:
    review = IntakeReview(
        org_id=org_id,
        ticket_type=ticket_type,
        title=title,
        parent_id=parent_id,
        spec=spec,
        acceptance_criteria=acceptance_criteria,
        budget_usd=budget_usd,
        repo_id=repo_id,
        submitted_by=submitted_by,
        submitted_at=submitted_at,
        status=status,
        screening_reason=screening_reason,
        decided_by=decided_by,
        decided_at=decided_at,
    )
    session.add(review)
    session.flush()
    return review


def get_intake_review(session: Session, review_id: int, *, org_id: str) -> IntakeReview | None:
    review = session.get(IntakeReview, review_id)
    if review is None or review.org_id != org_id:
        return None
    return review


def get_intake_review_any_org(session: Session, review_id: int) -> IntakeReview | None:
    """Staff-only lookup: reviewers act across orgs, so there is no single org_id to
    scope this by — the caller (a platform-staff-gated route) is the enforcement point,
    same pattern as admin.py's impersonate route resolving an org by id without
    comparing it to the staff caller's own org_id."""
    return session.get(IntakeReview, review_id)


def list_reviews(session: Session, *, org_id: str | None, status: str | None) -> list[IntakeReview]:
    filters = []
    if org_id is not None:
        filters.append(IntakeReview.org_id == org_id)
    if status is not None:
        filters.append(IntakeReview.status == status)
    return list(
        session.execute(
            select(IntakeReview).where(*filters).order_by(IntakeReview.submitted_at)
        )
        .scalars()
        .all()
    )


def resolve_review(
    session: Session,
    review: IntakeReview,
    *,
    status: str,
    decided_by: str,
    decided_at: datetime,
    decision_note: str | None,
) -> IntakeReview:
    review.status = status
    review.decided_by = decided_by
    review.decided_at = decided_at
    review.decision_note = decision_note
    session.flush()
    return review


__all__ = [
    "create_intake_review",
    "get_intake_review",
    "get_intake_review_any_org",
    "list_reviews",
    "resolve_review",
]
