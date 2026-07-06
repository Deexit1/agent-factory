"""T-102 groundwork: every domain table carries org_id, every repository query is
tenant-scoped. Real per-request org resolution (from user org membership, invites,
per-org RBAC roles) is T-201 — until then, every request is scoped to this single
seeded org."""

DEFAULT_ORG_ID = "default"
