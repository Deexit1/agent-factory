from schemas.models import FailureReport
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


def _initial_state(session: Session, request: CreateTicketRequest, *, org_id: str) -> TicketState:
    # Ideas enter directly at `approved` in Phase 2 (docs/03-state-machine.md) — a human
    # already decided go + budget by creating it with budget_usd set (contracts.py's
    # validator enforces that). Epics/tasks created by the Planner under an idea that's
    # still under review inherit `planning`; everything else keeps the Phase-1 default.
    if request.type is TicketType.IDEA:
        return TicketState.APPROVED
    if request.parent_id is not None:
        parent = repo.get_ticket(session, request.parent_id, org_id=org_id)
        if parent is not None and parent.state is TicketState.PLANNING:
            return TicketState.PLANNING
    return TicketState.READY


def create_ticket(session: Session, request: CreateTicketRequest, *, org_id: str) -> Ticket:
    ticket = repo.create_ticket(
        session,
        org_id=org_id,
        ticket_type=request.type,
        title=request.title,
        parent_id=request.parent_id,
        spec=request.spec,
        acceptance_criteria=[ac.model_dump() for ac in request.acceptance_criteria],
        assignee_agent=request.assignee_agent,
        budget_usd=request.budget_usd,
        created_by=request.created_by,
        state=_initial_state(session, request, org_id=org_id),
    )
    session.commit()
    return ticket


def get_ticket(session: Session, ticket_id: str, *, org_id: str) -> Ticket:
    ticket = repo.get_ticket(session, ticket_id, org_id=org_id)
    if ticket is None:
        raise TicketNotFound(ticket_id)
    return ticket


def get_ticket_with_recent_events(
    session: Session, ticket_id: str, *, org_id: str, limit: int = 20
) -> tuple[Ticket, list[TicketEvent]]:
    ticket = get_ticket(session, ticket_id, org_id=org_id)
    events, _total = repo.list_events(session, ticket_id, org_id=org_id, limit=limit, offset=0)
    return ticket, events


