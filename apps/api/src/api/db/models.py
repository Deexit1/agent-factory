from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy import Enum as PgEnum
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


class MergeQueueStatus(StrEnum):
    QUEUED = "queued"
    MERGED = "merged"
    CONFLICT = "conflict"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    BUDGET_EXCEEDED = "budget_exceeded"
    TIMED_OUT = "timed_out"


class UserRole(StrEnum):
    """T-201: per-org membership role (owner/approver/member/viewer) — renamed from the
    T-102-era admin/approver/viewer (owner replaces admin; member is new). Lives on
    `OrgMember.role`, not `User` — a user's role is per-org now, not global."""

    OWNER = "owner"
    APPROVER = "approver"
    MEMBER = "member"
    VIEWER = "viewer"


class Org(Base):
    """Tenant. Real multi-org membership/invites/RBAC land in T-201 (`OrgMember`,
    `OrgInvite`); T-102 only seeded the single "default" org and org_id groundwork."""

    __tablename__ = "orgs"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    # T-201: only the one quota that's actually enforceable today (mirrors
    # capability_registry.yaml's repo_concurrency_limit, scoped per-org instead of
    # global). Sandbox-minutes/day usage metering is still not enforced (T-105's own
    # disclosed gap) — but org-scoped egress IS real as of T-204 (see OrgEgressRule
    # below), so this column no longer needs to carry that caveat for egress.
    max_parallel_tickets: Mapped[int | None] = mapped_column(default=None)
    # T-202: ordered provider names, e.g. ["anthropic", "openai"] — a single small
    # per-org setting, not a separate ordering table (same judgment as
    # max_parallel_tickets above). None/empty means "whatever ProviderKey rows exist,
    # anthropic first".
    llm_fallback_order: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
    # T-205 (SPEC-205): billing_plans.PLANS key. "free" needs no card and is never
    # touched by Razorpay — razorpay_customer_id/subscription_id stay null for it.
    plan: Mapped[str] = mapped_column(default="free")
    # A scheduled downgrade — set by billing_service.set_plan, applied for real by
    # apply_pending_plan_sweep once current_period_end passes (AC3: tightens at period
    # end, not immediately). Upgrades never touch these; they apply straight to `plan`.
    pending_plan: Mapped[str | None] = mapped_column(default=None)
    pending_plan_effective_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None
    )
    # Nullable rather than backfilled: lazily initialized (org.created_at + 30d) the
    # first time billing_service touches an org, so no migration-time backfill sweep is
    # needed for orgs created before this column existed.
    current_period_end: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None
    )
    billing_status: Mapped[str] = mapped_column(default="active")  # active/past_due/paused
    dunning_grace_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None
    )
    razorpay_customer_id: Mapped[str | None] = mapped_column(default=None)
    razorpay_subscription_id: Mapped[str | None] = mapped_column(default=None)


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
    # T-203: which connected/provisioned repo this ticket delivers to. Nullable, never
    # backfilled — historical/dogfood tickets predate the repo registry and keep
    # targeting the platform monorepo via the ambient GITHUB_TOKEN/spec.repo path.
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repos.id"), default=None)

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
    prompt_version: Mapped[str | None] = mapped_column()
    # T-202: which provider actually served this run — nullable since historical rows
    # predate BYOK and stay unbackfilled (the old hard-coded "anthropic" literal in
    # cost_ledger was accurate for every run that ever occurred before this ticket).
    provider: Mapped[str | None] = mapped_column()


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


