import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useActor } from "../auth/ActorContext";
import {
  approveTicket,
  fetchTicket,
  fetchTickets,
  transitionTicket,
  type ApiError,
} from "./client";
import type { Approval, ApprovalDecision, ApprovalGate, Ticket, TicketState } from "./types";

export const ticketsQueryKey = ["tickets"] as const;
export const ticketQueryKey = (id: string) => ["tickets", id] as const;

export function useTickets() {
  const actorContext = useActor();
  return useQuery({
    queryKey: ticketsQueryKey,
    queryFn: () => fetchTickets(actorContext),
    refetchInterval: 5000,
  });
}

export function useTicket(ticketId: string | null) {
  const actorContext = useActor();
  return useQuery({
    queryKey: ticketQueryKey(ticketId ?? ""),
    queryFn: () => fetchTicket(actorContext, ticketId as string),
    enabled: ticketId !== null,
  });
}

export function useTransitionTicket() {
  const actorContext = useActor();
  const queryClient = useQueryClient();

  return useMutation<Ticket, ApiError, { ticketId: string; toState: TicketState }>({
    mutationFn: ({ ticketId, toState }) => transitionTicket(actorContext, ticketId, toState),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ticketsQueryKey });
    },
  });
}

export function useApproveTicket() {
  const actorContext = useActor();
  const queryClient = useQueryClient();

  return useMutation<
    Approval,
    ApiError,
    { ticketId: string; gate: ApprovalGate; decision: ApprovalDecision; note?: string }
  >({
    mutationFn: ({ ticketId, ...body }) => approveTicket(actorContext, ticketId, body),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ticketQueryKey(variables.ticketId) });
    },
  });
}
