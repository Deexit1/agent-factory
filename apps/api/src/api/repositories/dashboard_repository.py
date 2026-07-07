from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.models import (
    AgentRun,
    CostLedgerEntry,
    EscapedDefectReport,
    EventKind,
    Ticket,
    TicketEvent,
)


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


def sum_cost_ledger_by_agent_role(session: Session, *, org_id: str) -> list[tuple[str, float]]:
    rows = session.execute(
        select(AgentRun.agent_role, func.coalesce(func.sum(CostLedgerEntry.usd), 0))
        .join(AgentRun, AgentRun.id == CostLedgerEntry.agent_run_id)
        .where(CostLedgerEntry.org_id == org_id)
        .group_by(AgentRun.agent_role)
        .order_by(AgentRun.agent_role)
    ).all()
    return [(role, float(total)) for role, total in rows]


def sum_cost_ledger_by_prompt_version(
    session: Session, *, org_id: str
) -> list[tuple[str, str, float]]:
    version_expr = func.coalesce(AgentRun.prompt_version, "unknown").label("prompt_version")
    rows = session.execute(
        select(
            AgentRun.agent_role,
            version_expr,
            func.coalesce(func.sum(CostLedgerEntry.usd), 0),
        )
        .join(AgentRun, AgentRun.id == CostLedgerEntry.agent_run_id)
        .where(CostLedgerEntry.org_id == org_id)
        .group_by(AgentRun.agent_role, version_expr)
        .order_by(AgentRun.agent_role, version_expr)
    ).all()
    return [(role, version, float(total)) for role, version, total in rows]


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
