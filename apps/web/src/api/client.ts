import type {
  Approval,
  ApprovalDecision,
  ApprovalGate,
  CostRollup,
  CostSummary,
  CreateTicketRequest,
  DashboardMetrics,
  Descendants,
  FunnelCohort,
  IntakeQueuedResult,
  IntakeReview,
  OnboardingStatus,
  OrgStrike,
  Paginated,
  SpendBreakdown,
  Ticket,
  TicketEvent,
  TicketState,
  TicketWithEvents,
  UpdateTaskRequest,
  Utilisation,
} from "./types";

const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface ActorContext {
  token: string | null;
  actor?: string | null;
  role?: string | null;
}

export interface Session {
  token: string;
  actor: string;
  role: "viewer" | "approver" | "member" | "owner";
  org_id: string;
  is_platform_staff: boolean;
  impersonating: boolean;
}

export interface Org {
  id: string;
  name: string;
  created_at: string;
  max_parallel_tickets: number | null;
}

export interface OrgMember {
  id: number;
  org_id: string;
  user_email: string;
  role: "viewer" | "approver" | "member" | "owner";
  created_at: string;
}

export interface OrgInvite {
  id: number;
  org_id: string;
  email: string;
  role: "viewer" | "approver" | "member" | "owner";
  status: "pending" | "accepted" | "revoked";
  created_at: string;
  token: string;
}

export type ProviderName = "anthropic" | "openai";

export interface ProviderKey {
  id: number;
  org_id: string;
  provider: string;
  last4: string;
  status: "active" | "invalid" | "revoked";
  created_at: string;
  created_by: string;
  rotated_at: string | null;
}

export interface EvalFloor {
  agent_role: string;
  provider: string;
  verified: boolean;
  floor: number | null;
  opted_in: boolean;
}

export type RepoMode = "connected" | "provisioned";
export type RepoCIMode = "platform_runners" | "customer_ci";
export type RepoStatus = "active" | "disconnected" | "exported";

export interface Repo {
  id: number;
  org_id: string;
  mode: RepoMode;
  github_full_name: string | null;
  default_branch: string | null;
  ci_mode: RepoCIMode;
  protected_branch_rules_verified: boolean;
  status: RepoStatus;
  disconnected_reason: string | null;
  created_at: string;
  created_by: string;
}

export interface ExportRepoResult {
  mode: "transfer" | "archive";
  download_url: string | null;
}

