export type TicketType = "idea" | "epic" | "task";

export type TicketState =
  | "proposed"
  | "exec_review"
  | "awaiting_human_go"
  | "approved"
  | "planning"
  | "ready"
  | "in_progress"
  | "in_review"
  | "in_qa"
  | "done"
  | "bounced"
  | "escalated"
  | "blocked"
  | "cancelled";

export type EventKind = "message" | "tool_call" | "test_result" | "transition" | "cost" | "edit";

export type ApprovalGate = "idea" | "budget" | "deploy" | "escalation";

export type ApprovalDecision = "approved" | "rejected";

export interface AcceptanceCriterion {
  id: string;
  description: string;
  verification: string;
}

export interface Ticket {
  id: string;
  type: TicketType;
  parent_id: string | null;
  state: TicketState;
  title: string;
  spec: Record<string, unknown> | null;
  acceptance_criteria: AcceptanceCriterion[];
  assignee_agent: string | null;
  budget_usd: number | null;
  bounce_count: number;
  created_by: string;
  created_at: string;
}

export interface CostSummary {
  ticket_id: string;
  agent_runs_total_usd: number;
  cost_ledger_total_usd: number;
}

export interface DashboardMetrics {
  tickets_closed: number;
  tickets_escalated: number;
  first_pass_qa_rate: number | null;
  median_cost_per_closed_ticket_usd: number | null;
  escaped_defects: number;
  median_cycle_time_hours: number | null;
}

export interface TicketEvent {
  id: number;
  ticket_id: string;
  ts: string;
  actor: string;
  kind: EventKind;
  payload: Record<string, unknown>;
}

export interface TicketWithEvents extends Ticket {
  recent_events: TicketEvent[];
}

export interface Paginated<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface CreateTicketRequest {
  type: TicketType;
  title: string;
  parent_id?: string | null;
  spec?: Record<string, unknown> | null;
  acceptance_criteria: AcceptanceCriterion[];
  assignee_agent?: string | null;
  budget_usd?: number | null;
  created_by: string;
}

export interface Approval {
  id: number;
  ticket_id: string;
  gate: ApprovalGate;
  decided_by: string;
  decision: ApprovalDecision;
  note: string | null;
  ts: string;
}

export interface Descendants {
  items: Ticket[];
}

export interface UpdateTaskRequest {
  title?: string;
  spec?: Record<string, unknown> | null;
  acceptance_criteria?: AcceptanceCriterion[];
  budget_usd?: number;
}
