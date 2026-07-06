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
    org_id: str,
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
        org_id=org_id,
        type=ticket_type,
        parent_id=parent_id,
        state=state,
        title=title,
        spec=spec,
        acceptance_criteria=acceptance_criteria,
        assignee_agent=assignee_agent,
        budget_usd=budget_usd,
        bounce_count=0,
        created_by=created_by,
        created_at=datetime.now(UTC),
    )
    session.add(ticket)
    session.flush()
    return ticket


def get_ticket(session: Session, ticket_id: str, *, org_id: str) -> Ticket | None:
    ticket = session.get(Ticket, ticket_id)
    if ticket is None or ticket.org_id != org_id:
        return None
    return ticket


def list_tickets(
    session: Session,
    *,
    org_id: str,
    state: TicketState | None = None,
    ticket_type: TicketType | None = None,
    assignee_agent: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Ticket], int]:
    filters = [Ticket.org_id == org_id]
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


def get_descendants(session: Session, ticket_id: str, *, org_id: str) -> list[Ticket]:
    """BFS over `parent_id` — small, bounded tree depth (idea -> epic -> task), so a
    handful of queries beats standing up a recursive CTE for this."""
    descendants: list[Ticket] = []
    frontier = [ticket_id]
    while frontier:
        children = (
            session.execute(
                select(Ticket)
                .where(Ticket.org_id == org_id, Ticket.parent_id.in_(frontier))
                .order_by(Ticket.id)
            )
            .scalars()
            .all()
        )
        if not children:
            break
        descendants.extend(children)
        frontier = [child.id for child in children]
    return descendants


def get_root_ancestor(session: Session, ticket_id: str, *, org_id: str) -> Ticket:
    """Walk `parent_id` up to the top of the tree (a task's idea, via its epic)."""
    ticket = session.get(Ticket, ticket_id)
    assert ticket is not None and ticket.org_id == org_id
    while ticket.parent_id is not None:
        parent = session.get(Ticket, ticket.parent_id)
        assert parent is not None
        ticket = parent
    return ticket


def count_in_progress_by_assignee(session: Session, *, org_id: str, assignee_agent: str) -> int:
    return session.execute(
        select(func.count())
        .select_from(Ticket)
        .where(
            Ticket.org_id == org_id,
            Ticket.state == TicketState.IN_PROGRESS,
            Ticket.assignee_agent == assignee_agent,
        )
    ).scalar_one()


def count_in_progress_by_repo(session: Session, *, org_id: str, repo: str) -> int:
    return session.execute(
        select(func.count())
        .select_from(Ticket)
        .where(
            Ticket.org_id == org_id,
            Ticket.state == TicketState.IN_PROGRESS,
            Ticket.spec["repo"].astext == repo,
        )
    ).scalar_one()


def has_approval(
    session: Session,
    ticket_id: str,
    *,
    org_id: str,
    gate: ApprovalGate,
    decision: ApprovalDecision,
) -> bool:
    return (
        session.execute(
            select(func.count())
            .select_from(Approval)
            .where(
                Approval.ticket_id == ticket_id,
                Approval.org_id == org_id,
                Approval.gate == gate,
                Approval.decision == decision,
            )
        ).scalar_one()
        > 0
    )


def update_ticket_fields(
    session: Session,
    ticket: Ticket,
    *,
    title: str | None,
    spec: dict[str, object] | None,
    acceptance_criteria: list[dict[str, object]] | None,
    budget_usd: float | None,
) -> Ticket:
    if title is not None:
        ticket.title = title
    if spec is not None:
        ticket.spec = spec
    if acceptance_criteria is not None:
        ticket.acceptance_criteria = acceptance_criteria
    if budget_usd is not None:
        ticket.budget_usd = budget_usd
    session.flush()
    return ticket


def append_event(
    session: Session,
    *,
    org_id: str,
    ticket_id: str,
    actor: str,
    kind: EventKind,
    payload: dict[str, object],
) -> TicketEvent:
    event = TicketEvent(
        org_id=org_id,
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
    org_id: str,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[TicketEvent], int]:
    filters = (TicketEvent.ticket_id == ticket_id, TicketEvent.org_id == org_id)
    total = session.execute(
        select(func.count()).select_from(TicketEvent).where(*filters)
    ).scalar_one()
    items = (
        session.execute(
            select(TicketEvent).where(*filters).order_by(TicketEvent.id.desc()).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return list(items), total


def create_approval(
    session: Session,
    *,
    org_id: str,
    ticket_id: str,
    gate: ApprovalGate,
    decided_by: str,
    decision: ApprovalDecision,
    note: str | None,
) -> Approval:
    approval = Approval(
        org_id=org_id,
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
