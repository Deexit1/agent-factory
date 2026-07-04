export type TicketType = "idea" | "epic" | "task";

export type TicketState =
  | "proposed"
  | "exec_review"
  | "awaiting_human_go"
  | "approved"
  | "planning"
  | "ready"
  | "in_progress"
  | "in_qa"
  | "done"
  | "bounced"
  | "escalated"
  | "blocked"
  | "cancelled";

export type EventKind = "message" | "tool_call" | "test_result" | "transition" | "cost";

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
  spent_usd: number;
  bounce_count: number;
  created_by: string;
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
