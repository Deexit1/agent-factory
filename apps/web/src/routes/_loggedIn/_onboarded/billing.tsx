import { createFileRoute } from "@tanstack/react-router";

import { BillingPage } from "@/billing/BillingPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/billing")({
  component: BillingPage,
});
