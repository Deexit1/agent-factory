import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
      <h2 className="text-lg font-semibold text-foreground">Name your organization</h2>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="org-name">Organization name</Label>
        <Input
          id="org-name"
          type="text"
          placeholder="Acme Inc."
          value={name}
          onChange={(event) => setName(event.target.value)}
          aria-label="Organization name"
        />
      </div>
      <Button
        onClick={() => void handleCreate()}
        disabled={!name || createOrg.isPending || switchOrg.isPending}
        className="self-start"
      >
        Create organization
      </Button>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
