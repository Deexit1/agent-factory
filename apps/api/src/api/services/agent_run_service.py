from sqlalchemy.orm import Session

from api.contracts import CostSummaryOut
from api.db.models import AgentRun, AgentRunStatus, CostLedgerEntry
from api.repositories import agent_run_repository as repo
from api.services.ticket_service import TicketNotFound, get_ticket


class AgentRunNotFound(Exception):
    def __init__(self, run_id: int) -> None:
        self.run_id = run_id
        super().__init__(f"agent run {run_id} not found")


def create_agent_run(
    session: Session,
    ticket_id: str,
    *,
    agent_role: str,
    model: str,
    trace_id: str | None,
    org_id: str,
) -> AgentRun:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    run = repo.create_agent_run(
        session,
        org_id=org_id,
        ticket_id=ticket_id,
        agent_role=agent_role,
        model=model,
        trace_id=trace_id,
    )
    session.commit()
    return run


def complete_agent_run(
    session: Session,
    ticket_id: str,
    run_id: int,
    *,
    status: AgentRunStatus,
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    org_id: str,
) -> AgentRun:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    run = repo.get_agent_run(session, run_id, org_id=org_id)
    if run is None or run.ticket_id != ticket_id:
        raise AgentRunNotFound(run_id)

    run = repo.complete_agent_run(
        session, run, status=status, tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd
    )
    session.commit()
    return run


def list_agent_runs(session: Session, ticket_id: str, *, org_id: str) -> list[AgentRun]:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    return repo.list_agent_runs(session, ticket_id, org_id=org_id)


def list_cost_ledger(session: Session, ticket_id: str, *, org_id: str) -> list[CostLedgerEntry]:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    return repo.list_cost_ledger(session, ticket_id, org_id=org_id)


def cost_summary(session: Session, ticket_id: str, *, org_id: str) -> CostSummaryOut:
    get_ticket(session, ticket_id, org_id=org_id)  # 404s if the ticket doesn't exist
    runs = repo.list_agent_runs(session, ticket_id, org_id=org_id)
    agent_runs_total = sum(float(run.cost_usd) for run in runs)
    ledger_total = repo.sum_cost_ledger(session, ticket_id, org_id=org_id)
    return CostSummaryOut(
        ticket_id=ticket_id,
        agent_runs_total_usd=agent_runs_total,
        cost_ledger_total_usd=ledger_total,
    )


__all__ = [
    "AgentRunNotFound",
    "TicketNotFound",
    "create_agent_run",
    "complete_agent_run",
    "list_agent_runs",
    "list_cost_ledger",
    "cost_summary",
]
