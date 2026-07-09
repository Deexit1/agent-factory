import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
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
    <main className="flex h-full flex-col items-center justify-center gap-4 bg-background p-6">
      <h1 className="text-xl font-bold text-foreground">Staff: view as org</h1>
      <p className="max-w-sm text-center text-sm text-muted-foreground">
        Starts a short-lived, read-mostly session scoped to the org below. Every page you
        visit while impersonating is audited.
      </p>
      <Card className="w-72">
        <CardContent className="flex flex-col gap-2">
          <Input
            type="text"
            placeholder="org id"
            value={orgId}
            onChange={(event) => setOrgId(event.target.value)}
            aria-label="Org id"
          />
          <Button
            variant="destructive"
            onClick={() => void handleImpersonate()}
            disabled={!orgId || impersonate.isPending}
          >
            View as this org
          </Button>
          {error && <p className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>
    </main>
  );
}
