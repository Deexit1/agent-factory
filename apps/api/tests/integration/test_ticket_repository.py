from sqlalchemy.orm import Session

from api.db.models import ApprovalDecision, ApprovalGate, EventKind, Ticket, TicketState, TicketType
from api.repositories import ticket_repository as repo


def _make_task(session: Session) -> Ticket:
    return repo.create_ticket(
        session,
        ticket_type=TicketType.TASK,
        title="Do the thing",
        parent_id=None,
        spec=None,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        assignee_agent=None,
        budget_usd=10.0,
        created_by="human:alice",
    )


def test_create_ticket_generates_human_readable_id_per_type(db_session: Session) -> None:
    task = repo.create_ticket(
        db_session,
        ticket_type=TicketType.TASK,
        title="A task",
        parent_id=None,
        spec=None,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        assignee_agent=None,
        budget_usd=10.0,
        created_by="human:alice",
    )
    idea = repo.create_ticket(
        db_session,
        ticket_type=TicketType.IDEA,
        title="An idea",
        parent_id=None,
        spec=None,
        acceptance_criteria=[],
        assignee_agent=None,
        budget_usd=None,
        created_by="human:alice",
    )

    assert task.id.startswith("T-")
    assert idea.id.startswith("I-")
    assert task.state == TicketState.READY
    db_session.commit()


def test_get_ticket_returns_none_when_missing(db_session: Session) -> None:
    assert repo.get_ticket(db_session, "T-does-not-exist") is None


def test_list_tickets_filters_by_state_and_paginates(db_session: Session) -> None:
    for _ in range(3):
        _make_task(db_session)
    db_session.commit()

    items, total = repo.list_tickets(db_session, state=TicketState.READY, limit=2, offset=0)
    assert total == 3
    assert len(items) == 2

    items_page_2, total_page_2 = repo.list_tickets(
        db_session, state=TicketState.READY, limit=2, offset=2
    )
    assert total_page_2 == 3
    assert len(items_page_2) == 1

    no_match, no_match_total = repo.list_tickets(db_session, state=TicketState.DONE)
    assert no_match == []
    assert no_match_total == 0


def test_append_event_and_list_events_returns_newest_first(db_session: Session) -> None:
    ticket = _make_task(db_session)
    db_session.commit()

    first = repo.append_event(
        db_session, ticket_id=ticket.id, actor="system", kind=EventKind.TRANSITION, payload={"n": 1}
    )
    second = repo.append_event(
        db_session, ticket_id=ticket.id, actor="system", kind=EventKind.TRANSITION, payload={"n": 2}
    )
    db_session.commit()

    events, total = repo.list_events(db_session, ticket.id)
    assert total == 2
    assert [e.id for e in events] == [second.id, first.id]


def test_create_approval(db_session: Session) -> None:
    ticket = _make_task(db_session)
    db_session.commit()

    approval = repo.create_approval(
        db_session,
        ticket_id=ticket.id,
        gate=ApprovalGate.BUDGET,
        decided_by="human:bob",
        decision=ApprovalDecision.APPROVED,
        note="looks good",
    )
    db_session.commit()

    assert approval.id is not None
    assert approval.decision == ApprovalDecision.APPROVED
