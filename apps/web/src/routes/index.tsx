import { createFileRoute, redirect } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  beforeLoad: () => {
    // State-independent redirect only — auth/onboarding gating happens in _loggedIn
    // and _loggedIn/_onboarded, which run as React components (see their comments for
    // why this can't live in beforeLoad).
    throw redirect({ to: "/board" });
  },
});
