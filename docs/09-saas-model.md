# 09 — SaaS Model (tenancy, keys, repos, billing, abuse)

## Tenancy

**T-201 status**: real for orgs/org_members/invites/RBAC (owner/approver/member/
viewer)/the parallel-ticket quota/staff impersonation+audit — see docs/02-data-model.md
and docs/07-conventions.md's "Tenant scoping" section. Not yet real: sandbox-minutes/
day and storage quotas (no usage metering exists to enforce against).

**T-202 status**: real BYOK key management (add/rotate/delete, Vault storage, last-4
UI), a real provider router with Anthropic+OpenAI fallover/retries, per-provider eval
floors with an "unverified quality" opt-in gate, and a real key-hygiene scrubber. The
orchestrator's service-token path still resolves the org whose ticket is in play per
call (via the ticket's own `org_id`, fetched fresh) rather than being multi-org-aware
in the sense of dispatching across many orgs' ready queues at once — in practice today
it only ever sees `DEFAULT_ORG_ID`'s tickets (T-201's disclosed single-org dispatch
scope still applies), so BYOK is real and per-org by construction, just exercised
against one org in this environment. Not yet real: a third provider (Gemini, etc.), a
live eval run against OpenAI (no OpenAI credits in this environment — `providers.openai`
entries in `evals/thresholds.yaml` honestly ship `not_yet_enforced: true`), and real
production Vault topology (dev-mode only, see docs/06-tech-stack.md).

- `orgs` table; every domain table carries `org_id` (FK, NOT NULL). All repository-layer
  queries are tenant-scoped by construction (scoped session), verified by tests that
  attempt cross-tenant reads.
- Per-org quotas: max parallel tickets, max sandbox minutes/day, storage caps. Enforced
  in orchestrator code.
- RBAC per org: owner / approver / member / viewer. Platform staff role is separate and
  audited.

## BYOK — customer LLM keys (real, T-202)
- Users register provider keys (Anthropic, OpenAI today; Gemini not yet built — a
  disclosed scope trim, not a design limit) per org via `apps/web`'s "Keys" page ->
  `POST/DELETE /orgs/{id}/provider-keys`.
- Storage: Vault KV v2 at `tenants/<org_id>/llm/<provider>` — encrypted, never written
  to DB, logs, events, or traces (`packages/schemas/redaction.py`'s `scrub`/
  `scrub_payload`, applied at every event-write choke point). UI shows last-4 only;
  `provider_keys` (apps/api) holds only that metadata, never the secret.
- Injection: keys are fetched at agent-run start via a service-token-only
  `GET /orgs/{id}/llm/runtime-keys` call, held in memory in the runner, passed to the
  router — never mounted into sandboxes. The dev agent's CLI-subprocess path
  (`claude_runner.py`) gets its key via a scoped `Popen(env=...)` override, never
  argv, never a transcript payload.
- Validation on save: a cheap `models.list()`-shaped ping (not a completion call, not
  `llm_router` — a disclosed, narrow, allowlisted exception to "provider SDKs live
  only in llm_router", see `scripts/check_llm_router_gate.py`). A callable (not cron)
  health-check re-validates and flips a key to `invalid` on failure; the UI banners
  any non-`active` key.
- An org with NO configured key at all falls back to the platform's own key (the
  pre-BYOK behavior, unchanged) — this fallback stops the moment an org configures its
  own key; deleting it after that pauses dispatch for real (not a silent fallback).
- Token spend goes on the CUSTOMER's key; our cost_ledger still records usage per run
  for quotas and analytics (`cost_ledger.provider`/`agent_runs.provider`, both dynamic
  now instead of the old hard-coded `"anthropic"` literal).

## Provider router (real, T-202)
- Single module `packages/llm_router`: `route(role, *, credentials, complexity, ...)`
  tries each `ProviderCredential` in the org's fallback order, retrying transient
  failures per-provider before falling over to the next — real Anthropic + OpenAI
  adapters, fault-injection-tested at the HTTP boundary (zero live spend in tests).
  `complexity` is accepted per spec but doesn't yet subdivide model choice within a
  role (disclosed v1 scope trim). Usage capture stays the caller's job (an
  orchestrator agent function calls `apps/api`'s `agent-runs`/`complete` endpoints
  around the `route()` call, now threading the real `provider` through).
- Prompts remain provider-portable where possible; provider-specific prompt variants are
  versioned like any prompt and eval-gated per provider. An org selecting a provider
  we haven't eval-floored for a given agent gets a visible "unverified quality" badge
  (`GET /orgs/{id}/eval-floors`) and must record an explicit opt-in
  (`POST .../eval-floors/opt-in`) before that combo is dispatchable — enforced as a
  hard gate at every agent entry point, not a UI-only suggestion.

## Code delivery — two repo modes
1. **Connect (default):** user installs our GitHub App on their org/repo; agents push
   `agent/*` branches and open PRs there. Minimal permissions: contents + pull requests
   on selected repos only.
2. **Provisioned:** we create a repo under the platform org and transfer ownership on
   request/export.

## Billing & metering
- BYOK means tokens are the customer's cost. We charge platform usage: subscription
  tier (seats, parallel tickets) + metered units (agent-run minutes, sandbox minutes,
  active tickets). Stripe subscriptions + usage records fed nightly from cost_ledger /
  runner metrics.
- Hard spend guards remain per ticket/org even on customer keys — runaway loops burn
  THEIR money and OUR reputation.

## Isolation & abuse
- Multi-tenant sandboxes require VM-grade isolation (Firecracker/Kata) at GA — gVisor
  acceptable only for the closed beta.
- Acceptable-use policy; automated screening of idea/task content at intake (malware,
  scraping farms, credential attacks, spam infrastructure → reject + audit event).
- Per-org egress allow-list additions require human platform-staff approval.
