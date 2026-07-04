from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.auth import get_actor_context
from api.contracts import (
    AgentRunOut,
    CompleteAgentRunRequest,
    CostLedgerEntryOut,
    CostSummaryOut,
    CreateAgentRunRequest,
)
from api.db.session import get_db
from api.services import agent_run_service, ticket_service

router = APIRouter(
    prefix="/tickets", tags=["agent-runs"], dependencies=[Depends(get_actor_context)]
)


@router.post("/{ticket_id}/agent-runs", response_model=AgentRunOut, status_code=201)
def create_agent_run(
    ticket_id: str, request: CreateAgentRunRequest, db: Session = Depends(get_db)
) -> AgentRunOut:
    try:
        run = agent_run_service.create_agent_run(
            db,
            ticket_id,
            agent_role=request.agent_role,
            model=request.model,
            trace_id=request.trace_id,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AgentRunOut.model_validate(run)


@router.post("/{ticket_id}/agent-runs/{run_id}/complete", response_model=AgentRunOut)
def complete_agent_run(
    ticket_id: str,
    run_id: int,
    request: CompleteAgentRunRequest,
    db: Session = Depends(get_db),
) -> AgentRunOut:
    try:
        run = agent_run_service.complete_agent_run(
            db,
            ticket_id,
            run_id,
            status=request.status,
            tokens_in=request.tokens_in,
            tokens_out=request.tokens_out,
            cost_usd=request.cost_usd,
        )
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except agent_run_service.AgentRunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return AgentRunOut.model_validate(run)


@router.get("/{ticket_id}/agent-runs", response_model=list[AgentRunOut])
def list_agent_runs(ticket_id: str, db: Session = Depends(get_db)) -> list[AgentRunOut]:
    try:
        runs = agent_run_service.list_agent_runs(db, ticket_id)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [AgentRunOut.model_validate(run) for run in runs]


@router.get("/{ticket_id}/cost-ledger", response_model=list[CostLedgerEntryOut])
def list_cost_ledger(ticket_id: str, db: Session = Depends(get_db)) -> list[CostLedgerEntryOut]:
    try:
        entries = agent_run_service.list_cost_ledger(db, ticket_id)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return [CostLedgerEntryOut.model_validate(entry) for entry in entries]


@router.get("/{ticket_id}/cost-summary", response_model=CostSummaryOut)
def cost_summary(ticket_id: str, db: Session = Depends(get_db)) -> CostSummaryOut:
    try:
        return agent_run_service.cost_summary(db, ticket_id)
    except ticket_service.TicketNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