async function request<T>(
  path: string,
  actorContext: ActorContext,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(actorContext.token ? { Authorization: `Bearer ${actorContext.token}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : response.statusText;
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function fetchTickets(
  actorContext: ActorContext,
  params: { state?: TicketState; type?: string; assigneeAgent?: string } = {},
): Promise<Paginated<Ticket>> {
  const query = new URLSearchParams();
  if (params.state) query.set("state", params.state);
  if (params.type) query.set("type", params.type);
  if (params.assigneeAgent) query.set("assignee_agent", params.assigneeAgent);
  query.set("limit", "100");

  return request(`/tickets?${query.toString()}`, actorContext);
}

export function fetchTicket(
  actorContext: ActorContext,
  ticketId: string,
): Promise<TicketWithEvents> {
  return request(`/tickets/${ticketId}`, actorContext);
}

export function createTicket(
  actorContext: ActorContext,
  body: CreateTicketRequest,
): Promise<Ticket | IntakeQueuedResult> {
  // T-206 (SPEC-206 AC2): a 201 response is a real Ticket; a 202 response means the
  // submission was routed to the staff intake-review queue instead — callers branch on
  // isIntakeQueuedResult(). A 403/422 (stale ToS / hard-rejected content) still throws
  // ApiError via request()'s normal error path.
  return request("/tickets", actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function transitionTicket(
  actorContext: ActorContext,
  ticketId: string,
  toState: TicketState,
): Promise<Ticket> {
  return request(`/tickets/${ticketId}/transition`, actorContext, {
    method: "POST",
    body: JSON.stringify({ to_state: toState, actor: actorContext.actor ?? "" }),
  });
}

export function approveTicket(
  actorContext: ActorContext,
  ticketId: string,
  body: { gate: ApprovalGate; decision: ApprovalDecision; note?: string },
): Promise<Approval> {
  return request(`/tickets/${ticketId}/approve`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchMe(token: string): Promise<Session> {
  return request("/auth/me", { token });
}

export function devLogin(email: string, role: string, orgId?: string): Promise<Session> {
  return request(
    "/auth/dev-login",
    { token: null },
    {
      method: "POST",
      body: JSON.stringify({ email, role, ...(orgId ? { org_id: orgId } : {}) }),
    },
  );
}

export function switchOrg(actorContext: ActorContext, orgId: string): Promise<Session> {
  return request("/auth/switch-org", actorContext, {
    method: "POST",
    body: JSON.stringify({ org_id: orgId }),
  });
}

export function googleLoginUrl(): string {
  return `${API_URL}/auth/login`;
}

export function fetchMyOrgs(actorContext: ActorContext): Promise<{ items: Org[] }> {
  return request("/orgs/mine", actorContext);
}

export function fetchTos(actorContext: ActorContext): Promise<{ version: string; policy_text: string }> {
  return request("/tos", actorContext);
}

export function createOrg(
  actorContext: ActorContext,
  name: string,
  tosVersion: string,
): Promise<Org> {
  return request("/orgs", actorContext, {
    method: "POST",
    body: JSON.stringify({ name, tos_version: tosVersion }),
  });
}

export function acceptTos(
  actorContext: ActorContext,
  orgId: string,
  tosVersion: string,
): Promise<void> {
  return request(`/orgs/${orgId}/tos/accept`, actorContext, {
    method: "POST",
    body: JSON.stringify({ tos_version: tosVersion }),
  });
}

export function fetchOnboardingStatus(
  actorContext: ActorContext,
  orgId: string,
): Promise<OnboardingStatus> {
  return request(`/orgs/${orgId}/onboarding-status`, actorContext);
}

export function inviteMember(
  actorContext: ActorContext,
  orgId: string,
  body: { email: string; role: string },
): Promise<OrgInvite> {
  return request(`/orgs/${orgId}/invites`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function acceptInvite(actorContext: ActorContext, token: string): Promise<OrgMember> {
  return request(`/orgs/invites/${token}/accept`, actorContext, { method: "POST" });
}

export function fetchOrgMembers(
  actorContext: ActorContext,
  orgId: string,
): Promise<{ items: OrgMember[] }> {
  return request(`/orgs/${orgId}/members`, actorContext);
}

export function impersonateOrg(actorContext: ActorContext, orgId: string): Promise<Session> {
  return request(`/admin/orgs/${orgId}/impersonate`, actorContext, { method: "POST" });
}

export function reportPageViewAudit(actorContext: ActorContext, path: string): Promise<unknown> {
  return request("/admin/audit/page-view", actorContext, {
    method: "POST",
    body: JSON.stringify({ path }),
  });
}

export function fetchProviderKeys(
  actorContext: ActorContext,
  orgId: string,
): Promise<{ items: ProviderKey[] }> {
  return request(`/orgs/${orgId}/provider-keys`, actorContext);
}

export function addProviderKey(
  actorContext: ActorContext,
  orgId: string,
  body: { provider: ProviderName; api_key: string },
): Promise<ProviderKey> {
  return request(`/orgs/${orgId}/provider-keys`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function rotateProviderKey(
  actorContext: ActorContext,
  orgId: string,
  body: { provider: ProviderName; api_key: string },
): Promise<ProviderKey> {
  return request(`/orgs/${orgId}/provider-keys/${body.provider}/rotate`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function deleteProviderKey(
  actorContext: ActorContext,
  orgId: string,
  provider: ProviderName,
): Promise<void> {
  return request(`/orgs/${orgId}/provider-keys/${provider}`, actorContext, {
    method: "DELETE",
  });
}

export function setFallbackOrder(
  actorContext: ActorContext,
  orgId: string,
  order: string[],
): Promise<{ items: ProviderKey[] }> {
  return request(`/orgs/${orgId}/provider-keys/fallback-order`, actorContext, {
    method: "PUT",
    body: JSON.stringify({ order }),
  });
}

export function healthCheckProviderKeys(
  actorContext: ActorContext,
  orgId: string,
): Promise<{ items: ProviderKey[] }> {
  return request(`/orgs/${orgId}/provider-keys/health-check`, actorContext, { method: "POST" });
}

export function fetchEvalFloor(
  actorContext: ActorContext,
  orgId: string,
  agentRole: string,
  provider: string,
): Promise<EvalFloor> {
  const query = new URLSearchParams({ agent_role: agentRole, provider });
  return request(`/orgs/${orgId}/eval-floors?${query.toString()}`, actorContext);
}

export function optInEvalFloor(
  actorContext: ActorContext,
  orgId: string,
  body: { agent_role: string; provider: string },
): Promise<EvalFloor> {
  return request(`/orgs/${orgId}/eval-floors/opt-in`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchRepos(actorContext: ActorContext, orgId: string): Promise<{ items: Repo[] }> {
  return request(`/orgs/${orgId}/repos`, actorContext);
}

export function fetchConnectUrl(
  actorContext: ActorContext,
  orgId: string,
): Promise<{ url: string }> {
  return request(`/orgs/${orgId}/repos/connect-url`, actorContext);
}

export function provisionRepo(
  actorContext: ActorContext,
  orgId: string,
  body: { name: string },
): Promise<Repo> {
  return request(`/orgs/${orgId}/repos/provisioned`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function exportRepo(
  actorContext: ActorContext,
  orgId: string,
  repoId: number,
  body: { mode: "transfer" | "archive"; new_owner?: string },
): Promise<ExportRepoResult> {
  return request(`/orgs/${orgId}/repos/${repoId}/export`, actorContext, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function disconnectRepo(
  actorContext: ActorContext,
  orgId: string,
  repoId: number,
): Promise<Repo> {
  return request(`/orgs/${orgId}/repos/${repoId}`, actorContext, { method: "DELETE" });
}

export function fetchCostSummary(
  actorContext: ActorContext,
  ticketId: string,
): Promise<CostSummary> {
  return request(`/tickets/${ticketId}/cost-summary`, actorContext);
}

export function fetchCostRollup(
  actorContext: ActorContext,
  ticketId: string,
): Promise<CostRollup> {
  return request(`/tickets/${ticketId}/cost-rollup`, actorContext);
}

export function fetchTicketEvents(
  actorContext: ActorContext,
  ticketId: string,
): Promise<Paginated<TicketEvent>> {
  return request(`/tickets/${ticketId}/events`, actorContext);
}

export function ticketEventsWsUrl(ticketId: string): string {
  const wsBase = API_URL.replace(/^http/, "ws");
  return `${wsBase}/ws/tickets/${ticketId}`;
}

export function returnToDev(
  actorContext: ActorContext,
  ticketId: string,
  note: string,
): Promise<Ticket> {
  return request(`/tickets/${ticketId}/return-to-dev`, actorContext, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function fetchDashboardMetrics(actorContext: ActorContext): Promise<DashboardMetrics> {
  return request("/dashboard/metrics", actorContext);
}

export function reportEscapedDefect(
  actorContext: ActorContext,
  ticketId: string,
  note: string,
): Promise<unknown> {
  return request("/dashboard/escaped-defects", actorContext, {
    method: "POST",
    body: JSON.stringify({ ticket_id: ticketId, note }),
  });
}

export function fetchDescendants(
  actorContext: ActorContext,
  ticketId: string,
): Promise<Descendants> {
  return request(`/tickets/${ticketId}/descendants`, actorContext);
}

export function updateTask(
  actorContext: ActorContext,
  ticketId: string,
  body: UpdateTaskRequest,
): Promise<Ticket> {
  return request(`/tickets/${ticketId}`, actorContext, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function answerPlanningQuestions(
  actorContext: ActorContext,
  ticketId: string,
  answers: string,
): Promise<Ticket> {
  return request(`/tickets/${ticketId}/answer-planning-questions`, actorContext, {
    method: "POST",
    body: JSON.stringify({ answers }),
  });
}

export function fetchUtilisation(actorContext: ActorContext): Promise<Utilisation> {
  return request("/capability-registry/utilisation", actorContext);
}

export function fetchSpendByProfile(actorContext: ActorContext): Promise<SpendBreakdown> {
  return request("/dashboard/spend-by-profile", actorContext);
}

export function fetchSpendByPromptVersion(actorContext: ActorContext): Promise<SpendBreakdown> {
  return request("/dashboard/spend-by-prompt-version", actorContext);
}

export async function downloadDashboardCsv(actorContext: ActorContext): Promise<void> {
  const response = await fetch(`${API_URL}/dashboard/export.csv`, {
    headers: actorContext.token ? { Authorization: `Bearer ${actorContext.token}` } : {},
  });
  if (!response.ok) {
    throw new ApiError(response.status, response.statusText);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "pilot-dashboard.csv";
  link.click();
  URL.revokeObjectURL(url);
}

// --- T-206 (SPEC-206): intake review queue, org strikes/appeal, funnel dashboard ---

export function fetchIntakeReviews(
  actorContext: ActorContext,
  status: string = "pending",
): Promise<{ items: IntakeReview[] }> {
  const query = new URLSearchParams({ status });
  return request(`/admin/intake-reviews?${query.toString()}`, actorContext);
}

export function approveIntakeReview(
  actorContext: ActorContext,
  reviewId: number,
  note?: string,
): Promise<Ticket> {
  return request(`/admin/intake-reviews/${reviewId}/approve`, actorContext, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function rejectIntakeReview(
  actorContext: ActorContext,
  reviewId: number,
  note?: string,
): Promise<IntakeReview> {
  return request(`/admin/intake-reviews/${reviewId}/reject`, actorContext, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function fetchOrgStrikes(
  actorContext: ActorContext,
  orgId: string,
): Promise<{ items: OrgStrike[] }> {
  return request(`/orgs/${orgId}/strikes`, actorContext);
}

export function strikeOrg(
  actorContext: ActorContext,
  orgId: string,
  reason: string,
): Promise<OrgStrike> {
  return request(`/admin/orgs/${orgId}/strikes`, actorContext, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

export function appealStrike(
  actorContext: ActorContext,
  orgId: string,
  strikeId: number,
  note: string,
): Promise<OrgStrike> {
  return request(`/orgs/${orgId}/strikes/${strikeId}/appeal`, actorContext, {
    method: "POST",
    body: JSON.stringify({ note }),
  });
}

export function resolveStrikeAppeal(
  actorContext: ActorContext,
  strikeId: number,
  decision: "reinstate" | "deny",
): Promise<OrgStrike> {
  return request(`/admin/strikes/${strikeId}/resolve-appeal`, actorContext, {
    method: "POST",
    body: JSON.stringify({ decision }),
  });
}

export function fetchFunnelCohort(
  actorContext: ActorContext,
  start?: string,
  end?: string,
): Promise<FunnelCohort> {
  const query = new URLSearchParams();
  if (start) query.set("start", start);
  if (end) query.set("end", end);
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return request(`/dashboard/funnel${suffix}`, actorContext);
}
