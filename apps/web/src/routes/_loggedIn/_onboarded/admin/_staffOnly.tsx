import { createFileRoute } from "@tanstack/react-router";

import { StaffGuard } from "@/shell/StaffGuard";

export const Route = createFileRoute("/_loggedIn/_onboarded/admin/_staffOnly")({
  component: StaffGuard,
});
