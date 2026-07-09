import { createFileRoute } from "@tanstack/react-router";

import { OrgStrikesPage } from "@/admin/OrgStrikesPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/admin/_staffOnly/strikes")({
  component: OrgStrikesPage,
});
