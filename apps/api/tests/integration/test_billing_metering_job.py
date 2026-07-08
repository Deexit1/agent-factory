"""T-205 (SPEC-205 AC1/AC2): the nightly metering job against real Postgres.

AC1: re-running a day is idempotent — zero duplicate usage records.
AC2: a seeded month of fixtures (real agent_runs/usage_events/ticket_events rows
spread across two different days) produces an invoice matching a hand-computed golden
total, via the same compute_invoice the pure unit test (test_billing_plans.py) checks.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from api.db.models import AgentRun, AgentRunStatus, EventKind, TicketEvent, TicketType, UsageEvent
from api.repositories import org_repository
from api.repositories import ticket_repository as repo
from api.services import billing_service

DAY_1 = date(2026, 1, 1)
DAY_15 = date(2026, 1, 15)


def _make_org_on_starter_plan(session: Session) -> str:
    org = org_repository.create_org(session, name="Metering Test Org")
    billing_service.set_plan(session, org.id, "starter")
    session.commit()
    return org.id


def _make_ticket(session: Session, *, org_id: str) -> str:
    ticket = repo.create_ticket(
        session,
        org_id=org_id,
        ticket_type=TicketType.TASK,
        title="Do the thing",
        parent_id=None,
        spec=None,
        acceptance_criteria=[{"id": "AC-1", "description": "d", "verification": "v"}],
        assignee_agent=None,
        budget_usd=10.0,
        created_by="human:alice",
    )
    session.commit()
    return ticket.id


def _seed_agent_run(
    session: Session, *, org_id: str, ticket_id: str, day: date, minutes: float
) -> None:
    started_at = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=1)
    session.add(
        AgentRun(
            org_id=org_id,
            ticket_id=ticket_id,
            agent_role="dev",
            model="claude-sonnet-5",
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=minutes),
            status=AgentRunStatus.COMPLETED,
            provider="anthropic",
        )
    )
    session.commit()


def _seed_sandbox_usage(
    session: Session, *, org_id: str, ticket_id: str, day: date, minutes: float
) -> None:
    ts = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=2)
    session.add(
        UsageEvent(
            org_id=org_id, ticket_id=ticket_id, kind="sandbox_minutes", quantity=minutes, ts=ts
        )
    )
    session.commit()


def _seed_active_ticket(session: Session, *, org_id: str, ticket_id: str, day: date) -> None:
    ts = datetime.combine(day, datetime.min.time(), tzinfo=UTC) + timedelta(hours=3)
    session.add(
        TicketEvent(
            org_id=org_id,
            ticket_id=ticket_id,
            ts=ts,
            actor="human:alice",
            kind=EventKind.TRANSITION,
            payload={"from": "ready", "to": "in_progress"},
        )
    )
    session.commit()


def test_run_metering_for_day_is_idempotent(db_session: Session) -> None:
    org_id = _make_org_on_starter_plan(db_session)
    ticket_id = _make_ticket(db_session, org_id=org_id)
    _seed_agent_run(db_session, org_id=org_id, ticket_id=ticket_id, day=DAY_1, minutes=100)
    _seed_sandbox_usage(db_session, org_id=org_id, ticket_id=ticket_id, day=DAY_1, minutes=80)
    _seed_active_ticket(db_session, org_id=org_id, ticket_id=ticket_id, day=DAY_1)

    first = billing_service.run_metering_for_day(db_session, org_id=org_id, report_date=DAY_1)
    db_session.commit()
    assert sorted(first) == ["active_tickets", "agent_run_minutes", "sandbox_minutes"]

    second = billing_service.run_metering_for_day(db_session, org_id=org_id, report_date=DAY_1)
    db_session.commit()
    assert second == []  # AC1: already reported — no-op, zero new rows

    reported_total = billing_service.compute_invoice_for_period(
        db_session, org_id=org_id, start_date=DAY_1, end_date=DAY_1 + timedelta(days=1)
    )
    # Re-running the day a second time must not have changed what was recorded.
    assert reported_total.line_items[0].used == 100  # agent_run_minutes


def test_metering_a_seeded_month_produces_the_golden_invoice_total(db_session: Session) -> None:
    org_id = _make_org_on_starter_plan(db_session)
    ticket_a = _make_ticket(db_session, org_id=org_id)
    ticket_b = _make_ticket(db_session, org_id=org_id)
    ticket_c = _make_ticket(db_session, org_id=org_id)

    # Day 1: 2000 agent-run-min, 1500 sandbox-min, 2 distinct active tickets.
    _seed_agent_run(db_session, org_id=org_id, ticket_id=ticket_a, day=DAY_1, minutes=2_000)
    _seed_sandbox_usage(db_session, org_id=org_id, ticket_id=ticket_a, day=DAY_1, minutes=1_500)
    _seed_active_ticket(db_session, org_id=org_id, ticket_id=ticket_a, day=DAY_1)
    _seed_active_ticket(db_session, org_id=org_id, ticket_id=ticket_b, day=DAY_1)

    # Day 15: 1200 agent-run-min, 1700 sandbox-min, 1 more distinct active ticket.
    _seed_agent_run(db_session, org_id=org_id, ticket_id=ticket_b, day=DAY_15, minutes=1_200)
    _seed_sandbox_usage(db_session, org_id=org_id, ticket_id=ticket_b, day=DAY_15, minutes=1_700)
    _seed_active_ticket(db_session, org_id=org_id, ticket_id=ticket_c, day=DAY_15)

    for day in (DAY_1, DAY_15):
        billing_service.run_metering_for_day(db_session, org_id=org_id, report_date=day)
        db_session.commit()

    invoice = billing_service.compute_invoice_for_period(
        db_session, org_id=org_id, start_date=DAY_1, end_date=DAY_15 + timedelta(days=1)
    )

    line_items_by_kind = {item.kind: item for item in invoice.line_items}
    assert line_items_by_kind["agent_run_minutes"].used == 3_200
    assert line_items_by_kind["agent_run_minutes"].amount_inr == 400.0  # (3200-3000)*2.0
    assert line_items_by_kind["sandbox_minutes"].used == 3_200
    assert line_items_by_kind["sandbox_minutes"].amount_inr == 200.0  # (3200-3000)*1.0
    assert line_items_by_kind["active_tickets"].used == 3
    assert line_items_by_kind["active_tickets"].amount_inr == 0.0  # under the 20 included
    # Golden total: 4999 base + 400 + 200 + 0 overage = 5599
    assert invoice.total_inr == 5_599.0
