import { useState } from "react";

import { useCreateOrg, useSwitchOrg } from "../api/queries";
import { useAuth } from "../auth/AuthContext";

interface CreateOrgStepProps {
  tosVersion: string;
  onCreated: () => void;
}

export function CreateOrgStep({ tosVersion, onCreated }: CreateOrgStepProps): React.JSX.Element {
  const { setToken } = useAuth();
  const createOrg = useCreateOrg();
  const switchOrg = useSwitchOrg();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async (): Promise<void> => {
    setError(null);
    try {
      const org = await createOrg.mutateAsync({ name, tosVersion });
      // T-206: POST /orgs does NOT re-mint the caller's session token — it still
      // carries the pre-creation org_id/role until switch-org is called explicitly.
      const session = await switchOrg.mutateAsync({ orgId: org.id });
      setToken(session.token);
      onCreated();
    } catch {
      setError("Could not create the org — try a different name.");
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold text-gray-900">Name your organization</h2>
      <input
        type="text"
        placeholder="Acme Inc."
        value={name}
        onChange={(event) => setName(event.target.value)}
        aria-label="Organization name"
        className="rounded border border-gray-300 px-3 py-2 text-sm"
      />
      <button
        type="button"
        onClick={() => void handleCreate()}
        disabled={!name || createOrg.isPending || switchOrg.isPending}
        className="self-start rounded bg-gray-900 px-4 py-2 text-sm font-medium text-white hover:bg-gray-800 disabled:opacity-50"
      >
        Create organization
      </button>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}
