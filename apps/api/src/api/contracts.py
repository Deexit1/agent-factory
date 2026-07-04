from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.db.models import (
    AgentRunStatus,
    ApprovalDecision,
    ApprovalGate,
    EventKind,
    TicketState,
    TicketType,
    UserRole,
)


class AcceptanceCriterionIn(BaseModel):
    id: str
    description: str
    verification: str


class CreateTicketRequest(BaseModel):
    type: TicketType
    title: str
    parent_id: str | None = None
    spec: dict[str, object] | None = None
    acceptance_criteria: list[AcceptanceCriterionIn] = Field(default_factory=list)
    assignee_agent: str | None = None
    budget_usd: float | None = None
    created_by: str

    @model_validator(mode="after")
    def _task_requires_acceptance_criteria(self) -> "CreateTicketRequest":
        if self.type is TicketType.TASK and not self.acceptance_criteria:
            raise ValueError("task tickets require at least one acceptance criterion")
        return self


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: TicketType
    parent_id: str | None
    state: TicketState
    title: str
    spec: dict[str, object] | None
    acceptance_criteria: list[dict[str, object]]
    assignee_agent: str | None
    budget_usd: float | None
    bounce_count: int
    created_by: str
    created_at: datetime


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    ts: datetime
    actor: str
    kind: EventKind
    payload: dict[str, object]


class TicketWithEventsOut(TicketOut):
    recent_events: list[EventOut]


class PaginatedTickets(BaseModel):
    items: list[TicketOut]
    total: int
    limit: int
    offset: int


class PaginatedEvents(BaseModel):
    items: list[EventOut]
    total: int
    limit: int
    offset: int


class TransitionRequest(BaseModel):
    to_state: TicketState
    actor: str


class CreateEventRequest(BaseModel):
    actor: str
    kind: EventKind
    payload: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _kind_not_transition(self) -> "CreateEventRequest":
        if self.kind is EventKind.TRANSITION:
            raise ValueError(
                "transition events are written by POST /tickets/{id}/transition, not this endpoint"
            )
        return self


class ApproveRequest(BaseModel):
    gate: ApprovalGate
    decision: ApprovalDecision
    note: str | None = None


class ApprovalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    gate: ApprovalGate
    decided_by: str
    decision: ApprovalDecision
    note: str | None
    ts: datetime


class CreateAgentRunRequest(BaseModel):
    agent_role: str
    model: str
    trace_id: str | None = None


class CompleteAgentRunRequest(BaseModel):
    status: AgentRunStatus
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = Field(ge=0, default=0)

    @model_validator(mode="after")
    def _status_not_running(self) -> "CompleteAgentRunRequest":
        if self.status is AgentRunStatus.RUNNING:
            raise ValueError("cannot complete a run with status=running")
        return self


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    agent_role: str
    model: str
    started_at: datetime
    ended_at: datetime | None
    status: AgentRunStatus
    tokens_in: int
    tokens_out: int
    cost_usd: float
    trace_id: str | None


class CostLedgerEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    agent_run_id: int
    provider: str
    model: str
    usd: float
    ts: datetime


class CostSummaryOut(BaseModel):
    ticket_id: str
    agent_runs_total_usd: float
    cost_ledger_total_usd: float


class DevLoginRequest(BaseModel):
    """Dev/test-only stand-in for the Google OIDC round-trip (AUTH_DEV_MODE=true)."""

    email: str
    role: UserRole | None = None


class SessionOut(BaseModel):
    token: str
    actor: str
    role: UserRole


class ReturnToDevRequest(BaseModel):
    note: str


class EscapedDefectReportIn(BaseModel):
    ticket_id: str
    note: str


class EscapedDefectReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    note: str
    reported_by: str
    ts: datetime


class DashboardMetricsOut(BaseModel):
    tickets_closed: int
    tickets_escalated: int
    first_pass_qa_rate: float | None
    median_cost_per_closed_ticket_usd: float | None
    escaped_defects: int
    median_cycle_time_hours: float | None


class CIResultWebhook(BaseModel):
    """Payload posted by the agent-pr-gate GitHub Actions workflow on completion."""

    ticket_id: str
    conclusion: Literal["success", "failure"]
    suite: str = "ci"
    raw_log: str = ""
