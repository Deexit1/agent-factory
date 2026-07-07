# 02 — Data Model (Postgres 16)

All timestamps UTC. All agent payloads JSONB validated against `packages/schemas`.
Every table below carries `org_id` (FK → `orgs.id`, NOT NULL) — SaaS-readiness rule 1
(docs/00-vision.md). T-102 seeded a single default org and backfilled every existing
row to it; real per-request org resolution (invites, per-org membership) is T-201.

## orgs
`id (PK), name, created_at` — the tenant. Single "default" org today.

## tickets
| column | type | notes |
|---|---|---|
| id | text PK | `T-001` style, human-readable |
| org_id | text FK→orgs | tenant (T-102) |
| type | enum | `idea` \| `epic` \| `task` |
| parent_id | text FK→tickets | ideas parent epics parent tasks |
| state | enum | see 03-state-machine.md |
| title | text | |
| spec | jsonb | TaskSpec for tasks, BusinessCase for ideas |
| acceptance_criteria | jsonb | array of machine-checkable criteria |
| assignee_agent | text | agent role id, nullable |
| budget_usd | numeric | hard cap; running spend is `cost_ledger`'s sum for the ticket, not a column here |
| bounce_count | int | max 3 then `escalated` |
| created_by | text | user id or agent id |
| created_at | timestamptz | ticket creation time; Phase 1 tickets start in `ready`, so this doubles as the "ready" timestamp for the cycle-time metric (docs/00-vision.md) |

## ticket_events (append-only, partitioned monthly)
| column | type | notes |
|---|---|---|
| id | bigserial PK | |
| ticket_id | text FK | |
| ts | timestamptz | |
| actor | text | `agent:dev-1` \| `human:uid` \| `system` |
| kind | enum | `message` \| `tool_call` \| `test_result` \| `transition` \| `cost` \| `edit` (T-103: human edits to a Planner-produced TaskSpec, before/after payload) \| `assignment` (T-104: Delivery Manager decision + reason + profiles considered) \| `review` (T-106: Review agent verdict + comments + scope_violations) |
| payload | jsonb | |

## agent_runs
one row per agent invocation: `id, ticket_id, agent_role, model, started_at, ended_at,
status, tokens_in, tokens_out, cost_usd, trace_id` (links to Langfuse).

## cost_ledger
`id, ticket_id, agent_run_id, provider, model, usd, ts` — source of truth for $/ticket.

## approvals
`id, ticket_id, gate (idea|budget|deploy|escalation|review), decided_by, decision, note, ts`.

## artifacts
`id, ticket_id, kind (diff|ci_log|trace|coverage), s3_key, ts`.

## users
`email (PK), role (admin|approver|viewer), created_at` — OIDC-authenticated humans
(SPEC-006). First login creates a `viewer` row unless the email is pre-seeded via
`ADMIN_EMAILS`; promotion beyond that is a manual admin action in Phase 1.

## escaped_defect_reports
`id, ticket_id, note, reported_by, ts` — manual entry feeding the pilot dashboard's
"escaped defects" metric (docs/00-vision.md); a defect found after a ticket reached
`done` that QA didn't catch.

## Rules
- No updates or deletes on `ticket_events` and `cost_ledger` — append-only, enforced by
  DB grants.
- Every state change writes a `transition` event in the same DB transaction.
