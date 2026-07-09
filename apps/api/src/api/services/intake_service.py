"""T-206 (SPEC-206 AC2): gates `ticket_service.create_ticket` for raw user-submitted
idea/task content. Deliberately does NOT import ticket_service (the reverse dependency
— ticket_service imports this module to screen submissions) — `approve_review` creates
the ticket via `ticket_repository.create_ticket` directly, bypassing the screening
wrapper entirely so an already-approved submission is never re-screened.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.contracts import CreateTicketRequest
from api.db.models import IntakeReview, IntakeReviewStatus, Ticket, TicketState, TicketType
from api.repositories import intake_repository
from api.repositories import ticket_repository as repo
from api.services import intake_screening_service

INTAKE_SCREENER_ACTOR = "system:intake-screener"

_SCREENED_TYPES = {TicketType.IDEA, TicketType.TASK}


class IntakeRejected(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class IntakeQueuedForReview(Exception):
    def __init__(self, review_id: int, reason: str) -> None:
        self.review_id = review_id
        self.reason = reason
        super().__init__(reason)


class IntakeReviewNotFound(Exception):
    def __init__(self, review_id: int) -> None:
        self.review_id = review_id
        super().__init__(f"intake review {review_id} not found")


class IntakeReviewNotPending(Exception):
    def __init__(self, review_id: int) -> None:
        self.review_id = review_id
        super().__init__(f"intake review {review_id} is not pending")


def requires_screening(ticket_type: TicketType) -> bool:
    # Epics are planner-generated decompositions of an already-approved idea, not raw
    # user input — never screened.
    return ticket_type in _SCREENED_TYPES


def screen_submission(session: Session, request: CreateTicketRequest, *, org_id: str) -> None:
    """Raises IntakeRejected/IntakeQueuedForReview if the content doesn't pass; returns
    None silently on a clean pass (no intake_reviews row at all for the common case, so
    that table stays a signal — rejections and real review decisions only)."""
    if not requires_screening(request.type):
        return

    verdict = intake_screening_service.screen_content(request.title, request.spec)
    if verdict.decision == "pass":
        return

    now = datetime.now(UTC)
    is_reject = verdict.decision == "reject"
    status = IntakeReviewStatus.REJECTED if is_reject else IntakeReviewStatus.PENDING
    review = intake_repository.create_intake_review(
        session,
        org_id=org_id,
        ticket_type=request.type.value,
        title=request.title,
        parent_id=request.parent_id,
        spec=request.spec,
        acceptance_criteria=[ac.model_dump() for ac in request.acceptance_criteria],
        budget_usd=request.budget_usd,
        repo_id=request.repo_id,
        submitted_by=request.created_by,
        submitted_at=now,
        status=status.value,
        screening_reason=verdict.reason,
        decided_by=INTAKE_SCREENER_ACTOR if is_reject else None,
        decided_at=now if is_reject else None,
    )
    session.commit()

    if is_reject:
        raise IntakeRejected(verdict.reason or "rejected by intake screening")
    raise IntakeQueuedForReview(review.id, verdict.reason or "queued for staff review")


def _initial_state_for(ticket_type: TicketType, *, parent_planning: bool) -> TicketState:
    """Mirrors ticket_service._initial_state's rule set for the approve-review path,
    which has no live parent Ticket lookup convenience the way a fresh create_ticket
    call does — the caller resolves parent_planning once and passes it in."""
    if ticket_type is TicketType.IDEA:
        return TicketState.APPROVED
    if parent_planning:
        return TicketState.PLANNING
    return TicketState.READY


def list_pending_reviews(session: Session, *, org_id: str | None = None) -> list[IntakeReview]:
    return intake_repository.list_reviews(
        session, org_id=org_id, status=IntakeReviewStatus.PENDING.value
    )


def _get_review(session: Session, review_id: int) -> IntakeReview:
    review = intake_repository.get_intake_review_any_org(session, review_id)
    if review is None:
        raise IntakeReviewNotFound(review_id)
    return review


def approve_review(
    session: Session, review_id: int, *, decided_by: str, note: str | None = None
) -> Ticket:
    review = _get_review(session, review_id)
    if review.status != IntakeReviewStatus.PENDING.value:
        raise IntakeReviewNotPending(review_id)

    parent_planning = False
    if review.parent_id is not None:
        parent = repo.get_ticket(session, review.parent_id, org_id=review.org_id)
        parent_planning = parent is not None and parent.state is TicketState.PLANNING

    ticket = repo.create_ticket(
        session,
        org_id=review.org_id,
        ticket_type=TicketType(review.ticket_type),
        title=review.title,
        parent_id=review.parent_id,
        spec=review.spec,
        acceptance_criteria=review.acceptance_criteria,
        assignee_agent=None,
        budget_usd=float(review.budget_usd) if review.budget_usd is not None else None,
        created_by=review.submitted_by,
        state=_initial_state_for(TicketType(review.ticket_type), parent_planning=parent_planning),
        repo_id=review.repo_id,
    )
    intake_repository.resolve_review(
        session,
        review,
        status=IntakeReviewStatus.APPROVED.value,
        decided_by=decided_by,
        decided_at=datetime.now(UTC),
        decision_note=note,
    )
    session.commit()
    return ticket


def reject_review(
    session: Session, review_id: int, *, decided_by: str, note: str | None = None
) -> IntakeReview:
    review = _get_review(session, review_id)
    if review.status != IntakeReviewStatus.PENDING.value:
        raise IntakeReviewNotPending(review_id)

    intake_repository.resolve_review(
        session,
        review,
        status=IntakeReviewStatus.REJECTED.value,
        decided_by=decided_by,
        decided_at=datetime.now(UTC),
        decision_note=note,
    )
    session.commit()
    return review


__all__ = [
    "INTAKE_SCREENER_ACTOR",
    "IntakeRejected",
    "IntakeQueuedForReview",
    "IntakeReviewNotFound",
    "IntakeReviewNotPending",
    "requires_screening",
    "screen_submission",
    "list_pending_reviews",
    "approve_review",
    "reject_review",
]
