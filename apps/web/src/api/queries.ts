import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthContext";
import {
  answerPlanningQuestions,
  approveTicket,
  fetchCostSummary,
  fetchDashboardMetrics,
  fetchDescendants,
  fetchTicket,
  fetchTickets,
  reportEscapedDefect,
  returnToDev,
  transitionTicket,
  updateTask,
  type ApiError,
} from "./client";
import type {
  Approval,
  ApprovalDecision,
  ApprovalGate,
  CostSummary,
  DashboardMetrics,
  Descendants,
  Ticket,
  TicketState,
  UpdateTaskRequest,
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

export function useDescendants(ticketId: string | null) {
  const actorContext = useAuth();
  return useQuery<Descendants>({
    queryKey: ["descendants", ticketId],
    queryFn: () => fetchDescendants(actorContext, ticketId as string),
    enabled: ticketId !== null,
  });
}

export function useUpdateTask() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Ticket, ApiError, { ticketId: string; ideaId: string } & UpdateTaskRequest>({
    mutationFn: ({ ticketId, title, spec, acceptance_criteria, budget_usd }) =>
      updateTask(actorContext, ticketId, { title, spec, acceptance_criteria, budget_usd }),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["descendants", variables.ideaId] });
      void queryClient.invalidateQueries({ queryKey: ticketQueryKey(variables.ticketId) });
    },
  });
}

export function useAnswerPlanningQuestions() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();

  return useMutation<Ticket, ApiError, { ticketId: string; answers: string }>({
    mutationFn: ({ ticketId, answers }) => answerPlanningQuestions(actorContext, ticketId, answers),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ticketQueryKey(variables.ticketId) });
      void queryClient.invalidateQueries({ queryKey: ticketsQueryKey });
    },
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
