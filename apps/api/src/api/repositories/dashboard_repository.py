from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.models import CostLedgerEntry, EscapedDefectReport, EventKind, Ticket, TicketEvent


@dataclass(frozen=True)
class DashboardRow:
    ticket_id: str
    state: str
    bounce_count: int
    created_at: datetime
    done_at: datetime | None
    cost_usd: float
    escaped_defects: int


def _done_at(session: Session, ticket_id: str, *, org_id: str) -> datetime | None:
    return session.execute(
        select(TicketEvent.ts)
        .where(
            TicketEvent.ticket_id == ticket_id,
            TicketEvent.org_id == org_id,
            TicketEvent.kind == EventKind.TRANSITION,
            TicketEvent.payload["to"].astext == "done",
        )
        .order_by(TicketEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _cost_usd(session: Session, ticket_id: str, *, org_id: str) -> float:
    total = session.execute(
        select(func.coalesce(func.sum(CostLedgerEntry.usd), 0)).where(
            CostLedgerEntry.ticket_id == ticket_id, CostLedgerEntry.org_id == org_id
        )
    ).scalar_one()
    return float(total)


def _escaped_defects(session: Session, ticket_id: str, *, org_id: str) -> int:
    return session.execute(
        select(func.count())
        .select_from(EscapedDefectReport)
        .where(EscapedDefectReport.ticket_id == ticket_id, EscapedDefectReport.org_id == org_id)
    ).scalar_one()


def list_dashboard_rows(session: Session, *, org_id: str) -> list[DashboardRow]:
    tickets = (
        session.execute(select(Ticket).where(Ticket.org_id == org_id).order_by(Ticket.id))
        .scalars()
        .all()
    )
    return [
        DashboardRow(
            ticket_id=t.id,
            state=t.state.value,
            bounce_count=t.bounce_count,
            created_at=t.created_at,
            done_at=_done_at(session, t.id, org_id=org_id),
            cost_usd=_cost_usd(session, t.id, org_id=org_id),
            escaped_defects=_escaped_defects(session, t.id, org_id=org_id),
        )
        for t in tickets
    ]
