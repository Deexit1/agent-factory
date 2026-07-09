import { createFileRoute } from "@tanstack/react-router";

import { CheckpointExplainerPage } from "@/docs/CheckpointExplainerPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/docs")({
  component: CheckpointExplainerPage,
});
