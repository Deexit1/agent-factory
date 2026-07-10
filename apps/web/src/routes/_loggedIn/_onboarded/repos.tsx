import { createFileRoute } from "@tanstack/react-router";

import { RepoConnectPage } from "@/admin/RepoConnectPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/repos")({
  component: () => (
    <main className="mx-auto max-w-2xl p-6">
      <RepoConnectPage />
    </main>
  ),
});
