import { useEffect, useState } from "react";

import { useNavigate, useParams } from "@tanstack/react-router";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { useAcceptInvite } from "@/api/queries";

export function AcceptInvitePage(): React.JSX.Element {
  // Route id string, not an imported Route object — importing @/routes/.../invite.$token
  // here would be circular (that file imports this component).
  const { token } = useParams({ from: "/_loggedIn/invite/$token" });
  const navigate = useNavigate();
  const acceptInvite = useAcceptInvite();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    acceptInvite
      .mutateAsync({ token })
      .then(() => {
        void navigate({ to: "/board" });
      })
      .catch(() => {
        setError("This invite is invalid, expired, or has already been used.");
      });
    // Runs once on mount for this token — intentionally not re-running on every
    // acceptInvite mutation-object identity change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  if (error) {
    return (
      <main className="mx-auto max-w-md p-6">
        <Alert variant="destructive">
          <AlertTitle>Couldn't accept invite</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      </main>
    );
  }

  return <p className="p-4 text-gray-500">Joining org…</p>;
}
