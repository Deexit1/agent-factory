import { useState } from "react";

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

function statusColor(status: string): string {
  if (status === "active") return "bg-green-100 text-green-800";
  if (status === "revoked") return "bg-gray-200 text-gray-600";
  return "bg-red-100 text-red-800";
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
        <button
          type="button"
          onClick={() => void optIn.mutateAsync({ orgId, agent_role: agentRole, provider })}
          disabled={optIn.isPending}
          className="rounded border border-amber-400 px-2 py-0.5 text-amber-700 hover:bg-amber-50 disabled:opacity-50"
        >
          Opt in
        </button>
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
    return <p className="p-4 text-gray-500">Loading…</p>;
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
    <main className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-bold text-gray-900">Provider keys (BYOK)</h1>
      <p className="mt-1 text-sm text-gray-500">
        Bring your own LLM provider keys. Keys are stored in Vault — never in this app's
        database, logs, or events. Only the last 4 characters are ever shown here.
      </p>

      {anyUnhealthy && (
        <div role="alert" className="mt-4 rounded border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          At least one provider key is not active. Agent runs using that provider are paused
          until it's fixed.
        </div>
      )}

      <ul className="mt-4 flex flex-col gap-2">
        {items.map((key, index) => (
          <li
            key={key.provider}
            className="flex flex-col gap-1 rounded border border-gray-200 p-3 text-sm"
          >
            <div className="flex items-center justify-between">
              <span className="font-medium">{key.provider}</span>
              <span className={`rounded px-2 py-0.5 text-xs ${statusColor(key.status)}`}>
                {key.status}
              </span>
            </div>
            <span className="text-xs text-gray-500">••••{key.last4}</span>
            <div className="flex items-center gap-2 text-xs text-gray-500">
              <button
                type="button"
                onClick={() => moveProvider(index, index - 1)}
                disabled={index === 0 || !isOwner}
                className="rounded border border-gray-300 px-1.5 disabled:opacity-30"
                aria-label={`Move ${key.provider} up in fallback order`}
              >
                ↑
              </button>
              <button
                type="button"
                onClick={() => moveProvider(index, index + 1)}
                disabled={index === items.length - 1 || !isOwner}
                className="rounded border border-gray-300 px-1.5 disabled:opacity-30"
                aria-label={`Move ${key.provider} down in fallback order`}
              >
                ↓
              </button>
              {isOwner && (
                <button
                  type="button"
                  onClick={() => void deleteKey.mutateAsync({ orgId, provider: key.provider as ProviderName })}
                  disabled={deleteKey.isPending}
                  className="ml-auto text-red-600 hover:underline disabled:opacity-50"
                >
                  Delete
                </button>
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
          <li className="text-sm text-gray-500">No provider keys configured yet.</li>
        )}
      </ul>

      {isOwner && (
        <div className="mt-6 flex flex-col gap-2 rounded border border-gray-200 p-4">
          <h2 className="text-sm font-semibold text-gray-900">Add or rotate a key</h2>
          <select
            aria-label="Provider"
            value={provider}
            onChange={(event) => setProvider(event.target.value as ProviderName)}
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <input
            type="password"
            placeholder="API key"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            aria-label="API key"
            className="rounded border border-gray-300 px-2 py-1 text-sm"
          />
          <button
            type="button"
            onClick={() => void handleAdd()}
            disabled={!apiKey || addKey.isPending || rotateKey.isPending}
            className="rounded bg-gray-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
          >
            Save key
          </button>
          {error && <p className="text-xs text-red-600">{error}</p>}
          <button
            type="button"
            onClick={() => void healthCheck.mutateAsync({ orgId })}
            disabled={healthCheck.isPending}
            className="mt-2 self-start text-xs text-gray-500 hover:underline disabled:opacity-50"
          >
            Re-check key health
          </button>
        </div>
      )}
    </main>
  );
}
