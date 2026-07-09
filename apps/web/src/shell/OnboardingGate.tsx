import { useAuth } from "@/auth/AuthContext";
import { useOnboardingStatus } from "@/api/queries";
import { OnboardingWizard } from "@/onboarding/OnboardingWizard";
import { AppShell } from "@/shell/AppShell";

// Component-level gate, mirroring AuthGate — onboarding status is a TanStack Query
// result that resolves asynchronously, so this can't be a router beforeLoad either.
export function OnboardingGate(): React.JSX.Element {
  const { status, orgId, impersonating } = useAuth();
  const { data: onboardingStatus } = useOnboardingStatus(status === "authenticated" ? orgId : null);

  // Board access requires a real, fully-onboarded org: ToS accepted, a BYOK LLM key
  // added, and a repo connected. Staff impersonation always bypasses this — they're
  // viewing the org's real state for support, not going through its onboarding.
  if (!impersonating) {
    if (!onboardingStatus) {
      return <p className="p-4 text-gray-500">Loading…</p>;
    }
    const onboardingComplete =
      onboardingStatus.tos_accepted && onboardingStatus.has_provider_key && onboardingStatus.has_repo;
    if (!onboardingComplete) {
      return <OnboardingWizard />;
    }
  }

  return <AppShell />;
}
