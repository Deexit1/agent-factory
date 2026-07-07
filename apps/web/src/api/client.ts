import type {
  Approval,
  ApprovalDecision,
  ApprovalGate,
  CostRollup,
  CostSummary,
  CreateTicketRequest,
  DashboardMetrics,
  Descendants,
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
  role: "viewer" | "approver" | "admin";
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
): Promise<Ticket> {
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

export function devLogin(email: string, role: string): Promise<Session> {
  return request(
    "/auth/dev-login",
    { token: null },
    {
      method: "POST",
      body: JSON.stringify({ email, role }),
    },
  );
}

export function googleLoginUrl(): string {
  return `${API_URL}/auth/login`;
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
