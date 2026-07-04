from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum as PgEnum
from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.session import Base


def _pg_enum(enum_cls: type[StrEnum], name: str) -> Any:
    """Native Postgres enum storing member .value ("ready") not .name ("READY")."""
    return PgEnum(enum_cls, name=name, values_callable=lambda obj: [e.value for e in obj])


class TicketType(StrEnum):
    IDEA = "idea"
    EPIC = "epic"
    TASK = "task"


class TicketState(StrEnum):
    PROPOSED = "proposed"
    EXEC_REVIEW = "exec_review"
    AWAITING_HUMAN_GO = "awaiting_human_go"
    APPROVED = "approved"
    PLANNING = "planning"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    IN_QA = "in_qa"
    DONE = "done"
    BOUNCED = "bounced"
    ESCALATED = "escalated"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class EventKind(StrEnum):
    MESSAGE = "message"
    TOOL_CALL = "tool_call"
    TEST_RESULT = "test_result"
    TRANSITION = "transition"
    COST = "cost"


class ApprovalGate(StrEnum):
    IDEA = "idea"
    BUDGET = "budget"
    DEPLOY = "deploy"
    ESCALATION = "escalation"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(primary_key=True)
    type: Mapped[TicketType] = mapped_column(_pg_enum(TicketType, "ticket_type"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"))
    state: Mapped[TicketState] = mapped_column(_pg_enum(TicketState, "ticket_state"))
    title: Mapped[str] = mapped_column()
    spec: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    acceptance_criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    assignee_agent: Mapped[str | None] = mapped_column()
    budget_usd: Mapped[float | None] = mapped_column(Numeric)
    spent_usd: Mapped[float] = mapped_column(Numeric, default=0)
    bounce_count: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[str] = mapped_column()

    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket")


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    actor: Mapped[str] = mapped_column()
    kind: Mapped[EventKind] = mapped_column(_pg_enum(EventKind, "event_kind"))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    ticket: Mapped[Ticket] = relationship(back_populates="events")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    gate: Mapped[ApprovalGate] = mapped_column(_pg_enum(ApprovalGate, "approval_gate"))
    decided_by: Mapped[str] = mapped_column()
    decision: Mapped[ApprovalDecision] = mapped_column(
        _pg_enum(ApprovalDecision, "approval_decision")
    )
    note: Mapped[str | None] = mapped_column()
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
