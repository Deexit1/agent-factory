import { useDraggable } from "@dnd-kit/core";

import type { Ticket } from "../api/types";

export function TicketCard({
  ticket,
  onOpen,
}: {
  ticket: Ticket;
  onOpen: (ticketId: string) => void;
}): React.JSX.Element {
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: ticket.id,
  });

  const style = transform
    ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` }
    : undefined;

  return (
    <button
      type="button"
      ref={setNodeRef}
      style={style}
      {...listeners}
      {...attributes}
      onClick={() => onOpen(ticket.id)}
      data-testid="ticket-card"
      data-ticket-id={ticket.id}
      className={`w-full rounded-md border border-gray-200 bg-white p-3 text-left shadow-sm hover:border-gray-300 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-500 ${
        isDragging ? "opacity-50" : ""
      }`}
    >
      <p className="text-xs font-mono text-gray-400">{ticket.id}</p>
      <p className="font-medium text-gray-900">{ticket.title}</p>
      {ticket.bounce_count > 0 && (
        <span className="mt-1 inline-block rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-800">
          bounced {ticket.bounce_count}×
        </span>
      )}
    </button>
  );
}
