"""T-102 groundwork: every domain table carries org_id, every repository query is
tenant-scoped. Real per-request org resolution (from user org membership, invites,
per-org RBAC roles) landed in T-201 for humans (session JWT carries the resolved
org_id); ADMIN_EMAILS-seeded accounts still bootstrap into this single seeded org
(platform-staff/pilot-admin tooling)."""

DEFAULT_ORG_ID = "default"

# T-210: minted into a brand-new (non-admin) user's very first session so every
# `org_id: str` type contract (SessionOut, mint_session_token, the frontend Session
# type) is satisfied without needing a nullable org_id anywhere — but this id never
# corresponds to a real `Org` row. Every org-scoped query against it (onboarding
# status, ticket lists, provider keys, repos) naturally returns empty/false, which is
# exactly "onboarding not started yet" — OnboardingGate.tsx already renders the wizard
# correctly for that, unmodified. The session is upgraded to a real org's id the
# moment the user completes the wizard's "create your org" step (POST /orgs +
# POST /auth/switch-org, neither of which reads the caller's *current* org_id).
PENDING_ORG_ID = "pending"
