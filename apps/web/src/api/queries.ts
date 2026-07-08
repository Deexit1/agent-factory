import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthContext";
import {
  acceptInvite,
  addProviderKey,
  answerPlanningQuestions,
  approveTicket,
  createOrg,
  deleteProviderKey,
  disconnectRepo,
  exportRepo,
  fetchConnectUrl,
  fetchCostRollup,
  fetchCostSummary,
  fetchDashboardMetrics,
  fetchDescendants,
  fetchEvalFloor,
  fetchMyOrgs,
  fetchOrgMembers,
  fetchProviderKeys,
  fetchRepos,
  fetchSpendByPromptVersion,
  fetchSpendByProfile,
  fetchTicket,
  fetchTickets,
  fetchUtilisation,
  healthCheckProviderKeys,
  impersonateOrg,
  inviteMember,
  optInEvalFloor,
  provisionRepo,
  reportEscapedDefect,
  reportPageViewAudit,
  returnToDev,
  rotateProviderKey,
  setFallbackOrder,
  switchOrg,
  transitionTicket,
  updateTask,
  type ApiError,
  type EvalFloor,
  type ExportRepoResult,
  type Org,
  type OrgInvite,
  type OrgMember,
  type ProviderKey,
  type ProviderName,
  type Repo,
  type Session,
} from "./client";
import type {
  Approval,
  ApprovalDecision,
  ApprovalGate,
  CostRollup,
  CostSummary,
  DashboardMetrics,
  Descendants,
  SpendBreakdown,
  Ticket,
  TicketState,
  UpdateTaskRequest,
  Utilisation,
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

export function useCostRollup(ticketId: string | null) {
  const actorContext = useAuth();
  return useQuery<CostRollup>({
    queryKey: ["cost-rollup", ticketId],
    queryFn: () => fetchCostRollup(actorContext, ticketId as string),
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

export function useSpendByProfile() {
  const actorContext = useAuth();
  return useQuery<SpendBreakdown>({
    queryKey: ["spend-by-profile"],
    queryFn: () => fetchSpendByProfile(actorContext),
  });
}

export function useSpendByPromptVersion() {
  const actorContext = useAuth();
  return useQuery<SpendBreakdown>({
    queryKey: ["spend-by-prompt-version"],
    queryFn: () => fetchSpendByPromptVersion(actorContext),
  });
}

export function useUtilisation() {
  const actorContext = useAuth();
  return useQuery<Utilisation>({
    queryKey: ["utilisation"],
    queryFn: () => fetchUtilisation(actorContext),
    refetchInterval: 5000,
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

export function useMyOrgs() {
  const actorContext = useAuth();
  return useQuery<{ items: Org[] }>({
    queryKey: ["orgs-mine"],
    queryFn: () => fetchMyOrgs(actorContext),
  });
}

export function useSwitchOrg() {
  const actorContext = useAuth();
  return useMutation<Session, ApiError, { orgId: string }>({
    mutationFn: ({ orgId }) => switchOrg(actorContext, orgId),
  });
}

export function useCreateOrg() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Org, ApiError, { name: string }>({
    mutationFn: ({ name }) => createOrg(actorContext, name),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["orgs-mine"] });
    },
  });
}

export function useOrgMembers(orgId: string | null) {
  const actorContext = useAuth();
  return useQuery<{ items: OrgMember[] }>({
    queryKey: ["org-members", orgId],
    queryFn: () => fetchOrgMembers(actorContext, orgId as string),
    enabled: orgId !== null,
  });
}

export function useInviteMember() {
  const actorContext = useAuth();
  return useMutation<OrgInvite, ApiError, { orgId: string; email: string; role: string }>({
    mutationFn: ({ orgId, email, role }) => inviteMember(actorContext, orgId, { email, role }),
  });
}

export function useAcceptInvite() {
  const actorContext = useAuth();
  return useMutation<OrgMember, ApiError, { token: string }>({
    mutationFn: ({ token }) => acceptInvite(actorContext, token),
  });
}

export function useImpersonateOrg() {
  const actorContext = useAuth();
  return useMutation<Session, ApiError, { orgId: string }>({
    mutationFn: ({ orgId }) => impersonateOrg(actorContext, orgId),
  });
}

export function usePageViewAudit() {
  const actorContext = useAuth();
  return (path: string) => {
    void reportPageViewAudit(actorContext, path).catch(() => {
      // Best-effort — a failed audit POST shouldn't block navigation.
    });
  };
}

export const providerKeysQueryKey = (orgId: string | null) => ["provider-keys", orgId] as const;

export function useProviderKeys(orgId: string | null) {
  const actorContext = useAuth();
  return useQuery<{ items: ProviderKey[] }>({
    queryKey: providerKeysQueryKey(orgId),
    queryFn: () => fetchProviderKeys(actorContext, orgId as string),
    enabled: orgId !== null,
    refetchInterval: 15000,
  });
}

export function useAddProviderKey() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<
    ProviderKey,
    ApiError,
    { orgId: string; provider: ProviderName; api_key: string }
  >({
    mutationFn: ({ orgId, ...body }) => addProviderKey(actorContext, orgId, body),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: providerKeysQueryKey(variables.orgId) });
    },
  });
}

