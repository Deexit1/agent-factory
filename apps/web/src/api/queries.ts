import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthContext";
import {
  approveTicket,
  fetchCostSummary,
  fetchDashboardMetrics,
  fetchTicket,
  fetchTickets,
  reportEscapedDefect,
  returnToDev,
  transitionTicket,
  type ApiError,
} from "./client";
import type {
  Approval,
  ApprovalDecision,
  ApprovalGate,
  CostSummary,
  DashboardMetrics,
  Ticket,
  TicketState,
} from "./types";

export const ticketsQueryKey = ["tickets"] as const;
export const ticketQueryKey = (id: string) => ["tickets", id] as const;

export function useTickets() {
  const actorContext = useAuth();
  return useQuery({
    queryKey: ticketsQueryKey,
    queryFn: () => fetchTickets(actorContext),
    refetchInterval: 5000,
  });
}

export function useTicket(ticketId: string | null) {
  const actorContext = useAuth();
  return useQuery({
    queryKey: ticketQueryKey(ticketId ?? ""),
    queryFn: () => fetchTicket(actorContext, ticketId as string),
    enabled: ticketId !== null,
  });
}

export function useTransitionTicket() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Ticket, ApiError, { ticketId: string; toState: TicketState }>({
    mutationFn: ({ ticketId, toState }) => transitionTicket(actorContext, ticketId, toState),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ticketsQueryKey });
    },
  });
}

export function useCostSummary(ticketId: string | null) {
  const actorContext = useAuth();
  return useQuery<CostSummary>({
    queryKey: ["cost-summary", ticketId],
    queryFn: () => fetchCostSummary(actorContext, ticketId as string),
    enabled: ticketId !== null,
  });
}

export function useApproveTicket() {
  const actorContext = useAuth();
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

export function useReturnToDev() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Ticket, ApiError, { ticketId: string; note: string }>({
    mutationFn: ({ ticketId, note }) => returnToDev(actorContext, ticketId, note),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ticketQueryKey(variables.ticketId) });
      void queryClient.invalidateQueries({ queryKey: ticketsQueryKey });
    },
  });
}

export function useDashboardMetrics() {
  const actorContext = useAuth();
  return useQuery<DashboardMetrics>({
    queryKey: ["dashboard-metrics"],
    queryFn: () => fetchDashboardMetrics(actorContext),
  });
}

export function useReportEscapedDefect() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();

  return useMutation<unknown, ApiError, { ticketId: string; note: string }>({
    mutationFn: ({ ticketId, note }) => reportEscapedDefect(actorContext, ticketId, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["dashboard-metrics"] });
    },
  });
}
