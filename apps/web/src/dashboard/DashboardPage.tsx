import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAuth } from "../auth/AuthContext";
import { downloadDashboardCsv } from "../api/client";
import {
  useDashboardMetrics,
  useSpendByPromptVersion,
  useSpendByProfile,
} from "../api/queries";
import type { SpendBreakdownRow } from "../api/types";

function pct(value: number | null): string {
  return value === null ? "—" : `${Math.round(value * 100)}%`;
}

function usd(value: number | null): string {
  return value === null ? "—" : `$${value.toFixed(2)}`;
}

function hours(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)}h`;
}

export function DashboardPage(): React.JSX.Element {
  const actorContext = useAuth();
  const { data: metrics, isLoading, isError } = useDashboardMetrics();
  const { data: spendByProfile } = useSpendByProfile();
  const { data: spendByPromptVersion } = useSpendByPromptVersion();

  return (
    <main className="flex h-screen flex-col gap-4 bg-background p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-foreground">Pilot Dashboard</h1>
        <Button variant="secondary" onClick={() => void downloadDashboardCsv(actorContext)}>
          Download CSV
        </Button>
      </header>

      {isLoading && <p className="text-muted-foreground">Loading metrics…</p>}
      {isError && <p className="text-destructive">Failed to load dashboard metrics.</p>}

      {metrics && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <Tile label="First-pass QA rate" value={pct(metrics.first_pass_qa_rate)} />
          <Tile
            label="Median $ / closed ticket"
            value={usd(metrics.median_cost_per_closed_ticket_usd)}
          />
          <Tile label="Escaped defects" value={String(metrics.escaped_defects)} />
          <Tile label="Median cycle time" value={hours(metrics.median_cycle_time_hours)} />
          <Tile label="Tickets closed" value={String(metrics.tickets_closed)} />
          <Tile label="Tickets escalated" value={String(metrics.tickets_escalated)} />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <SpendBreakdownChart title="Spend by profile" rows={spendByProfile?.rows} />
        <SpendBreakdownChart title="Spend by prompt version" rows={spendByPromptVersion?.rows} />
      </div>
    </main>
  );
}

function Tile({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <Card>
      <CardContent>
        <p className="text-xs font-semibold text-muted-foreground">{label}</p>
        <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
      </CardContent>
    </Card>
  );
}

function SpendBreakdownChart({
  title,
  rows,
}: {
  title: string;
  rows: SpendBreakdownRow[] | undefined;
}): React.JSX.Element {
  const maxUsd = Math.max(1, ...(rows ?? []).map((row) => row.total_usd));

  return (
    <Card>
      <CardContent>
        <h2 className="mb-2 text-sm font-semibold text-foreground">{title}</h2>
        {!rows && <p className="text-sm text-muted-foreground">Loading…</p>}
        {rows && rows.length === 0 && <p className="text-sm text-muted-foreground">No spend recorded</p>}
        <ul className="flex flex-col gap-2">
          {rows?.map((row) => (
            <li key={row.label}>
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>{row.label}</span>
                <span>${row.total_usd.toFixed(2)}</span>
              </div>
              <Progress value={(row.total_usd / maxUsd) * 100} />
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