class UsageEvent(Base):
    """T-205 (SPEC-205): a sibling to `cost_ledger`, not an overload of `ticket_events`
    (whose `kind` is a Postgres enum — adding a value would force the documented
    two-migration ADD-VALUE-then-USE split for no benefit, and billing math wants a
    typed numeric column, not JSONB parsing). Only `kind="sandbox_minutes"` is written
    today, by `apps/orchestrator`'s `SandboxClaudeCodeRunner` after each real sandbox
    lease. `agent_run_minutes` needs no row here — it's derived at metering time from
    `agent_runs.started_at`/`ended_at`, which already exists and already carries
    `org_id`."""

    __tablename__ = "usage_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    kind: Mapped[str] = mapped_column()
    quantity: Mapped[float] = mapped_column(Numeric)
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class BillingUsageReport(Base):
    """T-205 (SPEC-205 AC1): the nightly metering job's own idempotency ledger — one row
    per `(org_id, report_date, kind)` it has ever reported to Razorpay. A second run for
    a day that already has a row is a no-op by construction: the unique constraint is a
    second line of defense, the job's own upsert-if-absent check is the first."""

    __tablename__ = "billing_usage_reports"
    __table_args__ = (
        UniqueConstraint(
            "org_id", "report_date", "kind", name="uq_billing_usage_reports_org_date_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    report_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column()
    quantity: Mapped[float] = mapped_column(Numeric)
    razorpay_addon_id: Mapped[str | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class User(Base):
    """OIDC-authenticated humans. T-201: role and org membership moved to
    `OrgMember` — a user's role is per-org now, not a single global value. Role still
    defaults to viewer at an org's first-login auto-join (T-008/SPEC-006 behavior,
    preserved via `user_service.get_or_create_user`'s ADMIN_EMAILS-seeded bootstrap).
    `is_platform_staff` is a separate, cross-org concept (impersonation, T-201) — not
    an org role."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(primary_key=True)
    is_platform_staff: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class OrgMember(Base):
    """T-201: a user's role within one org — replaces the old global `User.role`/
    `User.org_id` columns. A user can belong to multiple orgs, one row each."""

    __tablename__ = "org_members"
    __table_args__ = (UniqueConstraint("org_id", "user_email", name="uq_org_members_org_user"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    user_email: Mapped[str] = mapped_column(ForeignKey("users.email"))
    role: Mapped[UserRole] = mapped_column(_pg_enum(UserRole, "user_role"), default=UserRole.VIEWER)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class OrgInviteStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REVOKED = "revoked"


class OrgInvite(Base):
    """T-201: an owner-issued invite (email + role) into one org. `token` is a random,
    unguessable acceptance credential — not the ticket-facing service token."""

    __tablename__ = "org_invites"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    email: Mapped[str] = mapped_column()
    role: Mapped[UserRole] = mapped_column(_pg_enum(UserRole, "user_role"), default=UserRole.VIEWER)
    invited_by: Mapped[str] = mapped_column()
    token: Mapped[str] = mapped_column(unique=True)
    status: Mapped[OrgInviteStatus] = mapped_column(
        _pg_enum(OrgInviteStatus, "org_invite_status"), default=OrgInviteStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class StaffAuditLog(Base):
    """T-201 AC5: every platform-staff impersonation action, including one row per
    page view while impersonating an org — the frontend posts one on every route
    change while `ActorContext.impersonating` is true."""

    __tablename__ = "staff_audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    staff_email: Mapped[str] = mapped_column()
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    action: Mapped[str] = mapped_column()
    path: Mapped[str | None] = mapped_column()
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class MergeQueueEntry(Base):
    """SPEC-106: one FIFO slot per ticket whose CI went green. `in_qa -> done` is
    gated on a `merged` entry existing for the ticket (T-107) — CI-green alone no
    longer completes a ticket; the merge-queue processor
    (apps/orchestrator/src/orchestrator/merge_queue.py) does, after a real
    rebase-and-retest against the target branch."""

    __tablename__ = "merge_queue_entries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id"))
    repo: Mapped[str] = mapped_column()
    status: Mapped[MergeQueueStatus] = mapped_column(
        _pg_enum(MergeQueueStatus, "merge_queue_status"), default=MergeQueueStatus.QUEUED
    )
    enqueued_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


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


class ProviderKeyStatus(StrEnum):
    ACTIVE = "active"
    INVALID = "invalid"
    REVOKED = "revoked"


class ProviderKey(Base):
    """T-202 (SPEC-202): audit-only metadata for an org's BYOK provider key. The secret
    itself lives ONLY in Vault (tenants/<org_id>/llm/<provider>) — this row never holds
    key material, only what's needed to render the UI and gate dispatch: which
    providers an org has configured, their validation status, and last-4 for display."""

    __tablename__ = "provider_keys"
    __table_args__ = (
        UniqueConstraint("org_id", "provider", name="uq_provider_keys_org_provider"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    provider: Mapped[str] = mapped_column()  # "anthropic" | "openai"
    last4: Mapped[str] = mapped_column()
    status: Mapped[ProviderKeyStatus] = mapped_column(
        _pg_enum(ProviderKeyStatus, "provider_key_status"), default=ProviderKeyStatus.ACTIVE
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[str] = mapped_column()
    rotated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ProviderEvalOptIn(Base):
    """T-202 AC5: an org's explicit opt-in to use a (agent_role, provider) combo that
    has no green eval floor yet ("unverified quality"). Org/role/provider-scoped — a
    standing decision that persists across many future runs, not a per-ticket event
    (unlike TicketEvent) and not a staff action (unlike StaffAuditLog)."""

    __tablename__ = "provider_eval_opt_ins"
    __table_args__ = (
        UniqueConstraint("org_id", "agent_role", "provider", name="uq_eval_opt_in"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    agent_role: Mapped[str] = mapped_column()
    provider: Mapped[str] = mapped_column()
    opted_in_by: Mapped[str] = mapped_column()
    ts: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class RepoMode(StrEnum):
    CONNECTED = "connected"
    PROVISIONED = "provisioned"


class RepoCIMode(StrEnum):
    PLATFORM_RUNNERS = "platform_runners"
    CUSTOMER_CI = "customer_ci"


class RepoStatus(StrEnum):
    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    EXPORTED = "exported"


class Repo(Base):
    """T-203 (SPEC-203): a repo registry entry — either a customer repo connected via
    the GitHub App install flow (`mode=connected`) or a repo we created under the
    platform's own org from a template (`mode=provisioned`). Never holds a GitHub
    token/private key; those are minted on demand (github_app_client.py) and never
    persisted here or anywhere else (docs/09-saas-model.md's BYOK "never persist"
    doctrine, extended verbatim to installation tokens)."""

    __tablename__ = "repos"
    __table_args__ = (
        UniqueConstraint("org_id", "github_repo_id", name="uq_repos_org_github_repo_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    mode: Mapped[RepoMode] = mapped_column(_pg_enum(RepoMode, "repo_mode"))
    github_installation_id: Mapped[int] = mapped_column()
    # Nullable until the connect/provision call resolves the real GitHub-side repo.
    github_repo_id: Mapped[int | None] = mapped_column()
    github_full_name: Mapped[str | None] = mapped_column()
    clone_url: Mapped[str | None] = mapped_column()
    default_branch: Mapped[str | None] = mapped_column()
    ci_mode: Mapped[RepoCIMode] = mapped_column(
        _pg_enum(RepoCIMode, "repo_ci_mode"), default=RepoCIMode.PLATFORM_RUNNERS
    )
    protected_branch_rules_verified: Mapped[bool] = mapped_column(default=False)
    protected_branch_rules_verified_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )
    status: Mapped[RepoStatus] = mapped_column(
        _pg_enum(RepoStatus, "repo_status"), default=RepoStatus.ACTIVE
    )
    disconnected_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    disconnected_reason: Mapped[str | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    created_by: Mapped[str] = mapped_column()


class TosAcceptance(Base):
    """T-206 (SPEC-206 AC3): one row per (org, ToS version) an owner has accepted.
    Bundled into org creation (`org_service.create_org` writes this in the same
    transaction as the `Org` row) since every domain table carries `org_id` and an org
    doesn't exist before wizard step 1. Re-acceptance for a version bump is a separate
    `POST /orgs/{id}/tos/accept` call. Mirrors `ProviderEvalOptIn`'s "one row per
    (tenant, versioned-dimension)" shape."""

    __tablename__ = "tos_acceptances"
    __table_args__ = (
        UniqueConstraint("org_id", "tos_version", name="uq_tos_acceptances_org_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    accepted_by: Mapped[str] = mapped_column()
    tos_version: Mapped[str] = mapped_column()
    accepted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))


class IntakeReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class IntakeReview(Base):
    """T-206 (SPEC-206 AC2): one row per idea/task submission that didn't pass straight
    through `intake_screening_service.screen_content` — a hard-reject (status=rejected,
    decided immediately by the screener) or a borderline case awaiting platform-staff
    review (status=pending). No unique constraint: repeated hard-rejects each get their
    own audit row, by design. A `pass` verdict writes no row here at all, so this table
    stays small and every row is either a rejection reason or a real review decision —
    mirrors `OrgInvite`'s/`MergeQueueEntry`'s "one table, multiple statuses" shape."""

    __tablename__ = "intake_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    ticket_type: Mapped[str] = mapped_column()  # "idea" | "task"
    title: Mapped[str] = mapped_column()
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tickets.id"), default=None)
    spec: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    acceptance_criteria: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list)
    budget_usd: Mapped[float | None] = mapped_column(Numeric, default=None)
    repo_id: Mapped[int | None] = mapped_column(ForeignKey("repos.id"), default=None)
    submitted_by: Mapped[str] = mapped_column()
    submitted_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    # Plain string, not a native Postgres enum (matches Org.billing_status's own
    # precedent) — avoids the documented two-migration ADD-VALUE-then-USE split.
    status: Mapped[str] = mapped_column(default=IntakeReviewStatus.PENDING.value)
    screening_reason: Mapped[str | None] = mapped_column(default=None)
    decided_by: Mapped[str | None] = mapped_column(default=None)
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), default=None)
    decision_note: Mapped[str | None] = mapped_column(default=None)


