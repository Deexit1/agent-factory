from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.db.models import (
    ApprovalDecision,
    ApprovalGate,
    EventKind,
    TicketState,
    TicketType,
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
    spent_usd: float
    bounce_count: int
    created_by: str


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
