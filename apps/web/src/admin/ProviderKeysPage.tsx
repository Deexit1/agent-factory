import { useState } from "react";

import { ArrowDown, ArrowUp } from "lucide-react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { ProviderName } from "../api/client";
import {
  useAddProviderKey,
  useDeleteProviderKey,
  useEvalFloor,
  useHealthCheckProviderKeys,
  useOptInEvalFloor,
  useProviderKeys,
  useRotateProviderKey,
  useSetFallbackOrder,
} from "../api/queries";
import { useAuth } from "../auth/AuthContext";

const PROVIDERS: ProviderName[] = ["anthropic", "openai"];
const AGENT_ROLES = ["dev", "planner", "delivery-manager", "review"];

function statusBadgeClassName(status: string): string {
  if (status === "active") return "border-green-300 bg-green-50 text-green-800";
  if (status === "revoked") return "border-transparent bg-muted text-muted-foreground";
  return "border-red-300 bg-red-50 text-red-800";
}

function EvalFloorRow({
  orgId,
  provider,
  agentRole,
}: {
  orgId: string;
  provider: string;
  agentRole: string;
}): React.JSX.Element | null {
  const { data: floor } = useEvalFloor(orgId, agentRole, provider);
  const optIn = useOptInEvalFloor();

  if (!floor || floor.verified) {
    return null;
  }

  return (
    <div className="flex items-center justify-between gap-2 py-1 text-xs">
      <span className="text-amber-700">
        {agentRole}: unverified quality on {provider}
        {floor.opted_in ? " (opted in)" : ""}
      </span>
      {!floor.opted_in && (
        <Button
          size="xs"
          variant="outline"
          onClick={() => void optIn.mutateAsync({ orgId, agent_role: agentRole, provider })}
          disabled={optIn.isPending}
          className="border-amber-400 text-amber-700 hover:bg-amber-50"
        >
          Opt in
        </Button>
      )}
    </div>
  );
}

export function ProviderKeysPage(): React.JSX.Element {
  const { orgId, role } = useAuth();
  const isOwner = role === "owner";
  const { data: keys } = useProviderKeys(orgId);
  const addKey = useAddProviderKey();
  const rotateKey = useRotateProviderKey();
  const deleteKey = useDeleteProviderKey();
  const setFallbackOrder = useSetFallbackOrder();
  const healthCheck = useHealthCheckProviderKeys();

  const [provider, setProvider] = useState<ProviderName>("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!orgId) {
    return <p className="p-4 text-muted-foreground">Loading…</p>;
  }

  const items = keys?.items ?? [];
  const anyUnhealthy = items.some((k) => k.status !== "active");

  const handleAdd = async (): Promise<void> => {
    setError(null);
    try {
      const existing = items.find((k) => k.provider === provider);
      if (existing) {
        await rotateKey.mutateAsync({ orgId, provider, api_key: apiKey });
      } else {
        await addKey.mutateAsync({ orgId, provider, api_key: apiKey });
      }
      setApiKey("");
    } catch {
      setError("Could not save key — check it's a live, valid key for this provider.");
    }
  };

  const moveProvider = (from: number, to: number): void => {
    const order = items.map((k) => k.provider);
    if (to < 0 || to >= order.length) return;
    const moved = order.splice(from, 1)[0];
    if (moved === undefined) return;
    order.splice(to, 0, moved);
    void setFallbackOrder.mutateAsync({ orgId, order });
  };

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-xl font-bold text-foreground">Provider keys (BYOK)</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Bring your own LLM provider keys. Keys are stored in Vault — never in this app's
          database, logs, or events. Only the last 4 characters are ever shown here.
        </p>
      </div>

      {anyUnhealthy && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>
            At least one provider key is not active. Agent runs using that provider are paused
            until it's fixed.
          </AlertDescription>
        </Alert>
      )}

      <ul className="flex flex-col gap-2">
        {items.map((key, index) => (
          <li key={key.provider} className="flex flex-col gap-1 rounded-lg border p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-medium">{key.provider}</span>
              <Badge variant="outline" className={statusBadgeClassName(key.status)}>
                {key.status}
              </Badge>
            </div>
            <span className="text-xs text-muted-foreground">••••{key.last4}</span>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Button
                size="icon-xs"
                variant="outline"
                onClick={() => moveProvider(index, index - 1)}
                disabled={index === 0 || !isOwner}
                aria-label={`Move ${key.provider} up in fallback order`}
              >
                <ArrowUp />
              </Button>
              <Button
                size="icon-xs"
                variant="outline"
                onClick={() => moveProvider(index, index + 1)}
                disabled={index === items.length - 1 || !isOwner}
                aria-label={`Move ${key.provider} down in fallback order`}
              >
                <ArrowDown />
              </Button>
              {isOwner && (
                <Button
                  variant="link"
                  size="sm"
                  onClick={() => void deleteKey.mutateAsync({ orgId, provider: key.provider as ProviderName })}
                  disabled={deleteKey.isPending}
                  className="ml-auto h-auto p-0 text-destructive"
                >
                  Delete
                </Button>
              )}
            </div>
            {AGENT_ROLES.map((agentRole) => (
              <EvalFloorRow
                key={agentRole}
                orgId={orgId}
                provider={key.provider}
                agentRole={agentRole}
              />
            ))}
          </li>
        ))}
        {items.length === 0 && (
          <li className="text-sm text-muted-foreground">No provider keys configured yet.</li>
        )}
      </ul>

      {isOwner && (
        <div className="flex flex-col gap-2 rounded-lg border p-4">
          <h2 className="text-sm font-semibold text-foreground">Add or rotate a key</h2>
          <Select value={provider} onValueChange={(value) => value && setProvider(value as ProviderName)}>
            <SelectTrigger aria-label="Provider" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PROVIDERS.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="password"
            placeholder="API key"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            aria-label="API key"
          />
          <Button
            onClick={() => void handleAdd()}
            disabled={!apiKey || addKey.isPending || rotateKey.isPending}
            className="self-start"
          >
            Save key
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button
            variant="link"
            size="sm"
            onClick={() => void healthCheck.mutateAsync({ orgId })}
            disabled={healthCheck.isPending}
            className="mt-2 h-auto self-start p-0 text-xs text-muted-foreground"
          >
            Re-check key health
          </Button>
        </div>
      )}
    </div>
  );
}
