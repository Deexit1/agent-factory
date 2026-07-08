import { useState } from "react";

import {
  useApproveTicket,
  useCostRollup,
  useCostSummary,
  useDescendants,
  useReturnToDev,
  useTicket,
} from "../api/queries";
import { useTicketEventsFeed } from "../api/useTicketEventsFeed";
import type { ApprovalGate, TicketState } from "../api/types";
import { useAuth } from "../auth/AuthContext";

const GATE_BY_STATE: Partial<Record<TicketState, ApprovalGate>> = {
  awaiting_human_go: "idea",
  escalated: "escalation",
};

export function TicketDrawer({
  ticketId,
  onClose,
}: {
  ticketId: string | null;
  onClose: () => void;
}): React.JSX.Element | null {
  const { role } = useAuth();
  const { data: ticket } = useTicket(ticketId);
  const { data: costSummary } = useCostSummary(ticketId);
  const { data: descendants } = useDescendants(ticketId);
  const { data: costRollup } = useCostRollup(ticketId);
  const approve = useApproveTicket();
  const returnToDev = useReturnToDev();
  const [note, setNote] = useState("");

  const { events, connected } = useTicketEventsFeed(ticketId, ticket?.recent_events ?? []);

  if (!ticketId || !ticket) {
    return null;
  }

  const gate = GATE_BY_STATE[ticket.state];
  const canApprove = gate !== undefined && (role === "approver" || role === "owner");
  // The budget bar reflects cost_ledger — the documented source of truth for $/ticket
  // (docs/02-data-model.md) — not a separately-tracked running total on the ticket itself.
  const spentUsd = costSummary?.cost_ledger_total_usd ?? 0;
  const budgetPct =
    ticket.budget_usd && ticket.budget_usd > 0 ? Math.min(100, (spentUsd / ticket.budget_usd) * 100) : 0;

  return (
    <aside
      role="dialog"
      aria-label={`Ticket ${ticket.id} details`}
      data-testid="ticket-drawer"
      data-ws-connected={connected}
      className="fixed inset-y-0 right-0 flex w-96 flex-col gap-4 overflow-y-auto border-l border-gray-200 bg-white p-4 shadow-xl"
    >
      <div className="flex items-start justify-between">
        <div>
          <p className="font-mono text-xs text-gray-400">{ticket.id}</p>
          <h2 className="text-lg font-semibold text-gray-900">{ticket.title}</h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close ticket details"
          className="text-gray-400 hover:text-gray-700"
        >
          ×
        </button>
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold text-gray-700">Bounce count</h3>
        <p data-testid="bounce-count" className="text-sm text-gray-600">
          {ticket.bounce_count} / 3
        </p>
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold text-gray-700">Budget</h3>
        <div className="h-2 w-full rounded-full bg-gray-100">
          <div
            className="h-2 rounded-full bg-blue-500"
            style={{ width: `${budgetPct}%` }}
            role="progressbar"
            aria-valuenow={Math.round(budgetPct)}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
        <p className="mt-1 text-xs text-gray-500">
          ${spentUsd.toFixed(2)} / ${(ticket.budget_usd ?? 0).toFixed(2)}
        </p>
      </div>

      {descendants && descendants.items.length > 0 && costRollup && (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-gray-700">Rollup spend</h3>
          <p data-testid="cost-rollup" className="text-sm text-gray-600">
            ${costRollup.rollup_usd.toFixed(2)} across {costRollup.descendant_count} descendant
            {costRollup.descendant_count === 1 ? "" : "s"}
          </p>
        </div>
      )}

      <div>
        <h3 className="mb-1 text-sm font-semibold text-gray-700">Acceptance criteria</h3>
        <ul className="flex flex-col gap-1">
          {ticket.acceptance_criteria.map((criterion) => (
            <li key={criterion.id} className="text-sm text-gray-600">
              <span aria-hidden="true">☑</span> {criterion.description}
              <span className="ml-1 font-mono text-xs text-gray-400">
                ({criterion.verification})
              </span>
            </li>
          ))}
          {ticket.acceptance_criteria.length === 0 && (
            <li className="text-sm text-gray-400">None</li>
          )}
        </ul>
      </div>

      {ticket.spec && (
        <div>
          <h3 className="mb-1 text-sm font-semibold text-gray-700">Spec</h3>
          <pre className="max-h-32 overflow-auto rounded bg-gray-50 p-2 text-xs text-gray-600">
            {JSON.stringify(ticket.spec, null, 2)}
          </pre>
        </div>
      )}

      {canApprove && gate === "escalation" && (
        <div className="rounded-md border border-gray-200 p-3">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Escalation inbox</h3>
          <textarea
            className="mb-2 w-full rounded border border-gray-300 p-2 text-sm"
            placeholder="Note for the dev agent's next attempt"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            aria-label="Return to dev note"
          />
          <button
            type="button"
            disabled={!note}
            className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            onClick={() => returnToDev.mutate({ ticketId: ticket.id, note })}
          >
            Return to dev
          </button>
        </div>
      )}

      {canApprove && gate === "idea" && (
        <div className="rounded-md border border-gray-200 p-3">
          <h3 className="mb-2 text-sm font-semibold text-gray-700">Approval</h3>
          <textarea
            className="mb-2 w-full rounded border border-gray-300 p-2 text-sm"
            placeholder="Note (optional)"
            value={note}
            onChange={(event) => setNote(event.target.value)}
            aria-label="Approval note"
          />
          <div className="flex gap-2">
            <button
              type="button"
              className="rounded bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700"
              onClick={() =>
                approve.mutate({ ticketId: ticket.id, gate, decision: "approved", note })
              }
            >
              Approve
            </button>
            <button
              type="button"
              className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700"
              onClick={() =>
                approve.mutate({ ticketId: ticket.id, gate, decision: "rejected", note })
              }
            >
              Reject
            </button>
          </div>
        </div>
      )}

      <div className="flex-1">
        <h3 className="mb-1 text-sm font-semibold text-gray-700">Event feed</h3>
        <ul data-testid="event-feed" className="flex flex-col gap-1">
          {events.map((event) => (
            <li key={event.id} className="rounded bg-gray-50 p-2 text-xs text-gray-600">
              <span className="font-mono text-gray-400">{event.ts}</span> — {event.actor} —{" "}
              {event.kind}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
