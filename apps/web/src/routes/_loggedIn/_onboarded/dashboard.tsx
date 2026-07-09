import { createFileRoute } from "@tanstack/react-router";

import { DashboardPage } from "@/dashboard/DashboardPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/dashboard")({
  component: DashboardPage,
});
