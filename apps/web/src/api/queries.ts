import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../auth/AuthContext";
import {
  acceptInvite,
  acceptTos,
  addProviderKey,
  answerPlanningQuestions,
  appealStrike,
  approveIntakeReview,
  approveTicket,
  createOrg,
  createTicket,
  deleteProviderKey,
  disconnectRepo,
  exportRepo,
  fetchConnectUrl,
  fetchCostRollup,
  fetchCostSummary,
  fetchDashboardMetrics,
  fetchDescendants,
  fetchEvalFloor,
  fetchFunnelCohort,
  fetchIntakeReviews,
  fetchMyOrgs,
  fetchOnboardingStatus,
  fetchOrgMembers,
  fetchOrgStrikes,
  fetchProviderKeys,
  fetchRepos,
  fetchSpendByPromptVersion,
  fetchSpendByProfile,
  fetchTicket,
  fetchTickets,
  fetchTos,
  fetchUtilisation,
  healthCheckProviderKeys,
  impersonateOrg,
  inviteMember,
  optInEvalFloor,
  provisionRepo,
  rejectIntakeReview,
  reportEscapedDefect,
  reportPageViewAudit,
  resolveStrikeAppeal,
  returnToDev,
  rotateProviderKey,
  setFallbackOrder,
  strikeOrg,
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
  CreateTicketRequest,
  DashboardMetrics,
  Descendants,
  FunnelCohort,
  IntakeQueuedResult,
  IntakeReview,
  OnboardingStatus,
  OrgStrike,
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

export function useTos() {
  const actorContext = useAuth();
  return useQuery<{ version: string; policy_text: string }>({
    queryKey: ["tos"],
    queryFn: () => fetchTos(actorContext),
  });
}

export function useCreateOrg() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Org, ApiError, { name: string; tosVersion: string }>({
    mutationFn: ({ name, tosVersion }) => createOrg(actorContext, name, tosVersion),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["orgs-mine"] });
    },
  });
}

export function useAcceptTos() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<unknown, ApiError, { orgId: string; tosVersion: string }>({
    mutationFn: ({ orgId, tosVersion }) => acceptTos(actorContext, orgId, tosVersion),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: onboardingStatusQueryKey(variables.orgId) });
    },
  });
}

export const onboardingStatusQueryKey = (orgId: string | null) =>
  ["onboarding-status", orgId] as const;

export function useOnboardingStatus(orgId: string | null) {
  const actorContext = useAuth();
  return useQuery<OnboardingStatus>({
    queryKey: onboardingStatusQueryKey(orgId),
    queryFn: () => fetchOnboardingStatus(actorContext, orgId as string),
    enabled: orgId !== null,
  });
}

export function useCreateTicket() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Ticket | IntakeQueuedResult, ApiError, CreateTicketRequest>({
    mutationFn: (body) => createTicket(actorContext, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ticketsQueryKey });
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

// --- T-206 (SPEC-206): intake review queue ---

export const intakeReviewsQueryKey = (status: string) => ["intake-reviews", status] as const;

export function useIntakeReviews(status: string = "pending") {
  const actorContext = useAuth();
  return useQuery<{ items: IntakeReview[] }>({
    queryKey: intakeReviewsQueryKey(status),
    queryFn: () => fetchIntakeReviews(actorContext, status),
    refetchInterval: 15000,
  });
}

export function useApproveIntakeReview() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<Ticket, ApiError, { reviewId: number; note?: string }>({
    mutationFn: ({ reviewId, note }) => approveIntakeReview(actorContext, reviewId, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["intake-reviews"] });
    },
  });
}

export function useRejectIntakeReview() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<IntakeReview, ApiError, { reviewId: number; note?: string }>({
    mutationFn: ({ reviewId, note }) => rejectIntakeReview(actorContext, reviewId, note),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["intake-reviews"] });
    },
  });
}

// --- T-206 (SPEC-206): org strikes + appeal ---

export const orgStrikesQueryKey = (orgId: string | null) => ["org-strikes", orgId] as const;

export function useOrgStrikes(orgId: string | null) {
  const actorContext = useAuth();
  return useQuery<{ items: OrgStrike[] }>({
    queryKey: orgStrikesQueryKey(orgId),
    queryFn: () => fetchOrgStrikes(actorContext, orgId as string),
    enabled: orgId !== null,
    refetchInterval: 15000,
  });
}

export function useStrikeOrg() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<OrgStrike, ApiError, { orgId: string; reason: string }>({
    mutationFn: ({ orgId, reason }) => strikeOrg(actorContext, orgId, reason),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: orgStrikesQueryKey(variables.orgId) });
    },
  });
}

export function useAppealStrike() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<OrgStrike, ApiError, { orgId: string; strikeId: number; note: string }>({
    mutationFn: ({ orgId, strikeId, note }) => appealStrike(actorContext, orgId, strikeId, note),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: orgStrikesQueryKey(variables.orgId) });
    },
  });
}

export function useResolveStrikeAppeal() {
  const actorContext = useAuth();
  const queryClient = useQueryClient();
  return useMutation<
    OrgStrike,
    ApiError,
    { strikeId: number; decision: "reinstate" | "deny"; orgId?: string }
  >({
    mutationFn: ({ strikeId, decision }) => resolveStrikeAppeal(actorContext, strikeId, decision),
    onSuccess: (_data, variables) => {
      if (variables.orgId) {
        void queryClient.invalidateQueries({ queryKey: orgStrikesQueryKey(variables.orgId) });
      }
    },
  });
}

// --- T-206 (SPEC-206): funnel dashboard ---

export function useFunnelCohort(start?: string, end?: string) {
  const actorContext = useAuth();
  return useQuery<FunnelCohort>({
    queryKey: ["funnel-cohort", start, end],
    queryFn: () => fetchFunnelCohort(actorContext, start, end),
  });
}
