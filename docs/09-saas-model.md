# 09 — SaaS Model (tenancy, keys, repos, billing, abuse)

## Tenancy

**T-201 status**: real for orgs/org_members/invites/RBAC (owner/approver/member/
viewer)/the parallel-ticket quota/staff impersonation+audit — see docs/02-data-model.md
and docs/07-conventions.md's "Tenant scoping" section. Not yet real: sandbox-minutes/
day and storage quotas (no usage metering exists to enforce against), and the
orchestrator's service-token path staying single-org (`DEFAULT_ORG_ID`) — real per-org
agent dispatch is separate, larger work, likely T-202's territory since BYOK keys are
per-org.

- `orgs` table; every domain table carries `org_id` (FK, NOT NULL). All repository-layer
  queries are tenant-scoped by construction (scoped session), verified by tests that
  attempt cross-tenant reads.
- Per-org quotas: max parallel tickets, max sandbox minutes/day, storage caps. Enforced
  in orchestrator code.
- RBAC per org: owner / approver / member / viewer. Platform staff role is separate and
  audited.

## BYOK — customer LLM keys
- Users register provider keys (Anthropic, OpenAI, Gemini, …) per org.
- Storage: Vault KV at `tenants/<org_id>/llm/<provider>` — encrypted, never written to
  DB, logs, events, or traces. UI shows last-4 only.
- Injection: keys are fetched at agent-run start, held in memory in the runner, passed
  to the router — never mounted into sandboxes or exposed to agent-visible env.
- Validation on save (cheap ping call); health-check surfaces expired/exhausted keys.
- Token spend goes on the CUSTOMER's key; our cost_ledger still records usage per run
  for quotas and analytics.

## Provider router
- Single module `packages/llm_router`: role+complexity → (provider, model) using the
  org's configured keys, with fallback order per org. Retries, timeouts, usage capture.
- Prompts remain provider-portable where possible; provider-specific prompt variants are
  versioned like any prompt and eval-gated per provider. An org selecting a provider
  we haven't eval-floored for a given agent gets a visible "unverified quality" badge.

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
