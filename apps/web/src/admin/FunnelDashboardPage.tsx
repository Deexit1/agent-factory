import { Progress } from "@/components/ui/progress";
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
      <h1 className="text-xl font-bold text-foreground">Onboarding funnel</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        How many orgs (created in the last 30 days) reached each onboarding stage.
      </p>

      {isLoading && <p className="mt-4 text-sm text-muted-foreground">Loading…</p>}
      {isError && <p className="mt-4 text-sm text-destructive">Failed to load the funnel.</p>}

      <ul className="mt-4 flex flex-col gap-3">
        {stages.map((stage) => (
          <li key={stage.stage} data-testid={`funnel-stage-${stage.stage}`} className="text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">{STAGE_LABELS[stage.stage] ?? stage.stage}</span>
              <span className="font-semibold text-foreground">{stage.org_count}</span>
            </div>
            <Progress value={(stage.org_count / maxCount) * 100} className="mt-1" />
          </li>
        ))}
      </ul>
    </main>
  );
}
