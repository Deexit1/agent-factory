import { createFileRoute } from "@tanstack/react-router";

import { ProviderKeysPage } from "@/admin/ProviderKeysPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/keys")({
  component: ProviderKeysPage,
});
