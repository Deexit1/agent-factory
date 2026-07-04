from sqlalchemy.orm import Session

from api.contracts import CreateTicketRequest
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
from api.domain import state_machine
from api.repositories import ticket_repository as repo
from api.ws.broadcaster import broadcaster


def _event_ws_payload(event: TicketEvent) -> dict[str, object]:
    return {
        "id": event.id,
        "ticket_id": event.ticket_id,
        "ts": event.ts.isoformat(),
        "actor": event.actor,
        "kind": event.kind.value,
        "payload": event.payload,
    }


class TicketNotFound(Exception):
    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        super().__init__(f"ticket {ticket_id} not found")


class TransitionRefused(Exception):
    def __init__(self, reason: str, *, auto_escalated: bool) -> None:
        self.reason = reason
        self.auto_escalated = auto_escalated
        super().__init__(reason)


def create_ticket(session: Session, request: CreateTicketRequest) -> Ticket:
    ticket = repo.create_ticket(
        session,
        ticket_type=request.type,
        title=request.title,
        parent_id=request.parent_id,
        spec=request.spec,
        acceptance_criteria=[ac.model_dump() for ac in request.acceptance_criteria],
        assignee_agent=request.assignee_agent,
        budget_usd=request.budget_usd,
        created_by=request.created_by,
        state=TicketState.READY,
    )
    session.commit()
    return ticket


def get_ticket(session: Session, ticket_id: str) -> Ticket:
    ticket = repo.get_ticket(session, ticket_id)
    if ticket is None:
        raise TicketNotFound(ticket_id)
    return ticket


def get_ticket_with_recent_events(
    session: Session, ticket_id: str, *, limit: int = 20
) -> tuple[Ticket, list[TicketEvent]]:
    ticket = get_ticket(session, ticket_id)
    events, _total = repo.list_events(session, ticket_id, limit=limit, offset=0)
    return ticket, events


def list_tickets(
    session: Session,
    *,
    state: TicketState | None,
    ticket_type: TicketType | None,
    assignee_agent: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    return repo.list_tickets(
        session,
        state=state,
        ticket_type=ticket_type,
        assignee_agent=assignee_agent,
        limit=limit,
        offset=offset,
    )


def list_events(
    session: Session, ticket_id: str, *, limit: int, offset: int
) -> tuple[list[TicketEvent], int]:
    get_ticket(session, ticket_id)  # 404s if the ticket doesn't exist
    return repo.list_events(session, ticket_id, limit=limit, offset=offset)


def _acceptance_criteria_count(ticket: Ticket) -> int:
    return len(ticket.acceptance_criteria)


def request_transition(
    session: Session, ticket_id: str, to_state: TicketState, actor: str
) -> Ticket:
    ticket = get_ticket(session, ticket_id)
    from_state = ticket.state

    transition_request = state_machine.TransitionRequest(
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        bounce_count=ticket.bounce_count,
        budget_usd=float(ticket.budget_usd) if ticket.budget_usd is not None else None,
        acceptance_criteria_count=_acceptance_criteria_count(ticket),
    )

    try:
        state_machine.validate_transition(transition_request)
    except state_machine.TransitionRejected as exc:
        rejected_event = repo.append_event(
            session,
            ticket_id=ticket.id,
            actor=actor,
            kind=EventKind.TRANSITION,
            payload={
                "from": from_state.value,
                "to": to_state.value,
                "rejected": True,
                "reason": exc.reason,
            },
        )

        auto_escalated = False
        escalation_event = None
        if (
            from_state is TicketState.IN_QA
            and to_state is TicketState.BOUNCED
            and ticket.bounce_count >= state_machine.MAX_BOUNCES
        ):
            ticket.state = TicketState.ESCALATED
            escalation_event = repo.append_event(
                session,
                ticket_id=ticket.id,
                actor="system",
                kind=EventKind.TRANSITION,
                payload={
                    "from": from_state.value,
                    "to": TicketState.ESCALATED.value,
                    "reason": "max bounces exceeded",
                },
            )
            auto_escalated = True

        session.commit()
        broadcaster.publish(ticket.id, _event_ws_payload(rejected_event))
        if escalation_event is not None:
            broadcaster.publish(ticket.id, _event_ws_payload(escalation_event))
        raise TransitionRefused(exc.reason, auto_escalated=auto_escalated) from exc

    if to_state is TicketState.BOUNCED:
        ticket.bounce_count += 1
    ticket.state = to_state
    event = repo.append_event(
        session,
        ticket_id=ticket.id,
        actor=actor,
        kind=EventKind.TRANSITION,
        payload={"from": from_state.value, "to": to_state.value},
    )
    session.commit()
    broadcaster.publish(ticket.id, _event_ws_payload(event))
    return ticket


def record_approval(
    session: Session,
    ticket_id: str,
    *,
    gate: ApprovalGate,
    decided_by: str,
    decision: ApprovalDecision,
    note: str | None,
) -> Approval:
    get_ticket(session, ticket_id)  # 404s if the ticket doesn't exist
    approval = repo.create_approval(
        session,
        ticket_id=ticket_id,
        gate=gate,
        decided_by=decided_by,
        decision=decision,
        note=note,
    )
    session.commit()
    return approval


__all__ = [
    "TicketNotFound",
    "TransitionRefused",
    "create_ticket",
    "get_ticket",
    "get_ticket_with_recent_events",
    "list_tickets",
    "list_events",
    "request_transition",
    "record_approval",
]
