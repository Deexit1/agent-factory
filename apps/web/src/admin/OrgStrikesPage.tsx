import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useOrgStrikes, useResolveStrikeAppeal, useStrikeOrg } from "../api/queries";
import type { OrgStrike } from "../api/types";

function statusBadgeClassName(status: OrgStrike["status"]): string {
  if (status === "active") return "border-red-300 bg-red-50 text-red-800";
  if (status === "appealed") return "border-amber-300 bg-amber-50 text-amber-800";
  if (status === "reinstated") return "border-green-300 bg-green-50 text-green-800";
  return "border-transparent bg-muted text-muted-foreground";
}

function StrikeRow({ orgId, strike }: { orgId: string; strike: OrgStrike }): React.JSX.Element {
  const resolveAppeal = useResolveStrikeAppeal();

  return (
    <li
      data-testid={`org-strike-${strike.id}`}
      className="flex flex-col gap-2 rounded-lg border p-3 text-sm"
    >
      <div className="flex items-center justify-between">
        <span className="font-medium text-foreground">{strike.reason}</span>
        <Badge variant="outline" className={statusBadgeClassName(strike.status)}>
          {strike.status}
        </Badge>
      </div>
      <p className="text-xs text-muted-foreground">struck by {strike.struck_by}</p>
      {strike.appeal_note && (
        <p className="text-xs text-muted-foreground">Appeal: {strike.appeal_note}</p>
      )}
      {strike.status === "appealed" && (
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() =>
              void resolveAppeal.mutateAsync({ strikeId: strike.id, decision: "reinstate", orgId })
            }
            disabled={resolveAppeal.isPending}
          >
            Reinstate
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() =>
              void resolveAppeal.mutateAsync({ strikeId: strike.id, decision: "deny", orgId })
            }
            disabled={resolveAppeal.isPending}
          >
            Deny appeal
          </Button>
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
      <h1 className="text-xl font-bold text-foreground">Org strikes</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Imposing a strike blocks every in-flight ticket for the org (never deletes them).
        Appeal decisions are staff-only.
      </p>

      <div className="mt-4 flex flex-col gap-2 rounded-lg border p-4">
        <Input
          type="text"
          placeholder="org id"
          value={orgId}
          onChange={(event) => setOrgId(event.target.value)}
          aria-label="Org id"
        />
        <Input
          type="text"
          placeholder="reason"
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          aria-label="Strike reason"
        />
        <Button
          variant="destructive"
          onClick={() => void handleStrike()}
          disabled={!orgId || !reason || strikeOrg.isPending}
          className="self-start"
        >
          Strike org
        </Button>
        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      {orgId && (
        <ul className="mt-4 flex flex-col gap-2">
          {strikes.map((strike) => (
            <StrikeRow key={strike.id} orgId={orgId} strike={strike} />
          ))}
          {strikes.length === 0 && <li className="text-sm text-muted-foreground">No strikes for this org</li>}
        </ul>
      )}
    </main>
  );
}
