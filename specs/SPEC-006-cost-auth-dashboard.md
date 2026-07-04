# SPEC-006 — Cost Ledger UI, SSO & Pilot Dashboard

## Goal
Close Phase 1: real login, budget visibility, and the four pilot metrics.

## In scope
- OIDC SSO (Authlib) with RBAC (admin/approver/viewer); replaces stub auth everywhere.
- Cost views: per-ticket spend bar (drawer), org-level spend by model & agent role.
- Pilot dashboard: first-pass QA rate, median $/closed ticket, escaped defects
  (manual entry field), cycle time (ready → done) — with CSV export.
- Escalation inbox for approvers with one-click "return to dev with note".

## Acceptance criteria
1. Unauthenticated API access (except /health) returns 401; viewer cannot approve (403).
2. Drawer budget bar equals cost_ledger sum for the ticket (integration test).
3. Dashboard numbers match a seeded fixture dataset exactly (golden test).
4. CSV export reproduces the dashboard dataset.
5. Approver "return to dev" creates a bounce-style event and transitions the ticket.
