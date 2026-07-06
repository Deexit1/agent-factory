import csv
import io
import statistics
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from api.contracts import DashboardMetricsOut
from api.db.models import EscapedDefectReport
from api.repositories import dashboard_repository as repo
from api.repositories.dashboard_repository import DashboardRow
from api.services.ticket_service import get_ticket

CSV_COLUMNS = [
    "ticket_id",
    "state",
    "bounce_count",
    "created_at",
    "done_at",
    "cycle_time_hours",
    "cost_usd",
    "escaped_defects",
]


def _cycle_time_hours(row: DashboardRow) -> float | None:
    if row.done_at is None:
        return None
    return (row.done_at - row.created_at).total_seconds() / 3600


def compute_metrics(session: Session, *, org_id: str) -> DashboardMetricsOut:
    rows = repo.list_dashboard_rows(session, org_id=org_id)
    return _metrics_from_rows(rows)


def _metrics_from_rows(rows: list[DashboardRow]) -> DashboardMetricsOut:
    done_rows = [r for r in rows if r.state == "done"]
    escalated_rows = [r for r in rows if r.state == "escalated"]
    terminal_count = len(done_rows) + len(escalated_rows)

    # docs/00-vision.md: "tickets closed with <= 1 bounce" out of every ticket that reached
    # a terminal QA outcome (done or escalated) - escalated tickets count against the rate.
    first_pass_qa_rate = (
        sum(1 for r in done_rows if r.bounce_count <= 1) / terminal_count
        if terminal_count > 0
        else None
    )

    done_costs = [r.cost_usd for r in done_rows]
    median_cost = statistics.median(done_costs) if done_costs else None

    cycle_times = [t for r in done_rows if (t := _cycle_time_hours(r)) is not None]
    median_cycle_time = statistics.median(cycle_times) if cycle_times else None

    return DashboardMetricsOut(
        tickets_closed=len(done_rows),
        tickets_escalated=len(escalated_rows),
        first_pass_qa_rate=first_pass_qa_rate,
        median_cost_per_closed_ticket_usd=median_cost,
        escaped_defects=sum(r.escaped_defects for r in rows),
        median_cycle_time_hours=median_cycle_time,
    )


def export_csv(session: Session, *, org_id: str) -> str:
    rows = repo.list_dashboard_rows(session, org_id=org_id)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        cycle_time = _cycle_time_hours(row)
        writer.writerow(
            [
                row.ticket_id,
                row.state,
                row.bounce_count,
                row.created_at.isoformat(),
                row.done_at.isoformat() if row.done_at else "",
                cycle_time if cycle_time is not None else "",
                row.cost_usd,
                row.escaped_defects,
            ]
        )
    return buffer.getvalue()


def record_escaped_defect(
    session: Session, *, ticket_id: str, note: str, reported_by: str, org_id: str
) -> EscapedDefectReport:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    report = EscapedDefectReport(
        org_id=org_id, ticket_id=ticket_id, note=note, reported_by=reported_by, ts=datetime.now(UTC)
    )
    session.add(report)
    session.commit()
    return report


__all__ = ["compute_metrics", "export_csv", "record_escaped_defect"]
