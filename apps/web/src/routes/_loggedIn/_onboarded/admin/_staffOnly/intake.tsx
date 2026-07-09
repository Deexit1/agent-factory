import { createFileRoute } from "@tanstack/react-router";

import { IntakeReviewPage } from "@/admin/IntakeReviewPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/admin/_staffOnly/intake")({
  component: IntakeReviewPage,
});