class OrgStrikeStatus(StrEnum):
    ACTIVE = "active"
    APPEALED = "appealed"
    REINSTATED = "reinstated"
    DENIED = "denied"


class OrgStrike(Base):
    """T-206 (SPEC-206 AC5): a platform-staff-imposed abuse strike. Imposing a strike
    reuses `billing_service.pause_org_for_nonpayment`'s force-block loop verbatim
    (`ticket_repository.list_in_flight_by_org` + `ticket_service.request_transition` to
    BLOCKED) — the actor is `human:{staff_email}`, already covered by
    `state_machine.is_human_actor`, so no new `_SYSTEM_BLOCK_ACTORS` entry is needed.
    Appeal *request* is owner-initiated (self-service); appeal *decision* is
    platform-staff-only — an org cannot un-strike itself."""

    __tablename__ = "org_strikes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    reason: Mapped[str] = mapped_column()
    struck_by: Mapped[str] = mapped_column()
    struck_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    # Plain string, not a native Postgres enum — same rationale as IntakeReview.status.
    status: Mapped[str] = mapped_column(default=OrgStrikeStatus.ACTIVE.value)
    appeal_note: Mapped[str | None] = mapped_column(default=None)
    appealed_by: Mapped[str | None] = mapped_column(default=None)
    appealed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), default=None)
    appeal_decided_by: Mapped[str | None] = mapped_column(default=None)
    appeal_decided_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), default=None
    )


class OrgEgressRule(Base):
    """T-204 (SPEC-204 AC3): one org-approved addition to the sandbox egress
    allow-list, on top of `sandbox.config.DEFAULT_ALLOWED_DOMAINS` (the base list every
    org gets). Only platform staff may create/remove rows here — same
    `ActorContext.is_platform_staff` gate `routers/admin.py` already established for
    T-201 impersonation, no new auth concept."""

    __tablename__ = "org_egress_rules"
    __table_args__ = (
        UniqueConstraint("org_id", "domain", name="uq_org_egress_rules_org_domain"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(ForeignKey("orgs.id"))
    domain: Mapped[str] = mapped_column()
    approved_by: Mapped[str] = mapped_column()
    approved_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True))
