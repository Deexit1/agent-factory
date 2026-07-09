import { createFileRoute } from "@tanstack/react-router";

import { AcceptInvitePage } from "@/members/AcceptInvitePage";

export const Route = createFileRoute("/_loggedIn/invite/$token")({
  component: AcceptInvitePage,
});
