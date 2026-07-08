"""T-205 (SPEC-205 AC4): "Payment failure walks the dunning path and pauses the org;
payment fix unpauses." Real Postgres — reuses github_repo_service.disconnect_repo's
exact force-block precedent (T-203), keyed off org instead of repo."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from api.db.models import Org, Ticket, TicketState, TicketType
from api.repositories import org_repository
from api.repositories import ticket_repository as repo
from api.services import billing_service, ticket_service

_SUBSCRIPTION_ID = "sub_dunning_test_123"


def _make_org_with_subscription(session: Session) -> str:
    org = org_repository.create_org(session, name="Dunning Org")
    billing_service.set_plan(session, org.id, "starter")
    stored = session.get(Org, org.id)
    assert stored is not None
    stored.razorpay_subscription_id = _SUBSCRIPTION_ID
    session.commit()
    return org.id


def _make_in_progress_ticket(session: Session, *, org_id: str) -> Ticket:
    ticket = repo.create_ticket(
        session,
        org_id=org_id,
        ticket_type=TicketType.TASK,
        title="In-flight work",
        parent_id=None,
        spec=None,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        assignee_agent=None,
        budget_usd=10.0,
        created_by="human:alice",
    )
    session.commit()
    ticket_service.request_transition(
        session, ticket.id, TicketState.IN_PROGRESS, "human:alice", org_id=org_id
    )
    return ticket


def test_payment_failed_starts_a_grace_period_without_touching_in_flight_tickets(
    db_session: Session,
) -> None:
    org_id = _make_org_with_subscription(db_session)
    ticket = _make_in_progress_ticket(db_session, org_id=org_id)

    result = billing_service.handle_payment_failed(
        db_session, razorpay_subscription_id=_SUBSCRIPTION_ID
    )
    db_session.commit()

    assert result is not None
    assert result.billing_status == "past_due"
    assert result.dunning_grace_until is not None
    assert result.dunning_grace_until > datetime.now(UTC)

    still_in_progress = repo.get_ticket(db_session, ticket.id, org_id=org_id)
    assert still_in_progress is not None
    assert still_in_progress.state == TicketState.IN_PROGRESS


def test_expired_grace_period_pauses_the_org_and_force_blocks_in_flight_tickets(
    db_session: Session,
) -> None:
    org_id = _make_org_with_subscription(db_session)
    ticket = _make_in_progress_ticket(db_session, org_id=org_id)
    billing_service.handle_payment_failed(db_session, razorpay_subscription_id=_SUBSCRIPTION_ID)
    db_session.commit()

    stored = db_session.get(Org, org_id)
    assert stored is not None
    assert stored.dunning_grace_until is not None
    future_now = stored.dunning_grace_until + timedelta(hours=1)

    paused = billing_service.expire_grace_periods(db_session, now=future_now)
    db_session.commit()

    assert [o.id for o in paused] == [org_id]
    refreshed_org = db_session.get(Org, org_id)
    assert refreshed_org is not None
    assert refreshed_org.billing_status == "paused"

    blocked = repo.get_ticket(db_session, ticket.id, org_id=org_id)
    assert blocked is not None
    assert blocked.state == TicketState.BLOCKED
    # "data retained" — nothing about the ticket's history was deleted.
    events, _total = repo.list_events(db_session, ticket.id, org_id=org_id, limit=100, offset=0)
    assert any(e.actor == "system:billing" for e in events)


def test_grace_period_not_yet_expired_leaves_the_org_untouched(db_session: Session) -> None:
    org_id = _make_org_with_subscription(db_session)
    billing_service.handle_payment_failed(db_session, razorpay_subscription_id=_SUBSCRIPTION_ID)
    db_session.commit()

    paused = billing_service.expire_grace_periods(db_session)
    db_session.commit()

    assert org_id not in [o.id for o in paused]
    refreshed_org = db_session.get(Org, org_id)
    assert refreshed_org is not None
    assert refreshed_org.billing_status == "past_due"


def test_payment_succeeded_unpauses_the_org_but_does_not_auto_unblock_tickets(
    db_session: Session,
) -> None:
    org_id = _make_org_with_subscription(db_session)
    ticket = _make_in_progress_ticket(db_session, org_id=org_id)
    billing_service.pause_org_for_nonpayment(db_session, org_id=org_id)
    db_session.commit()

    result = billing_service.handle_payment_succeeded(
        db_session, razorpay_subscription_id=_SUBSCRIPTION_ID
    )
    db_session.commit()

    assert result is not None
    assert result.billing_status == "active"
    assert result.dunning_grace_until is None

    # Pre-existing gap since T-203 (github_repo_service.disconnect_repo has the same
    # standing): BLOCKED has no whitelisted exit in state_machine.py at all — a human
    # must manually resolve each ticket. Not created or closed by this ticket.
    still_blocked = repo.get_ticket(db_session, ticket.id, org_id=org_id)
    assert still_blocked is not None
    assert still_blocked.state == TicketState.BLOCKED


def test_webhook_events_for_an_unknown_subscription_are_a_harmless_no_op(
    db_session: Session,
) -> None:
    failed = billing_service.handle_payment_failed(db_session, razorpay_subscription_id="sub_ghost")
    assert failed is None
    succeeded = billing_service.handle_payment_succeeded(
        db_session, razorpay_subscription_id="sub_ghost"
    )
    assert succeeded is None
