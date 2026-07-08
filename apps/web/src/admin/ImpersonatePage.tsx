import { useState } from "react";

import { useAuth } from "../auth/AuthContext";
import { useImpersonateOrg } from "../api/queries";

export function ImpersonatePage(): React.JSX.Element {
  const { setToken } = useAuth();
  const impersonate = useImpersonateOrg();
  const [orgId, setOrgId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleImpersonate = async (): Promise<void> => {
    setError(null);
    try {
      const session = await impersonate.mutateAsync({ orgId });
      setToken(session.token);
    } catch {
      setError("Could not start impersonation — check the org id and that you're platform staff.");
    }
  };

  return (
    <main className="flex h-screen flex-col items-center justify-center gap-4 bg-white">
      <h1 className="text-xl font-bold text-gray-900">Staff: view as org</h1>
      <p className="max-w-sm text-center text-sm text-gray-500">
        Starts a short-lived, read-mostly session scoped to the org below. Every page you
        visit while impersonating is audited.
      </p>
      <div className="flex w-72 flex-col gap-2 rounded-md border border-gray-200 p-4">
        <input
          type="text"
          placeholder="org id"
          value={orgId}
          onChange={(event) => setOrgId(event.target.value)}
          aria-label="Org id"
          className="rounded border border-gray-300 px-2 py-1 text-sm"
        />
        <button
          type="button"
          onClick={() => void handleImpersonate()}
          disabled={!orgId || impersonate.isPending}
          className="rounded bg-red-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
        >
          View as this org
        </button>
        {error && <p className="text-xs text-red-600">{error}</p>}
      </div>
    </main>
  );
}