def list_tickets(
    session: Session,
    *,
    org_id: str,
    state: TicketState | None,
    ticket_type: TicketType | None,
    assignee_agent: str | None,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    return repo.list_tickets(
        session,
        org_id=org_id,
        state=state,
        ticket_type=ticket_type,
        assignee_agent=assignee_agent,
        limit=limit,
        offset=offset,
    )


def list_events(
    session: Session, ticket_id: str, *, org_id: str, limit: int, offset: int
) -> tuple[list[TicketEvent], int]:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    return repo.list_events(session, ticket_id, org_id=org_id, limit=limit, offset=offset)


def record_event(
    session: Session,
    ticket_id: str,
    *,
    org_id: str,
    actor: str,
    kind: EventKind,
    payload: dict[str, object],
) -> TicketEvent:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    event = repo.append_event(
        session, org_id=org_id, ticket_id=ticket_id, actor=actor, kind=kind, payload=payload
    )
    session.commit()
    broadcaster.publish(ticket_id, _event_ws_payload(event))
    return event


def _acceptance_criteria_count(ticket: Ticket) -> int:
    return len(ticket.acceptance_criteria)


def _plan_has_cycle(task_tickets: list[Ticket]) -> bool:
    """DFS-with-recursion-stack cycle check over the TaskSpec-id space each task
    ticket's `spec` JSONB carries (`spec["id"]`/`spec["depends_on"]`) — deliberately
    NOT the real Ticket.id space, since the Planner assigns its own scratch ids to
    reference sibling tasks before any Ticket row exists."""
    graph: dict[str, list[str]] = {}
    for ticket in task_tickets:
        spec = ticket.spec or {}
        task_id = spec.get("id")
        if not isinstance(task_id, str):
            continue
        depends_on = spec.get("depends_on")
        graph[task_id] = (
            [dep for dep in depends_on if isinstance(dep, str)]
            if isinstance(depends_on, list)
            else []
        )

    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dep in graph.get(node, []):
            if _visit(dep):
                return True
        visiting.discard(node)
        visited.add(node)
        return False

    return any(_visit(node) for node in graph)


def _plan_fields(
    session: Session, ticket: Ticket, *, org_id: str
) -> tuple[int, bool, float, bool]:
    """Only computed for an idea's `planning -> ready` attempt — everywhere else these
    default to the harmless zero-values on `state_machine.TransitionRequest`."""
    descendants = repo.get_descendants(session, ticket.id, org_id=org_id)
    task_tickets = [d for d in descendants if d.type is TicketType.TASK]
    task_count = len(task_tickets)
    has_cycle = _plan_has_cycle(task_tickets)
    child_budget_total = sum(float(t.budget_usd or 0) for t in task_tickets)
    has_budget_approval = repo.has_approval(
        session,
        ticket.id,
        org_id=org_id,
        gate=ApprovalGate.BUDGET,
        decision=ApprovalDecision.APPROVED,
    )
    return task_count, has_cycle, child_budget_total, has_budget_approval


def _cascade_plan_to_ready(session: Session, ticket: Ticket, *, org_id: str) -> None:
    """Once an idea's plan is approved, its descendant epic/task tickets (created
    directly into `planning`, mirroring the parent, since nothing else reaches them
    for review) become `ready` too — the Delivery Manager (T-104) picks up tasks from
    there."""
    for descendant in repo.get_descendants(session, ticket.id, org_id=org_id):
        if descendant.state is not TicketState.PLANNING:
            continue
        descendant.state = TicketState.READY
        event = repo.append_event(
            session,
            org_id=org_id,
            ticket_id=descendant.id,
            actor="system",
            kind=EventKind.TRANSITION,
            payload={"from": "planning", "to": "ready", "reason": "parent idea plan approved"},
        )
        broadcaster.publish(descendant.id, _event_ws_payload(event))


def request_transition(
    session: Session, ticket_id: str, to_state: TicketState, actor: str, *, org_id: str
) -> Ticket:
    ticket = get_ticket(session, ticket_id, org_id=org_id)
    from_state = ticket.state

    plan_task_count, plan_has_cycle, plan_child_budget_total, plan_has_budget_approval = (
        (0, False, 0.0, False)
        if not (from_state is TicketState.PLANNING and to_state is TicketState.READY)
        else _plan_fields(session, ticket, org_id=org_id)
    )

    transition_request = state_machine.TransitionRequest(
        from_state=from_state,
        to_state=to_state,
        actor=actor,
        bounce_count=ticket.bounce_count,
        budget_usd=float(ticket.budget_usd) if ticket.budget_usd is not None else None,
        acceptance_criteria_count=_acceptance_criteria_count(ticket),
        plan_task_count=plan_task_count,
        plan_has_cycle=plan_has_cycle,
        plan_child_budget_total=plan_child_budget_total,
        plan_has_budget_approval=plan_has_budget_approval,
    )

    try:
        state_machine.validate_transition(transition_request)
    except state_machine.TransitionRejected as exc:
        rejected_event = repo.append_event(
            session,
            org_id=org_id,
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
            from_state in (TicketState.IN_QA, TicketState.IN_REVIEW)
            and to_state is TicketState.BOUNCED
            and ticket.bounce_count >= state_machine.MAX_BOUNCES
        ):
            ticket.state = TicketState.ESCALATED
            escalation_event = repo.append_event(
                session,
                org_id=org_id,
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
        org_id=org_id,
        ticket_id=ticket.id,
        actor=actor,
        kind=EventKind.TRANSITION,
        payload={"from": from_state.value, "to": to_state.value},
    )

    if from_state is TicketState.PLANNING and to_state is TicketState.READY:
        _cascade_plan_to_ready(session, ticket, org_id=org_id)

    session.commit()
    broadcaster.publish(ticket.id, _event_ws_payload(event))
    return ticket


def record_approval(
    session: Session,
    ticket_id: str,
    *,
    org_id: str,
    gate: ApprovalGate,
    decided_by: str,
    decision: ApprovalDecision,
    note: str | None,
) -> Approval:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    approval = repo.create_approval(
        session,
        org_id=org_id,
        ticket_id=ticket_id,
        gate=gate,
        decided_by=decided_by,
        decision=decision,
        note=note,
    )
    session.commit()
    return approval


def return_to_dev(
    session: Session, ticket_id: str, *, actor: str, note: str, org_id: str
) -> Ticket:
    """Escalation inbox "return to dev with note" (SPEC-006 AC5): a bounce-style event
    carrying the human's note as a FailureReport, then escalated -> in_progress. Doesn't
    touch bounce_count — this is a fresh restart, not one more of the 3 QA bounces."""
    ticket = get_ticket(session, ticket_id, org_id=org_id)
    report = FailureReport(
        ticket_id=ticket_id,
        failing_suite="human-escalation-review",
        failing_tests=[],
        expected_vs_actual=note,
        suspect_files=[],
        attempt_no=min(max(ticket.bounce_count, 1), 3),
    )
    record_event(
        session,
        ticket_id,
        org_id=org_id,
        actor=actor,
        kind=EventKind.TEST_RESULT,
        payload={"conclusion": "returned_by_human", "failure_report": report.model_dump()},
    )
    return request_transition(
        session, ticket_id, TicketState.IN_PROGRESS, actor=actor, org_id=org_id
    )


def answer_planning_questions(
    session: Session, ticket_id: str, *, actor: str, answers: str, org_id: str
) -> Ticket:
    """Human-answer round trip for an under-specified idea (SPEC-102 AC2): the human's
    answers are recorded as an event, then the idea returns escalated -> planning so
    the Planner can re-run with the new context."""
    record_event(
        session,
        ticket_id,
        org_id=org_id,
        actor=actor,
        kind=EventKind.MESSAGE,
        payload={"conclusion": "planning_questions_answered", "answers": answers},
    )
    return request_transition(session, ticket_id, TicketState.PLANNING, actor=actor, org_id=org_id)


def get_descendants(session: Session, ticket_id: str, *, org_id: str) -> list[Ticket]:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    return repo.get_descendants(session, ticket_id, org_id=org_id)


def update_task(
    session: Session,
    ticket_id: str,
    *,
    org_id: str,
    actor: str,
    title: str | None,
    spec: dict[str, object] | None,
    acceptance_criteria: list[dict[str, object]] | None,
    budget_usd: float | None,
) -> Ticket:
    """Human inline-edits a Planner-produced TaskSpec (SPEC-102 AC6): versioned as an
    `edit` event carrying the full before/after ticket payload."""
    ticket = get_ticket(session, ticket_id, org_id=org_id)
    before = {
        "title": ticket.title,
        "spec": ticket.spec,
        "acceptance_criteria": ticket.acceptance_criteria,
        "budget_usd": float(ticket.budget_usd) if ticket.budget_usd is not None else None,
    }
    repo.update_ticket_fields(
        session,
        ticket,
        title=title,
        spec=spec,
        acceptance_criteria=acceptance_criteria,
        budget_usd=budget_usd,
    )
    after = {
        "title": ticket.title,
        "spec": ticket.spec,
        "acceptance_criteria": ticket.acceptance_criteria,
        "budget_usd": float(ticket.budget_usd) if ticket.budget_usd is not None else None,
    }
    event = repo.append_event(
        session,
        org_id=org_id,
        ticket_id=ticket.id,
        actor=actor,
        kind=EventKind.EDIT,
        payload={"before": before, "after": after},
    )
    session.commit()
    broadcaster.publish(ticket.id, _event_ws_payload(event))
    return ticket


__all__ = [
    "TicketNotFound",
    "TransitionRefused",
    "create_ticket",
    "get_ticket",
    "get_ticket_with_recent_events",
    "list_tickets",
    "list_events",
    "record_event",
    "request_transition",
    "record_approval",
    "return_to_dev",
    "answer_planning_questions",
    "get_descendants",
    "update_task",
]
