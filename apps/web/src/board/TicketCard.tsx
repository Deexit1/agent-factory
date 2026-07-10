import { useDraggable } from "@dnd-kit/core";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
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

  // dnd-kit's ref/listeners/attributes must live on the actual draggable DOM node —
  // shadcn's generated Card isn't wrapped in React.forwardRef (Base UI/React-19-shaped
  // templates on this React-18 app), so wrapping this button in <Card> would silently
  // break the drag ref. Applying Card's own utility-class recipe directly instead.
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
      className={cn(
        "w-full rounded-xl border bg-card p-3 text-left text-card-foreground shadow-sm ring-1 ring-foreground/10 transition-colors hover:border-ring/50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring",
        isDragging && "opacity-50",
      )}
    >
      <p className="font-mono text-xs text-muted-foreground">{ticket.id}</p>
      <p className="font-medium text-foreground">{ticket.title}</p>
      {ticket.bounce_count > 0 && (
        <Badge variant="outline" className="mt-1 border-amber-300 bg-amber-50 text-amber-800">
          bounced {ticket.bounce_count}×
        </Badge>
      )}
    </button>
  );
}
