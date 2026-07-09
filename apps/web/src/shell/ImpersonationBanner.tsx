import { Alert, AlertDescription } from "@/components/ui/alert";
import { useAuth } from "@/auth/AuthContext";

export function ImpersonationBanner(): React.JSX.Element {
  const { orgId, actor } = useAuth();

  return (
    <Alert variant="destructive" className="rounded-none border-x-0 border-t-0 py-1.5 text-center">
      <AlertDescription className="mx-auto justify-center text-xs font-semibold">
        Staff view — viewing org {orgId} as {actor}. This session is audited.
      </AlertDescription>
    </Alert>
  );
}
