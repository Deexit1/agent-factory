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

export type EventKind =
  | "message"
  | "tool_call"
  | "test_result"
  | "transition"
  | "cost"
  | "edit"
  | "assignment";

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

export interface CostRollup {
  ticket_id: string;
  descendant_count: number;
  rollup_usd: number;
}

export interface SpendBreakdownRow {
  label: string;
  total_usd: number;
}

export interface SpendBreakdown {
  rows: SpendBreakdownRow[];
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

export interface ProfileUtilisation {
  profile: string;
  in_progress_count: number;
  max_parallel: number;
}

export interface Utilisation {
  items: ProfileUtilisation[];
}

export interface UpdateTaskRequest {
  title?: string;
  spec?: Record<string, unknown> | null;
  acceptance_criteria?: AcceptanceCriterion[];
  budget_usd?: number;
}

export interface OnboardingStatus {
  org_id: string;
  tos_accepted: boolean;
  has_provider_key: boolean;
  has_repo: boolean;
  has_idea_ticket: boolean;
}

export interface IntakeQueuedResult {
  status: "queued_for_review";
  intake_review_id: number;
  reason: string;
}

export function isIntakeQueuedResult(
  value: Ticket | IntakeQueuedResult,
): value is IntakeQueuedResult {
  return "status" in value && value.status === "queued_for_review";
}

export type IntakeReviewStatus = "pending" | "approved" | "rejected";

export interface IntakeReview {
  id: number;
  org_id: string;
  ticket_type: string;
  title: string;
  parent_id: string | null;
  budget_usd: number | null;
  repo_id: number | null;
  submitted_by: string;
  submitted_at: string;
  status: IntakeReviewStatus;
  screening_reason: string | null;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
}

export type OrgStrikeStatus = "active" | "appealed" | "reinstated" | "denied";

export interface OrgStrike {
  id: number;
  org_id: string;
  reason: string;
  struck_by: string;
  struck_at: string;
  status: OrgStrikeStatus;
  appeal_note: string | null;
  appealed_by: string | null;
  appealed_at: string | null;
  appeal_decided_by: string | null;
  appeal_decided_at: string | null;
}

export interface FunnelStageCount {
  stage: string;
  org_count: number;
}

export interface FunnelCohort {
  cohort_start: string;
  cohort_end: string;
  stages: FunnelStageCount[];
}
