import { createFileRoute } from "@tanstack/react-router";

import { AuthGate } from "@/shell/AuthGate";

export const Route = createFileRoute("/_loggedIn")({
  component: AuthGate,
});
