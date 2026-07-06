import type { TicketState } from "../api/types";

export interface BoardColumn {
  state: TicketState;
  label: string;
}

export const BOARD_COLUMNS: BoardColumn[] = [
  { state: "planning", label: "Planning" },
  { state: "ready", label: "Ready" },
  { state: "in_progress", label: "In Progress" },
  { state: "in_review", label: "In Review" },
  { state: "in_qa", label: "In QA" },
  { state: "bounced", label: "Bounced" },
  { state: "escalated", label: "Escalated" },
  { state: "done", label: "Done" },
];
