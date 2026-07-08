from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from api.db.models import (
    AgentRunStatus,
    ApprovalDecision,
    ApprovalGate,
    EventKind,
    MergeQueueStatus,
    OrgInviteStatus,
    ProviderKeyStatus,
    RepoCIMode,
    RepoMode,
    RepoStatus,
    TicketState,
    TicketType,
    UserRole,
)
from api.tenancy import DEFAULT_ORG_ID


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
    # T-203: which connected/provisioned repo this ticket delivers to. None = the
    # pre-T-203 dogfood path (spec["repo"]/ambient GITHUB_TOKEN), unchanged.
    repo_id: int | None = None

    @model_validator(mode="after")
    def _task_requires_acceptance_criteria(self) -> "CreateTicketRequest":
        if self.type is TicketType.TASK and not self.acceptance_criteria:
            raise ValueError("task tickets require at least one acceptance criterion")
        return self

    @model_validator(mode="after")
    def _idea_requires_approved_budget(self) -> "CreateTicketRequest":
        # Ideas enter directly at `approved` in Phase 2 (docs/03-state-machine.md) — a
        # human already decided go + budget by creating it, so budget_usd must be set
        # here rather than approved separately later.
        if self.type is TicketType.IDEA and not (self.budget_usd and self.budget_usd > 0):
            raise ValueError("idea tickets require a positive budget_usd")
        return self


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
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
    repo_id: int | None = None


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
    assignee_agent: str | None = None


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
    prompt_version: str | None = None


class CompleteAgentRunRequest(BaseModel):
    status: AgentRunStatus
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = Field(ge=0, default=0)
    provider: str = "anthropic"

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
    prompt_version: str | None
    provider: str | None


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


class CostRollupOut(BaseModel):
    """T-108: cost_ledger sum for a ticket and every descendant (idea -> epic -> task)."""

    ticket_id: str
    descendant_count: int
    rollup_usd: float


class DevLoginRequest(BaseModel):
    """Dev/test-only stand-in for the Google OIDC round-trip (AUTH_DEV_MODE=true)."""

    email: str
    role: UserRole | None = None
    org_id: str = DEFAULT_ORG_ID


class SessionOut(BaseModel):
    token: str
    actor: str
    role: UserRole
    org_id: str = DEFAULT_ORG_ID
    is_platform_staff: bool = False
    impersonating: bool = False


class CreateOrgRequest(BaseModel):
    name: str


class OrgOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    created_at: datetime
    max_parallel_tickets: int | None
    llm_fallback_order: list[str] | None = None


class OrgListOut(BaseModel):
    items: list[OrgOut]


class OrgMemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    user_email: str
    role: UserRole
    created_at: datetime


class OrgMemberListOut(BaseModel):
    items: list[OrgMemberOut]


class InviteMemberRequest(BaseModel):
    email: str
    role: UserRole


class OrgInviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    email: str
    role: UserRole
    status: OrgInviteStatus
    created_at: datetime
    # No email-sending exists in this system yet — the invite creation response is
    # the only place the acceptance token is ever surfaced (a real deployment would
    # email a link instead of returning this to the inviter).
    token: str


class SwitchOrgRequest(BaseModel):
    org_id: str


class PageViewAuditRequest(BaseModel):
    path: str


class ReturnToDevRequest(BaseModel):
    note: str


class AnswerPlanningQuestionsRequest(BaseModel):
    answers: str


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    spec: dict[str, object] | None = None
    acceptance_criteria: list[AcceptanceCriterionIn] | None = None
    budget_usd: float | None = Field(default=None, gt=0)


class DescendantsOut(BaseModel):
    items: list[TicketOut]


class ProfileUtilisationOut(BaseModel):
    profile: str
    in_progress_count: int
    max_parallel: int


class UtilisationOut(BaseModel):
    items: list[ProfileUtilisationOut]


class MergeQueueEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    repo: str
    status: MergeQueueStatus
    enqueued_at: datetime
    resolved_at: datetime | None


class MergeQueueListOut(BaseModel):
    items: list[MergeQueueEntryOut]


class MergeConflictIn(BaseModel):
    actor: str
    conflicting_paths: list[str] = Field(default_factory=list)


class MergeSuccessIn(BaseModel):
    actor: str


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


class SpendBreakdownRow(BaseModel):
    label: str
    total_usd: float


class SpendBreakdownOut(BaseModel):
    rows: list[SpendBreakdownRow]


class CIResultWebhook(BaseModel):
    """Payload posted by the agent-pr-gate GitHub Actions workflow on completion."""

    ticket_id: str
    conclusion: Literal["success", "failure"]
    suite: str = "ci"
    raw_log: str = ""


class AddProviderKeyRequest(BaseModel):
    """T-202 (SPEC-202): the raw key never persists past this request — it's written
    straight to Vault; only last4/status/timestamps land in the DB."""

    provider: Literal["anthropic", "openai"]
    api_key: str = Field(min_length=8)


class ProviderKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    provider: str
    last4: str
    status: ProviderKeyStatus
    created_at: datetime
    created_by: str
    rotated_at: datetime | None


class ProviderKeyListOut(BaseModel):
    items: list[ProviderKeyOut]


class SetFallbackOrderRequest(BaseModel):
    order: list[str]


class ProviderCredentialOut(BaseModel):
    """Service-token-only: actual key material for an org's runtime dispatch. Never
    logged, never cached — apps/orchestrator fetches this fresh at agent-run start."""

    provider: str
    api_key: str


class RuntimeKeysOut(BaseModel):
    items: list[ProviderCredentialOut]


class EvalFloorOut(BaseModel):
    agent_role: str
    provider: str
    verified: bool
    floor: float | None
    opted_in: bool


class OptInEvalFloorRequest(BaseModel):
    agent_role: str
    provider: str


class RepoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    mode: RepoMode
    github_full_name: str | None
    default_branch: str | None
    ci_mode: RepoCIMode
    protected_branch_rules_verified: bool
    status: RepoStatus
    disconnected_reason: str | None
    created_at: datetime
    created_by: str


class RepoListOut(BaseModel):
    items: list[RepoOut]


class ConnectUrlOut(BaseModel):
    url: str


class ProvisionRepoRequest(BaseModel):
    name: str = Field(min_length=1)


class ExportRepoRequest(BaseModel):
    mode: Literal["transfer", "archive"]
    new_owner: str | None = None


class ExportRepoOut(BaseModel):
    mode: Literal["transfer", "archive"]
    download_url: str | None = None


class GitHubInstallTokenOut(BaseModel):
    """Service-token-only: a per-ticket, minted-on-demand installation token — never
    persisted anywhere (docs/09-saas-model.md's BYOK "never persist" doctrine, extended
    to GitHub App tokens)."""

    token: str
    expires_at: datetime
    default_branch: str


class EgressRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: str
    domain: str
    approved_by: str
    approved_at: datetime
    created_at: datetime


class EgressRuleListOut(BaseModel):
    items: list[EgressRuleOut]


class AddEgressRuleRequest(BaseModel):
    domain: str = Field(min_length=1)


class EffectiveEgressDomainsOut(BaseModel):
    """Service-token-only: the base allow-list plus this org's approved additions —
    what the orchestrator fetches at sandbox-provision time (T-204)."""

    domains: list[str]


class ArtifactCredentialOut(BaseModel):
    """T-204 (SPEC-204 AC5): a short-lived, org-prefix-scoped MinIO credential — never
    persisted, mirrors GitHubInstallTokenOut/RuntimeKeysOut's "minted on demand, held in
    memory only" doctrine."""

    access_key: str
    secret_key: str
    session_token: str
    bucket: str
    prefix: str
    expires_at: datetime
