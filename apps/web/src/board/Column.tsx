import { useDroppable } from "@dnd-kit/core";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { Ticket } from "../api/types";
import type { BoardColumn } from "./columns";
import { TicketCard } from "./TicketCard";

export function Column({
  column,
  tickets,
  onOpenTicket,
}: {
  column: BoardColumn;
  tickets: Ticket[];
  onOpenTicket: (ticketId: string) => void;
}): React.JSX.Element {
  const { setNodeRef, isOver } = useDroppable({ id: column.state });

  return (
    <section
      aria-label={`${column.label} column`}
      className="flex w-64 shrink-0 flex-col gap-2 rounded-xl bg-muted/50 p-3"
    >
      <h2 className="flex items-center justify-between text-sm font-semibold text-foreground">
        {column.label}
        <Badge variant="secondary">{tickets.length}</Badge>
      </h2>
      {/* dnd-kit's droppable ref must live on this native div — see TicketCard.tsx's
          comment for why it isn't wrapped in a non-forwardRef shadcn component. */}
      <div
        ref={setNodeRef}
        data-testid={`column-${column.state}`}
        className={cn(
          "flex min-h-[120px] flex-col gap-2 rounded-lg p-1 transition-colors",
          isOver && "bg-primary/5 ring-2 ring-primary/30",
        )}
      >
        {tickets.map((ticket) => (
          <TicketCard key={ticket.id} ticket={ticket} onOpen={onOpenTicket} />
        ))}
      </div>
    </section>
  );
}
