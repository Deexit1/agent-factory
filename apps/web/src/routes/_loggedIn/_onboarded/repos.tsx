import { createFileRoute } from "@tanstack/react-router";

import { RepoConnectPage } from "@/admin/RepoConnectPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/repos")({
  component: RepoConnectPage,
});
