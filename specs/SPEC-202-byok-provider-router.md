# SPEC-202 — BYOK Keys & Provider Router

## Goal
Customers bring their own LLM keys; all model calls flow through one router module.

## In scope
- `packages/llm_router`: (agent_role, complexity, org) → (provider, model, key);
  org-level fallback order; retries/timeouts; usage capture into agent_runs/cost_ledger.
- Migration: ALL existing direct Anthropic client calls replaced by the router
  (grep-gate: no provider SDK imports outside the router package).
- Key management UI + API: add/validate/rotate/delete per provider; Vault storage at
  `tenants/<org>/llm/<provider>`; last-4 display only.
- Key hygiene: keys never in DB/logs/events/traces (log-scrubber test); fetched at run
  start; never exposed inside sandboxes.
- Provider health-check job; failed key → banner + affected agents paused for that org.
- Per-provider eval floors: an org's provider/model choice for an agent must have a
  green eval floor or the UI shows "unverified quality" and requires opt-in.

## Acceptance criteria
1. Grep-gate: zero provider SDK imports outside `packages/llm_router` (CI check).
2. A planted key string in any log/event/trace fixture fails the scrubber test.
3. Org A's runs are billed to Org A's key: provider-side usage matches agent_runs
   attribution in a recorded fixture.
4. Primary-provider outage (fault injection) fails over per the org's fallback order
   and records the switch as an event.
5. Selecting an uneval'd provider/agent combo shows the badge and requires explicit
   opt-in; the opt-in is recorded.
6. Deleting a key revokes it from Vault and pauses dependent agents within 60s.
