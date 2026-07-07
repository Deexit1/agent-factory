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
    IN_REVIEW = "in_review"
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
    EDIT = "edit"
    ASSIGNMENT = "assignment"
    REVIEW = "review"


class ApprovalGate(StrEnum):
    IDEA = "idea"
    BUDGET = "budget"
    DEPLOY = "deploy"
    ESCALATION = "escalation"
    REVIEW = "review"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMED_OUT = "timed_out"


class UserRole(StrEnum):
    ADMIN = "admin"
    APPROVER = "approver"
    VIEWER = "viewer"


class Org(Base):
    """Tenant. Single "default" org today (T-102 groundwork); invites, membership and
    per-org RBAC roles beyond admin/approver/viewer are T-201."""

    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    type: Mapped[TicketType] = mapped_column(_pg_enum(TicketType, "ticket_type"))
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"))
    state: Mapped[TicketState] = mapped_column(_pg_enum(TicketState, "ticket_state"))
    title: Mapped[str] = mapped_column()
    spec: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    acceptance_criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    assignee_agent: Mapped[str | None] = mapped_column()
    budget_usd: Mapped[float | None] = mapped_column(Numeric)
    bounce_count: Mapped[int] = mapped_column(default=0)
    created_by: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))

    events: Mapped[list["TicketEvent"]] = relationship(back_populates="ticket")


class TicketEvent(Base):
    __tablename__ = "ticket_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    actor: Mapped[str] = mapped_column()
    kind: Mapped[EventKind] = mapped_column(_pg_enum(EventKind, "event_kind"))
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)

    ticket: Mapped[Ticket] = relationship(back_populates="events")


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    gate: Mapped[ApprovalGate] = mapped_column(_pg_enum(ApprovalGate, "approval_gate"))
    decided_by: Mapped[str] = mapped_column()
    decision: Mapped[ApprovalDecision] = mapped_column(
        _pg_enum(ApprovalDecision, "approval_decision")
    )
    note: Mapped[str | None] = mapped_column()
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    agent_role: Mapped[str] = mapped_column()
    model: Mapped[str] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status: Mapped[AgentRunStatus] = mapped_column(
        _pg_enum(AgentRunStatus, "agent_run_status"), default=AgentRunStatus.RUNNING
    )
    tokens_in: Mapped[int] = mapped_column(default=0)
    tokens_out: Mapped[int] = mapped_column(default=0)
    cost_usd: Mapped[float] = mapped_column(Numeric, default=0)
    trace_id: Mapped[str | None] = mapped_column()


class CostLedgerEntry(Base):
    __tablename__ = "cost_ledger"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    agent_run_id: Mapped[int] = mapped_column(ForeignKey("agent_runs.id"))
    provider: Mapped[str] = mapped_column()
    model: Mapped[str] = mapped_column()
    usd: Mapped[float] = mapped_column(Numeric)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class User(Base):
    """OIDC-authenticated humans. Role defaults to viewer at first login (T-008/SPEC-006);
    promotion to approver/admin is a manual DB/admin action in Phase 1."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(primary_key=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    role: Mapped[UserRole] = mapped_column(_pg_enum(UserRole, "user_role"), default=UserRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class EscapedDefectReport(Base):
    """Manual entry: a defect found after a ticket reached `done`, missed by QA.
    Count feeds the pilot dashboard's "escaped defects" metric (docs/00-vision.md)."""

    __tablename__ = "escaped_defect_reports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    note: Mapped[str] = mapped_column()
    reported_by: Mapped[str] = mapped_column()
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
