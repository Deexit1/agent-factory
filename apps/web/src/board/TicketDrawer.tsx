import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
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
    <Sheet open onOpenChange={(open) => !open && onClose()}>
      <SheetContent
        aria-label={`Ticket ${ticket.id} details`}
        data-testid="ticket-drawer"
        data-ws-connected={connected}
        showCloseButton={false}
        className="w-96 gap-4 overflow-y-auto p-4 sm:max-w-md"
      >
        <div className="flex items-start justify-between">
          <div>
            <p className="font-mono text-xs text-muted-foreground">{ticket.id}</p>
            <SheetTitle className="text-lg">{ticket.title}</SheetTitle>
          </div>
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="Close ticket details"
          >
            ×
          </Button>
        </div>

        <div>
          <h3 className="mb-1 text-sm font-semibold text-foreground">Bounce count</h3>
          <p data-testid="bounce-count" className="text-sm text-muted-foreground">
            {ticket.bounce_count} / 3
          </p>
        </div>

        <div>
          <h3 className="mb-1 text-sm font-semibold text-foreground">Budget</h3>
          <Progress value={budgetPct} />
          <p className="mt-1 text-xs text-muted-foreground">
            ${spentUsd.toFixed(2)} / ${(ticket.budget_usd ?? 0).toFixed(2)}
          </p>
        </div>

        {descendants && descendants.items.length > 0 && costRollup && (
          <div>
            <h3 className="mb-1 text-sm font-semibold text-foreground">Rollup spend</h3>
            <p data-testid="cost-rollup" className="text-sm text-muted-foreground">
              ${costRollup.rollup_usd.toFixed(2)} across {costRollup.descendant_count} descendant
              {costRollup.descendant_count === 1 ? "" : "s"}
            </p>
          </div>
        )}

        <div>
          <h3 className="mb-1 text-sm font-semibold text-foreground">Acceptance criteria</h3>
          <ul className="flex flex-col gap-1">
            {ticket.acceptance_criteria.map((criterion) => (
              <li key={criterion.id} className="text-sm text-muted-foreground">
                <span aria-hidden="true">☑</span> {criterion.description}
                <span className="ml-1 font-mono text-xs text-muted-foreground/70">
                  ({criterion.verification})
                </span>
              </li>
            ))}
            {ticket.acceptance_criteria.length === 0 && (
              <li className="text-sm text-muted-foreground/70">None</li>
            )}
          </ul>
        </div>

        {ticket.spec && (
          <div>
            <h3 className="mb-1 text-sm font-semibold text-foreground">Spec</h3>
            <pre className="max-h-32 overflow-auto rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
              {JSON.stringify(ticket.spec, null, 2)}
            </pre>
          </div>
        )}

        {canApprove && gate === "escalation" && (
          <div className="rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold text-foreground">Escalation inbox</h3>
            <Textarea
              className="mb-2"
              placeholder="Note for the dev agent's next attempt"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              aria-label="Return to dev note"
            />
            <Button
              type="button"
              disabled={!note}
              onClick={() => returnToDev.mutate({ ticketId: ticket.id, note })}
            >
              Return to dev
            </Button>
          </div>
        )}

        {canApprove && gate === "idea" && (
          <div className="rounded-lg border p-3">
            <h3 className="mb-2 text-sm font-semibold text-foreground">Approval</h3>
            <Textarea
              className="mb-2"
              placeholder="Note (optional)"
              value={note}
              onChange={(event) => setNote(event.target.value)}
              aria-label="Approval note"
            />
            <div className="flex gap-2">
              <Button
                type="button"
                onClick={() =>
                  approve.mutate({ ticketId: ticket.id, gate, decision: "approved", note })
                }
              >
                Approve
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={() =>
                  approve.mutate({ ticketId: ticket.id, gate, decision: "rejected", note })
                }
              >
                Reject
              </Button>
            </div>
          </div>
        )}

        <div className="flex-1">
          <h3 className="mb-1 text-sm font-semibold text-foreground">Event feed</h3>
          <ul data-testid="event-feed" className="flex flex-col gap-1">
            {events.map((event) => (
              <li key={event.id} className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground">
                <span className="font-mono text-muted-foreground/70">{event.ts}</span> — {event.actor} —{" "}
                {event.kind}
              </li>
            ))}
          </ul>
        </div>
      </SheetContent>
    </Sheet>
  );
}
