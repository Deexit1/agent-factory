import {
  DndContext,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { useState } from "react";

import type { TicketState } from "../api/types";
import { useTickets, useTransitionTicket } from "../api/queries";
import { BOARD_COLUMNS } from "./columns";
import { Column } from "./Column";
import { ErrorBanner } from "./ErrorBanner";
import { TicketDrawer } from "./TicketDrawer";

export function BoardPage(): React.JSX.Element {
  const { data, isLoading, isError } = useTickets();
  const transition = useTransitionTicket();
  const [openTicketId, setOpenTicketId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // A minimum drag distance before dnd-kit takes over, so a plain click on a card
  // still reaches its onClick handler instead of being swallowed as a zero-distance drag.
  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 8 } }));

  const handleDragEnd = (event: DragEndEvent): void => {
    const ticketId = String(event.active.id);
    const toState = event.over?.id as TicketState | undefined;
    if (!toState) {
      return;
    }

    const ticket = data?.items.find((t) => t.id === ticketId);
    if (!ticket || ticket.state === toState) {
      return;
    }

    transition.mutate(
      { ticketId, toState },
      {
        onError: (mutationError) => {
          setError(mutationError.message);
        },
      },
    );
  };

  return (
    <main className="flex h-full flex-col gap-4 bg-white p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Agent Factory — Board</h1>
      </header>

      {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

      {isLoading && <p className="text-gray-500">Loading tickets…</p>}
      {isError && <p className="text-red-600">Failed to load tickets.</p>}

      {data && (
        <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
          <div className="flex flex-1 gap-4 overflow-x-auto">
            {BOARD_COLUMNS.map((column) => (
              <Column
                key={column.state}
                column={column}
                tickets={data.items.filter((ticket) => ticket.state === column.state)}
                onOpenTicket={setOpenTicketId}
              />
            ))}
          </div>
        </DndContext>
      )}

      <TicketDrawer ticketId={openTicketId} onClose={() => setOpenTicketId(null)} />
    </main>
  );
}
