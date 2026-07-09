import { createFileRoute } from "@tanstack/react-router";

import { PlanningReviewPage } from "@/planning/PlanningReviewPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/planning")({
  component: PlanningReviewPage,
});
