import { createFileRoute } from "@tanstack/react-router";

import { OnboardingGate } from "@/shell/OnboardingGate";

export const Route = createFileRoute("/_loggedIn/_onboarded")({
  component: OnboardingGate,
});
