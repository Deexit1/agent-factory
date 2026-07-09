import { useState } from "react";

import { useOrgStrikes, useResolveStrikeAppeal, useStrikeOrg } from "../api/queries";
import type { OrgStrike } from "../api/types";

function statusColor(status: OrgStrike["status"]): string {
  if (status === "active") return "bg-red-100 text-red-800";
  if (status === "appealed") return "bg-amber-100 text-amber-800";
  if (status === "reinstated") return "bg-green-100 text-green-800";
  return "bg-gray-200 text-gray-600";
}

function StrikeRow({ orgId, strike }: { orgId: string; strike: OrgStrike }): React.JSX.Element {
  const resolveAppeal = useResolveStrikeAppeal();

  return (
    <li
      data-testid={`org-strike-${strike.id}`}
      className="flex flex-col gap-2 rounded border border-gray-200 p-3 text-sm"
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-gray-900">{strike.reason}</span>
        <span className={`rounded px-2 py-0.5 text-xs ${statusColor(strike.status)}`}>
          {strike.status}
        </span>
      </div>
      <p className="text-xs text-gray-500">struck by {strike.struck_by}</p>
      {strike.appeal_note && (
        <p className="text-xs text-gray-600">Appeal: {strike.appeal_note}</p>
      )}
      {strike.status === "appealed" && (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() =>
              void resolveAppeal.mutateAsync({ strikeId: strike.id, decision: "reinstate", orgId })
            }
            disabled={resolveAppeal.isPending}
            className="rounded bg-green-700 px-3 py-1 text-xs font-medium text-white hover:bg-green-800 disabled:opacity-50"
          >
            Reinstate
          </button>
          <button
            type="button"
            onClick={() =>
              void resolveAppeal.mutateAsync({ strikeId: strike.id, decision: "deny", orgId })
            }
            disabled={resolveAppeal.isPending}
            className="rounded bg-gray-700 px-3 py-1 text-xs font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Deny appeal
          </button>
        </div>
      )}
    </li>
  );
}

export function OrgStrikesPage(): React.JSX.Element {
  const [orgId, setOrgId] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { data } = useOrgStrikes(orgId || null);
  const strikeOrg = useStrikeOrg();

  const handleStrike = async (): Promise<void> => {
    setError(null);
    try {
      await strikeOrg.mutateAsync({ orgId, reason });
      setReason("");
    } catch {
      setError("Could not strike this org — check the org id.");
    }
  };

  const strikes = data?.items ?? [];

  return (
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-gray-900">Org strikes</h1>
      <p className="mt-1 text-sm text-gray-500">
        Imposing a strike blocks every in-flight ticket for the org (never deletes them).
        Appeal decisions are staff-only.
      </p>

      <div className="mt-4 flex flex-col gap-2 rounded border border-gray-200 p-4">
        <input
          type="text"
          placeholder="org id"
          value={orgId}
          onChange={(event) => setOrgId(event.target.value)}
          aria-label="Org id"
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
        <input
          type="text"
          placeholder="reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label="Strike reason"
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
        <button
          type="button"
          onClick={() => void handleStrike()}
          disabled={!orgId || !reason || strikeOrg.isPending}
          className="self-start rounded bg-red-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50"
        >
          Strike org
        </button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>

      {orgId && (
        <ul className="mt-4 flex flex-col gap-2">
          {strikes.map((strike) => (
            <StrikeRow key={strike.id} orgId={orgId} strike={strike} />
          ))}
          {strikes.length === 0 && <li className="text-sm text-gray-400">No strikes for this org</li>}
        </ul>
      )}
    </main>
  );
}
