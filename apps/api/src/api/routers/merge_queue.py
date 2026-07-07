from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    MergeConflictIn,
    MergeQueueEntryOut,
    MergeQueueListOut,
    MergeSuccessIn,
    TicketOut,
)
from api.db.session import get_db
from api.services import ticket_service

router = APIRouter(
    prefix="/merge-queue", tags=["merge-queue"], dependencies=[Depends(get_actor_context)]
)


@router.get("", response_model=MergeQueueListOut)
def list_queued(
    repo: str = Query(...),
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> MergeQueueListOut:
    entries = ticket_service.list_queued_merge_queue_entries(
        db, org_id=actor_context.org_id, repo_name=repo
    )
    return MergeQueueListOut(items=[MergeQueueEntryOut.model_validate(e) for e in entries])


@router.post("/{entry_id}/merge", response_model=TicketOut)
def merge(
    entry_id: int,
    request: MergeSuccessIn,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    try:
        ticket = ticket_service.resolve_merge_success(
            db, entry_id, org_id=actor_context.org_id, actor=request.actor
        )
    except ticket_service.MergeQueueEntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TransitionRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    return TicketOut.model_validate(ticket)


@router.post("/{entry_id}/conflict", response_model=TicketOut)
def conflict(
    entry_id: int,
    request: MergeConflictIn,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    try:
        ticket = ticket_service.resolve_merge_conflict(
            db,
            entry_id,
            org_id=actor_context.org_id,
            actor=request.actor,
            conflicting_paths=request.conflicting_paths,
        )
    except ticket_service.MergeQueueEntryNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TransitionRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc
    return TicketOut.model_validate(ticket)
