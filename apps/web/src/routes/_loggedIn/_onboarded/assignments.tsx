import { createFileRoute } from "@tanstack/react-router";

import { AssignmentQueuePage } from "@/assignments/AssignmentQueuePage";

export const Route = createFileRoute("/_loggedIn/_onboarded/assignments")({
  component: AssignmentQueuePage,
});
