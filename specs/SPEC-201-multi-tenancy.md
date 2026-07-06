# SPEC-201 — Multi-Tenancy Core

## Goal
Org-scoped everything: schema, queries, quotas, RBAC. The groundwork (org_id columns)
lands in T-102's migration; this spec completes enforcement and UX.

## In scope
- `orgs`, `org_members` tables; org switcher in the UI; invites (email + role).
- Tenant-scoped session/repository layer: queries cannot be written unscoped
  (lint rule + runtime guard).
- Per-org quotas (parallel tickets, sandbox minutes/day, storage) enforced in
  orchestrator code; quota events visible on the board.
- RBAC per org: owner / approver / member / viewer; platform-staff role with audited
  impersonation ("view as org" writes an audit event).

## Acceptance criteria
1. Cross-tenant read/write attempts in a dedicated test suite all fail (API 404, repo
   layer raises); suite runs in CI.
2. Static check fails the build on any repository query missing tenant scope.
3. Exceeding parallel-ticket quota leaves the extra task `ready` with a quota event.
4. Invited member gets role-appropriate access; viewer cannot approve (403).
5. Staff impersonation is watermarked in the UI and writes audit events for every page.
