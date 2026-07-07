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
    <main className="flex h-screen flex-col gap-4 bg-white p-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-bold text-gray-900">Pilot Dashboard</h1>
        <button
          type="button"
          onClick={() => void downloadDashboardCsv(actorContext)}
          className="rounded bg-gray-800 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-900"
        >
          Download CSV
        </button>
      </header>

      {isLoading && <p className="text-gray-500">Loading metrics…</p>}
      {isError && <p className="text-red-600">Failed to load dashboard metrics.</p>}

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
    <div className="rounded-md border border-gray-200 p-4">
      <p className="text-xs font-semibold text-gray-500">{label}</p>
      <p className="mt-1 text-2xl font-bold text-gray-900">{value}</p>
    </div>
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
    <div className="rounded-md border border-gray-200 p-4">
      <h2 className="mb-2 text-sm font-semibold text-gray-700">{title}</h2>
      {!rows && <p className="text-sm text-gray-500">Loading…</p>}
      {rows && rows.length === 0 && <p className="text-sm text-gray-400">No spend recorded</p>}
      <ul className="flex flex-col gap-2">
        {rows?.map((row) => (
          <li key={row.label}>
            <div className="flex items-center justify-between text-xs text-gray-600">
              <span>{row.label}</span>
              <span>${row.total_usd.toFixed(2)}</span>
            </div>
            <div className="h-2 w-full rounded-full bg-gray-100">
              <div
                className="h-2 rounded-full bg-blue-500"
                style={{ width: `${(row.total_usd / maxUsd) * 100}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
