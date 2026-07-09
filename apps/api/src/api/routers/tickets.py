from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from api.auth import ActorContext, get_actor_context
from api.contracts import (
    AnswerPlanningQuestionsRequest,
    ApprovalOut,
    ApproveRequest,
    CreateEventRequest,
    CreateTicketRequest,
    DescendantsOut,
    EventOut,
    IntakeQueuedOut,
    PaginatedEvents,
    PaginatedTickets,
    RecordUsageEventRequest,
    ReturnToDevRequest,
    TicketOut,
    TicketWithEventsOut,
    TransitionRequest,
    UpdateTaskRequest,
    UsageEventOut,
)
from api.db.models import TicketState, TicketType
from api.db.session import get_db
from api.services import intake_service, ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"], dependencies=[Depends(get_actor_context)])

APPROVER_ROLES = {"approver", "owner"}


@router.post("", response_model=TicketOut | IntakeQueuedOut, status_code=201)
def create_ticket(
    request: CreateTicketRequest,
    response: Response,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut | IntakeQueuedOut:
    try:
        ticket = ticket_service.create_ticket(db, request, org_id=actor_context.org_id)
    except ticket_service.RepoNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.RepoNotActive as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ticket_service.TosNotCurrent as exc:
        raise HTTPException(
            status_code=403,
            detail=f"org must accept the current ToS (version {exc.current_version}) first",
        ) from exc
    except intake_service.IntakeRejected as exc:
        raise HTTPException(status_code=422, detail=exc.reason) from exc
    except intake_service.IntakeQueuedForReview as exc:
        response.status_code = 202
        return IntakeQueuedOut(intake_review_id=exc.review_id, reason=exc.reason)
    return TicketOut.model_validate(ticket)


@router.get("", response_model=PaginatedTickets)
def list_tickets(
    state: TicketState | None = None,
    type_: TicketType | None = Query(default=None, alias="type"),
    assignee_agent: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> PaginatedTickets:
    items, total = ticket_service.list_tickets(
        db,
        org_id=actor_context.org_id,
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
def get_ticket(
    ticket_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketWithEventsOut:
    try:
        ticket, events = ticket_service.get_ticket_with_recent_events(
            db, ticket_id, org_id=actor_context.org_id
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return TicketWithEventsOut(
        **TicketOut.model_validate(ticket).model_dump(),
        recent_events=[EventOut.model_validate(e) for e in events],
    )


@router.post("/{ticket_id}/transition", response_model=TicketOut)
def transition_ticket(
    ticket_id: str,
    request: TransitionRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    try:
        ticket = ticket_service.request_transition(
            db,
            ticket_id,
            request.to_state,
            request.actor,
            org_id=actor_context.org_id,
            assignee_agent=request.assignee_agent,
        )
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
        raise HTTPException(status_code=403, detail="only an approver or owner may decide a gate")

    try:
        approval = ticket_service.record_approval(
            db,
            ticket_id,
            org_id=actor_context.org_id,
            gate=request.gate,
            decided_by=actor_context.actor,
            decision=request.decision,
            note=request.note,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ApprovalOut.model_validate(approval)


@router.post("/{ticket_id}/return-to-dev", response_model=TicketOut)
def return_to_dev(
    ticket_id: str,
    request: ReturnToDevRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    if actor_context.role not in APPROVER_ROLES:
        raise HTTPException(
            status_code=403, detail="only an approver or owner may return a ticket to dev"
        )

    try:
        ticket = ticket_service.return_to_dev(
            db, ticket_id, actor=actor_context.actor, note=request.note, org_id=actor_context.org_id
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TransitionRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc

    return TicketOut.model_validate(ticket)


@router.get("/{ticket_id}/descendants", response_model=DescendantsOut)
def get_descendants(
    ticket_id: str,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> DescendantsOut:
    try:
        items = ticket_service.get_descendants(db, ticket_id, org_id=actor_context.org_id)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return DescendantsOut(items=[TicketOut.model_validate(t) for t in items])


@router.post("/{ticket_id}/answer-planning-questions", response_model=TicketOut)
def answer_planning_questions(
    ticket_id: str,
    request: AnswerPlanningQuestionsRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    if actor_context.role not in APPROVER_ROLES:
        raise HTTPException(
            status_code=403, detail="only an approver or owner may answer planning questions"
        )

    try:
        ticket = ticket_service.answer_planning_questions(
            db,
            ticket_id,
            actor=actor_context.actor,
            answers=request.answers,
            org_id=actor_context.org_id,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ticket_service.TransitionRefused as exc:
        raise HTTPException(status_code=409, detail=exc.reason) from exc

    return TicketOut.model_validate(ticket)


@router.patch("/{ticket_id}", response_model=TicketOut)
def update_task(
    ticket_id: str,
    request: UpdateTaskRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> TicketOut:
    if actor_context.role not in APPROVER_ROLES:
        raise HTTPException(status_code=403, detail="only an approver or owner may edit a task")

    try:
        ticket = ticket_service.update_task(
            db,
            ticket_id,
            org_id=actor_context.org_id,
            actor=actor_context.actor,
            title=request.title,
            spec=request.spec,
            acceptance_criteria=(
                [ac.model_dump() for ac in request.acceptance_criteria]
                if request.acceptance_criteria is not None
                else None
            ),
            budget_usd=request.budget_usd,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return TicketOut.model_validate(ticket)


@router.post("/{ticket_id}/events", response_model=EventOut, status_code=201)
def create_ticket_event(
    ticket_id: str,
    request: CreateEventRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> EventOut:
    try:
        event = ticket_service.record_event(
            db,
            ticket_id,
            org_id=actor_context.org_id,
            actor=request.actor,
            kind=request.kind,
            payload=request.payload,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return EventOut.model_validate(event)


@router.post("/{ticket_id}/usage-events", response_model=UsageEventOut, status_code=201)
def create_usage_event(
    ticket_id: str,
    request: RecordUsageEventRequest,
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> UsageEventOut:
    """T-205: posted by apps/orchestrator's SandboxClaudeCodeRunner after each real
    sandbox lease — service-token authenticated, same shape as POST .../events above."""
    try:
        event = ticket_service.record_usage_event(
            db,
            ticket_id,
            org_id=actor_context.org_id,
            kind=request.kind,
            quantity=request.quantity,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return UsageEventOut.model_validate(event)


@router.get("/{ticket_id}/events", response_model=PaginatedEvents)
def list_ticket_events(
    ticket_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor_context: ActorContext = Depends(get_actor_context),
    db: Session = Depends(get_db),
) -> PaginatedEvents:
    try:
        items, total = ticket_service.list_events(
            db, ticket_id, org_id=actor_context.org_id, limit=limit, offset=offset
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return PaginatedEvents(
        items=[EventOut.model_validate(e) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )
