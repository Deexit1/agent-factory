from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.db.models import AgentRun, AgentRunStatus, CostLedgerEntry


def create_agent_run(
    session: Session,
    *,
    org_id: str,
    ticket_id: str,
    agent_role: str,
    model: str,
    trace_id: str | None,
    prompt_version: str | None = None,
) -> AgentRun:
    run = AgentRun(
        org_id=org_id,
        ticket_id=ticket_id,
        agent_role=agent_role,
        model=model,
        started_at=datetime.now(UTC),
        status=AgentRunStatus.RUNNING,
        tokens_in=0,
        tokens_out=0,
        cost_usd=0,
        trace_id=trace_id,
        prompt_version=prompt_version,
    )
    session.add(run)
    session.flush()
    return run


def get_agent_run(session: Session, run_id: int, *, org_id: str) -> AgentRun | None:
    run = session.get(AgentRun, run_id)
    if run is None or run.org_id != org_id:
        return None
    return run


def complete_agent_run(
    session: Session,
    run: AgentRun,
    *,
    status: AgentRunStatus,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    provider: str = "anthropic",
) -> AgentRun:
    run.ended_at = datetime.now(UTC)
    run.status = status
    run.tokens_in = tokens_in
    run.tokens_out = tokens_out
    run.cost_usd = cost_usd
    run.provider = provider
    session.flush()

    if cost_usd > 0:
        create_cost_ledger_entry(
            session,
            org_id=run.org_id,
            ticket_id=run.ticket_id,
            agent_run_id=run.id,
            provider=provider,
            model=run.model,
            usd=cost_usd,
        )
    return run


def list_agent_runs(session: Session, ticket_id: str, *, org_id: str) -> list[AgentRun]:
    return list(
        session.execute(
            select(AgentRun)
            .where(AgentRun.ticket_id == ticket_id, AgentRun.org_id == org_id)
            .order_by(AgentRun.id)
        )
        .scalars()
        .all()
    )


def create_cost_ledger_entry(
    session: Session,
    *,
    org_id: str,
    ticket_id: str,
    agent_run_id: int,
    provider: str,
    model: str,
    usd: float,
) -> CostLedgerEntry:
    entry = CostLedgerEntry(
        org_id=org_id,
        ticket_id=ticket_id,
        agent_run_id=agent_run_id,
        provider=provider,
        model=model,
        usd=usd,
        ts=datetime.now(UTC),
    )
    session.add(entry)
    session.flush()
    return entry


def list_cost_ledger(session: Session, ticket_id: str, *, org_id: str) -> list[CostLedgerEntry]:
    return list(
        session.execute(
            select(CostLedgerEntry)
            .where(CostLedgerEntry.ticket_id == ticket_id, CostLedgerEntry.org_id == org_id)
            .order_by(CostLedgerEntry.id)
        )
        .scalars()
        .all()
    )


def sum_cost_ledger(session: Session, ticket_id: str, *, org_id: str) -> float:
    total = session.execute(
        select(func.coalesce(func.sum(CostLedgerEntry.usd), 0)).where(
            CostLedgerEntry.ticket_id == ticket_id, CostLedgerEntry.org_id == org_id
        )
    ).scalar_one()
    return float(total)


def sum_cost_ledger_for_tickets(
    session: Session, ticket_ids: list[str], *, org_id: str
) -> float:
    total = session.execute(
        select(func.coalesce(func.sum(CostLedgerEntry.usd), 0)).where(
            CostLedgerEntry.ticket_id.in_(ticket_ids), CostLedgerEntry.org_id == org_id
        )
    ).scalar_one()
    return float(total)
