import { createFileRoute } from "@tanstack/react-router";

import { OrgMembersPage } from "@/members/OrgMembersPage";

export const Route = createFileRoute("/_loggedIn/_onboarded/members")({
  component: OrgMembersPage,
});
