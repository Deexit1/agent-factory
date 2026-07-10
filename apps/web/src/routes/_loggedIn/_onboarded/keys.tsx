import { createFileRoute } from "@tanstack/react-router";

import { ProviderKeysPage } from "@/admin/ProviderKeysPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/keys")({
  component: () => (
    <main className="mx-auto max-w-2xl p-6">
      <ProviderKeysPage />
    </main>
  ),
});
