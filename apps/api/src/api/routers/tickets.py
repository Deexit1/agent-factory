from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    ApprovalOut,
    ApproveRequest,
    CreateTicketRequest,
    EventOut,
    PaginatedEvents,
    PaginatedTickets,
    TicketOut,
    TicketWithEventsOut,
    TransitionRequest,
)
from api.db.models import TicketState, TicketType
from api.db.session import get_db
from api.services import ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])

APPROVER_ROLES = {"approver", "admin"}


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(request: CreateTicketRequest, db: Session = Depends(get_db)) -> TicketOut:
    ticket = ticket_service.create_ticket(db, request)
    return TicketOut.model_validate(ticket)


@router.get("", response_model=PaginatedTickets)
def list_tickets(
    state: TicketState | None = None,
    type_: TicketType | None = Query(default=None, alias="type"),
    assignee_agent: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedTickets:
    items, total = ticket_service.list_tickets(
        db,
        state=state,
        ticket_type=type_,
        assignee_agent=assignee_agent,
        limit=limit,
        offset=offset,
    )
    return PaginatedTickets(
        items=[TicketOut.model_validate(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{ticket_id}", response_model=TicketWithEventsOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db)) -> TicketWithEventsOut:
    try:
        ticket, events = ticket_service.get_ticket_with_recent_events(db, ticket_id)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return TicketWithEventsOut(
        **TicketOut.model_validate(ticket).model_dump(),
        recent_events=[EventOut.model_validate(e) for e in events],
    )


@router.post("/{ticket_id}/transition", response_model=TicketOut)
def transition_ticket(
    ticket_id: str, request: TransitionRequest, db: Session = Depends(get_db)
) -> TicketOut:
    try:
        ticket = ticket_service.request_transition(db, ticket_id, request.to_state, request.actor)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TransitionRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc

    return TicketOut.model_validate(ticket)


@router.post("/{ticket_id}/approve", response_model=ApprovalOut)
def approve_ticket(
    ticket_id: str,
    request: ApproveRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> ApprovalOut:
    if actor_context.role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="only an approver or admin may decide a gate")

    try:
        approval = ticket_service.record_approval(
            db,
            ticket_id,
            gate=request.gate,
            decided_by=actor_context.actor,
            decision=request.decision,
            note=request.note,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ApprovalOut.model_validate(approval)


@router.get("/{ticket_id}/events", response_model=PaginatedEvents)
def list_ticket_events(
    ticket_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> PaginatedEvents:
    try:
        items, total = ticket_service.list_events(db, ticket_id, limit=limit, offset=offset)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PaginatedEvents(
        items=[EventOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
