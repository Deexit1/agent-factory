from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.models import (
    Approval,
    ApprovalDecision,
    ApprovalGate,
    EventKind,
    Ticket,
    TicketEvent,
    TicketState,
    TicketType,
)

_ID_PREFIX = {
    TicketType.IDEA: "I",
    TicketType.EPIC: "E",
    TicketType.TASK: "T",
}


def next_ticket_id(session: Session, ticket_type: TicketType) -> str:
    seq_value = session.execute(func.nextval("ticket_seq")).scalar_one()
    return f"{_ID_PREFIX[ticket_type]}-{seq_value:03d}"


def create_ticket(
    session: Session,
    *,
    ticket_type: TicketType,
    title: str,
    parent_id: str | None,
    spec: dict[str, object] | None,
    acceptance_criteria: list[dict[str, object]],
    assignee_agent: str | None,
    budget_usd: float | None,
    created_by: str,
    state: TicketState = TicketState.READY,
) -> Ticket:
    ticket = Ticket(
        id=next_ticket_id(session, ticket_type),
        type=ticket_type,
        parent_id=parent_id,
        state=state,
        title=title,
        spec=spec,
        acceptance_criteria=acceptance_criteria,
        assignee_agent=assignee_agent,
        budget_usd=budget_usd,
        spent_usd=0,
        bounce_count=0,
        created_by=created_by,
    )
    session.add(ticket)
    session.flush()
    return ticket


def get_ticket(session: Session, ticket_id: str) -> Ticket | None:
    return session.get(Ticket, ticket_id)


def list_tickets(
    session: Session,
    *,
    state: TicketState | None = None,
    ticket_type: TicketType | None = None,
    assignee_agent: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    filters = []
    if state is not None:
        filters.append(Ticket.state == state)
    if ticket_type is not None:
        filters.append(Ticket.type == ticket_type)
    if assignee_agent is not None:
        filters.append(Ticket.assignee_agent == assignee_agent)

    total = session.execute(select(func.count()).select_from(Ticket).where(*filters)).scalar_one()
    items = (
        session.execute(
            select(Ticket).where(*filters).order_by(Ticket.id).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(items), total


def append_event(
    session: Session,
    *,
    ticket_id: str,
    actor: str,
    kind: EventKind,
    payload: dict[str, object],
) -> TicketEvent:
    event = TicketEvent(
        ticket_id=ticket_id,
        ts=datetime.now(UTC),
        actor=actor,
        kind=kind,
        payload=payload,
    )
    session.add(event)
    session.flush()
    return event


def list_events(
    session: Session,
    ticket_id: str,
    *,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[TicketEvent], int]:
    total = session.execute(
        select(func.count()).select_from(TicketEvent).where(TicketEvent.ticket_id == ticket_id)
    ).scalar_one()
    items = (
        session.execute(
            select(TicketEvent)
            .where(TicketEvent.ticket_id == ticket_id)
            .order_by(TicketEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(items), total


def create_approval(
    session: Session,
    *,
    ticket_id: str,
    gate: ApprovalGate,
    decided_by: str,
    decision: ApprovalDecision,
    note: str | None,
) -> Approval:
    approval = Approval(
        ticket_id=ticket_id,
        gate=gate,
        decided_by=decided_by,
        decision=decision,
        note=note,
        ts=datetime.now(UTC),
    )
    session.add(approval)
    session.flush()
    return approval
