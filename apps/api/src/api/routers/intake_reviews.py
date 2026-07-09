"""T-206 (SPEC-206 AC2): the platform-staff review queue for borderline intake
submissions. Staff review across every org, not just their own — same
`ActorContext.is_platform_staff` gate `routers/admin.py` established for T-201
impersonation, no new auth concept, and no org_id-equality check (unlike a normal
member route) since staff aren't members of the orgs they review.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    IntakeReviewListOut,
    IntakeReviewOut,
    ResolveIntakeReviewRequest,
    TicketOut,
)
from api.db.session import get_db
from api.repositories import intake_repository
from api.services import intake_service

router = APIRouter(
    prefix="/admin/intake-reviews",
    tags=["intake-reviews"],
    dependencies=[Depends(get_actor_context)],
)


def _require_staff(actor_context: ActorContext) -> None:
    if not actor_context.is_platform_staff:
        raise HTTPException(status_code=403, detail="platform staff only")


@router.get("", response_model=IntakeReviewListOut)
def list_reviews(
    status: str | None = Query(default="pending"),
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> IntakeReviewListOut:
    _require_staff(actor_context)
    if status == "pending" or status is None:
        reviews = intake_service.list_pending_reviews(db)
    else:
        reviews = intake_repository.list_reviews(db, org_id=None, status=status)
    return IntakeReviewListOut(items=[IntakeReviewOut.model_validate(r) for r in reviews])


@router.post("/{review_id}/approve", response_model=TicketOut)
def approve_review(
    review_id: int,
    request: ResolveIntakeReviewRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    _require_staff(actor_context)
    try:
        ticket = intake_service.approve_review(
            db, review_id, decided_by=actor_context.actor, note=request.note
        )
    except intake_service.IntakeReviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except intake_service.IntakeReviewNotPending as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return TicketOut.model_validate(ticket)


@router.post("/{review_id}/reject", response_model=IntakeReviewOut)
def reject_review(
    review_id: int,
    request: ResolveIntakeReviewRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> IntakeReviewOut:
    _require_staff(actor_context)
    try:
        review = intake_service.reject_review(
            db, review_id, decided_by=actor_context.actor, note=request.note
        )
    except intake_service.IntakeReviewNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except intake_service.IntakeReviewNotPending as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return IntakeReviewOut.model_validate(review)