export function useRotateProviderKey() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<
    ProviderKey,
    ApiError,
    { orgId: string; provider: ProviderName; api_key: string }
  >({
    mutationFn: ({ orgId, ...body }) => rotateProviderKey(actorContext, orgId, body),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: providerKeysQueryKey(variables.orgId) });
    },
  });
}

export function useDeleteProviderKey() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<unknown, ApiError, { orgId: string; provider: ProviderName }>({
    mutationFn: ({ orgId, provider }) => deleteProviderKey(actorContext, orgId, provider),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: providerKeysQueryKey(variables.orgId) });
    },
  });
}

export function useSetFallbackOrder() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<{ items: ProviderKey[] }, ApiError, { orgId: string; order: string[] }>({
    mutationFn: ({ orgId, order }) => setFallbackOrder(actorContext, orgId, order),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: providerKeysQueryKey(variables.orgId) });
    },
  });
}

export function useHealthCheckProviderKeys() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<{ items: ProviderKey[] }, ApiError, { orgId: string }>({
    mutationFn: ({ orgId }) => healthCheckProviderKeys(actorContext, orgId),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: providerKeysQueryKey(variables.orgId) });
    },
  });
}

export function useEvalFloor(orgId: string | null, agentRole: string, provider: string) {
  const actorContext = useAuth();
  return useQuery<EvalFloor>({
    queryKey: ["eval-floor", orgId, agentRole, provider],
    queryFn: () => fetchEvalFloor(actorContext, orgId as string, agentRole, provider),
    enabled: orgId !== null,
  });
}

export function useOptInEvalFloor() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<EvalFloor, ApiError, { orgId: string; agent_role: string; provider: string }>({
    mutationFn: ({ orgId, ...body }) => optInEvalFloor(actorContext, orgId, body),
    onSuccess: (data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ["eval-floor", variables.orgId, data.agent_role, data.provider],
      });
    },
  });
}

export const reposQueryKey = (orgId: string | null) => ["repos", orgId] as const;

export function useRepos(orgId: string | null) {
  const actorContext = useAuth();
  return useQuery<{ items: Repo[] }>({
    queryKey: reposQueryKey(orgId),
    queryFn: () => fetchRepos(actorContext, orgId as string),
    enabled: orgId !== null,
    refetchInterval: 15000,
  });
}

export function useConnectUrl() {
  const actorContext = useAuth();
  return useMutation<{ url: string }, ApiError, { orgId: string }>({
    mutationFn: ({ orgId }) => fetchConnectUrl(actorContext, orgId),
  });
}

export function useProvisionRepo() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Repo, ApiError, { orgId: string; name: string }>({
    mutationFn: ({ orgId, name }) => provisionRepo(actorContext, orgId, { name }),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: reposQueryKey(variables.orgId) });
    },
  });
}

export function useExportRepo() {
  const actorContext = useAuth();
  return useMutation<
    ExportRepoResult,
    ApiError,
    { orgId: string; repoId: number; mode: "transfer" | "archive"; new_owner?: string }
  >({
    mutationFn: ({ orgId, repoId, ...body }) => exportRepo(actorContext, orgId, repoId, body),
  });
}

export function useDisconnectRepo() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Repo, ApiError, { orgId: string; repoId: number }>({
    mutationFn: ({ orgId, repoId }) => disconnectRepo(actorContext, orgId, repoId),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: reposQueryKey(variables.orgId) });
    },
  });
}
