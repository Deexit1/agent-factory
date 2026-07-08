from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.models import (
    AgentRun,
    BillingUsageReport,
    EventKind,
    Org,
    TicketEvent,
    UsageEvent,
)


def record_usage_event(
    session: Session, *, org_id: str, ticket_id: str, kind: str, quantity: float, ts: datetime
) -> UsageEvent:
    event = UsageEvent(org_id=org_id, ticket_id=ticket_id, kind=kind, quantity=quantity, ts=ts)
    session.add(event)
    session.flush()
    return event


def sum_usage_events(
    session: Session, *, org_id: str, kind: str, start: datetime, end: datetime
) -> float:
    total = session.execute(
        select(func.coalesce(func.sum(UsageEvent.quantity), 0)).where(
            UsageEvent.org_id == org_id,
            UsageEvent.kind == kind,
            UsageEvent.ts >= start,
            UsageEvent.ts < end,
        )
    ).scalar_one()
    return float(total)


def sum_agent_run_minutes(
    session: Session, *, org_id: str, start: datetime, end: datetime
) -> float:
    """agent_run_minutes needs no dedicated usage_events row — it's derived straight
    from agent_runs.started_at/ended_at, which already exists and already carries
    org_id (T-205's own design decision: reuse recorded data, don't re-instrument)."""
    seconds = session.execute(
        select(
            func.coalesce(
                func.sum(func.extract("epoch", AgentRun.ended_at - AgentRun.started_at)), 0
            )
        ).where(
            AgentRun.org_id == org_id,
            AgentRun.ended_at.is_not(None),
            AgentRun.started_at >= start,
            AgentRun.started_at < end,
        )
    ).scalar_one()
    return float(seconds) / 60.0


def count_active_tickets(session: Session, *, org_id: str, start: datetime, end: datetime) -> int:
    """Distinct tickets transitioned to `in_progress` in the window — derived from the
    existing ticket_events transition audit trail, not a new tracking mechanism."""
    count = session.execute(
        select(func.count(func.distinct(TicketEvent.ticket_id))).where(
            TicketEvent.org_id == org_id,
            TicketEvent.kind == EventKind.TRANSITION,
            TicketEvent.payload["to"].astext == "in_progress",
            TicketEvent.payload["rejected"].astext.is_distinct_from("true"),
            TicketEvent.ts >= start,
            TicketEvent.ts < end,
        )
    ).scalar_one()
    return int(count)


def get_usage_report(
    session: Session, *, org_id: str, report_date: date, kind: str
) -> BillingUsageReport | None:
    """AC1's idempotency check: a non-null result means this (org, day, kind) has
    already been reported to Razorpay — the metering job must skip it."""
    return session.execute(
        select(BillingUsageReport).where(
            BillingUsageReport.org_id == org_id,
            BillingUsageReport.report_date == report_date,
            BillingUsageReport.kind == kind,
        )
    ).scalar_one_or_none()


def record_usage_report(
    session: Session,
    *,
    org_id: str,
    report_date: date,
    kind: str,
    quantity: float,
    razorpay_addon_id: str | None,
    created_at: datetime,
) -> BillingUsageReport:
    report = BillingUsageReport(
        org_id=org_id,
        report_date=report_date,
        kind=kind,
        quantity=quantity,
        razorpay_addon_id=razorpay_addon_id,
        created_at=created_at,
    )
    session.add(report)
    session.flush()
    return report


def sum_usage_reports(
    session: Session, *, org_id: str, kind: str, start_date: date, end_date: date
) -> float:
    """AC5 reconciliation: what the metering job actually recorded as sent to Razorpay
    for a period — the org dashboard's usage endpoint is checked against this."""
    total = session.execute(
        select(func.coalesce(func.sum(BillingUsageReport.quantity), 0)).where(
            BillingUsageReport.org_id == org_id,
            BillingUsageReport.kind == kind,
            BillingUsageReport.report_date >= start_date,
            BillingUsageReport.report_date < end_date,
        )
    ).scalar_one()
    return float(total)


def list_all_org_ids(session: Session) -> list[str]:
    """The nightly metering job's one legitimate cross-tenant sweep — no single org_id
    to scope by, since it visits every org. Allowlisted in
    scripts/check_tenant_scope_gate.py next to next_ticket_id/user_repository.get_user,
    same documented pattern."""
    return list(session.execute(select(Org.id).order_by(Org.id)).scalars().all())


def get_org_by_razorpay_subscription_id(session: Session, subscription_id: str) -> Org | None:
    """A Razorpay webhook delivery only ever gives us its subscription id, never an
    org_id — same shape as repo_repository.list_by_installation's GitHub-webhook
    justification. The caller resolves org_id from the returned row before doing
    anything tenant-scoped with it."""
    return session.execute(
        select(Org).where(Org.razorpay_subscription_id == subscription_id)
    ).scalar_one_or_none()


__all__ = [
    "record_usage_event",
    "sum_usage_events",
    "sum_agent_run_minutes",
    "count_active_tickets",
    "get_usage_report",
    "record_usage_report",
    "sum_usage_reports",
    "list_all_org_ids",
    "get_org_by_razorpay_subscription_id",
]
