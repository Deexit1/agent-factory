import { useEffect, useState } from "react";

import { ticketEventsWsUrl } from "./client";
import type { TicketEvent } from "./types";

export interface TicketEventsFeed {
  events: TicketEvent[];
  connected: boolean;
}

export function useTicketEventsFeed(
  ticketId: string | null,
  initialEvents: TicketEvent[],
): TicketEventsFeed {
  const [liveEvents, setLiveEvents] = useState<TicketEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    setLiveEvents([]);
    setConnected(false);
    if (!ticketId) {
      return;
    }

    const socket = new WebSocket(ticketEventsWsUrl(ticketId));
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (message: MessageEvent<string>) => {
      const event = JSON.parse(message.data) as TicketEvent;
      setLiveEvents((prev) => [event, ...prev]);
    };

    return () => {
      socket.close();
    };
  }, [ticketId]);

  const liveIds = new Set(liveEvents.map((event) => event.id));
  const dedupedInitial = initialEvents.filter((event) => !liveIds.has(event.id));
  return { events: [...liveEvents, ...dedupedInitial], connected };
}
