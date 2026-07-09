import { createFileRoute } from "@tanstack/react-router";

import { FunnelDashboardPage } from "@/admin/FunnelDashboardPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/admin/_staffOnly/funnel")({
  component: FunnelDashboardPage,
});
