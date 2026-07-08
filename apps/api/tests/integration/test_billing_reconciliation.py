"""T-205 (SPEC-205 AC5): "Usage shown in the org dashboard equals what Stripe [Razorpay]
was told." A real reconciliation, not a tautology: the dashboard
(compute_live_invoice_for_period) computes directly from usage_events/agent_runs/
ticket_events; the metering job (run_metering_for_day) separately records into
billing_usage_reports, what would actually be sent to Razorpay. This test proves those
two independently-derived numbers agree once the metering job has run for every day in
the period — the same real Postgres fixtures test_billing_metering_job.py seeds."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from api.db.models import AgentRun, AgentRunStatus, TicketType
from api.repositories import org_repository
from api.repositories import ticket_repository as repo
from api.services import billing_service

REPORT_DAY = date(2026, 2, 1)


def _make_org(session: Session) -> str:
    org = org_repository.create_org(session, name="Reconciliation Org")
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


def test_dashboard_usage_matches_what_the_metering_job_recorded(db_session: Session) -> None:
    org_id = _make_org(db_session)
    ticket_id = _make_ticket(db_session, org_id=org_id)
    started_at = datetime.combine(REPORT_DAY, datetime.min.time(), tzinfo=UTC) + timedelta(hours=1)
    db_session.add(
        AgentRun(
            org_id=org_id,
            ticket_id=ticket_id,
            agent_role="dev",
            model="claude-sonnet-5",
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=250),
            status=AgentRunStatus.COMPLETED,
            provider="anthropic",
        )
    )
    db_session.commit()

    # Before the metering job has run: dashboard already sees the live usage, but
    # nothing has been recorded as "sent to Razorpay" yet.
    live_before = billing_service.compute_live_invoice_for_period(
        db_session, org_id=org_id, start_date=REPORT_DAY, end_date=REPORT_DAY + timedelta(days=1)
    )
    ledger_before = billing_service.compute_invoice_for_period(
        db_session, org_id=org_id, start_date=REPORT_DAY, end_date=REPORT_DAY + timedelta(days=1)
    )
    assert ledger_before.total_inr == ledger_before.base_fee_inr  # nothing reported yet
    agent_minutes_before = next(
        item for item in live_before.line_items if item.kind == "agent_run_minutes"
    )
    assert agent_minutes_before.used == 250

    billing_service.run_metering_for_day(db_session, org_id=org_id, report_date=REPORT_DAY)
    db_session.commit()

    live_after = billing_service.compute_live_invoice_for_period(
        db_session, org_id=org_id, start_date=REPORT_DAY, end_date=REPORT_DAY + timedelta(days=1)
    )
    ledger_after = billing_service.compute_invoice_for_period(
        db_session, org_id=org_id, start_date=REPORT_DAY, end_date=REPORT_DAY + timedelta(days=1)
    )

    # AC5: the two independently-computed totals now agree, line item by line item.
    live_by_kind = {item.kind: item for item in live_after.line_items}
    ledger_by_kind = {item.kind: item for item in ledger_after.line_items}
    for kind in live_by_kind:
        assert live_by_kind[kind].used == ledger_by_kind[kind].used
        assert live_by_kind[kind].amount_inr == ledger_by_kind[kind].amount_inr
    assert live_after.total_inr == ledger_after.total_inr
