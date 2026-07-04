import { useDroppable } from "@dnd-kit/core";

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
      className="flex w-64 shrink-0 flex-col gap-2 rounded-lg bg-gray-50 p-3"
    >
      <h2 className="flex items-center justify-between text-sm font-semibold text-gray-700">
        {column.label}
        <span className="rounded-full bg-gray-200 px-2 py-0.5 text-xs text-gray-600">
          {tickets.length}
        </span>
      </h2>
      <div
        ref={setNodeRef}
        data-testid={`column-${column.state}`}
        className={`flex min-h-[120px] flex-col gap-2 rounded-md p-1 transition-colors ${
          isOver ? "bg-blue-50 ring-2 ring-blue-300" : ""
        }`}
      >
        {tickets.map((ticket) => (
          <TicketCard key={ticket.id} ticket={ticket} onOpen={onOpenTicket} />
        ))}
      </div>
    </section>
  );
}
