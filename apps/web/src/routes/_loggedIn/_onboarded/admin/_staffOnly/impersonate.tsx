import { createFileRoute } from "@tanstack/react-router";

import { ImpersonatePage } from "@/admin/ImpersonatePage";

export const Route = createFileRoute("/_loggedIn/_onboarded/admin/_staffOnly/impersonate")({
  component: ImpersonatePage,
});
