import { useFunnelCohort } from "../api/queries";

const STAGE_LABELS: Record<string, string> = {
  signup: "Signed up",
  tos_accepted: "Accepted ToS",
  key_added: "Added an LLM key",
  repo_connected: "Connected a repo",
  first_idea_created: "Created first idea",
  first_pr_merged: "First PR merged",
};

export function FunnelDashboardPage(): React.JSX.Element {
  const { data, isLoading, isError } = useFunnelCohort();
  const stages = data?.stages ?? [];
  const maxCount = Math.max(1, ...stages.map((s) => s.org_count));

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-gray-900">Onboarding funnel</h1>
      <p className="mt-1 text-sm text-gray-500">
        How many orgs (created in the last 30 days) reached each onboarding stage.
      </p>

      {isLoading && <p className="mt-4 text-sm text-gray-500">Loading…</p>}
      {isError && <p className="mt-4 text-sm text-red-600">Failed to load the funnel.</p>}

      <ul className="mt-4 flex flex-col gap-2">
        {stages.map((stage) => (
          <li key={stage.stage} data-testid={`funnel-stage-${stage.stage}`} className="text-sm">
            <div className="flex items-center justify-between">
              <span className="text-gray-700">{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
              <span className="font-semibold text-gray-900">{stage.org_count}</span>
            </div>
            <div className="mt-1 h-2 rounded bg-gray-100">
              <div
                className="h-2 rounded bg-gray-900"
                style={{ width: `${(stage.org_count / maxCount) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
