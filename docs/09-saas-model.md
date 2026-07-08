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

## Code delivery — two repo modes (real, T-203)

**T-203 status**: real GitHub App connect/provision/export/disconnect, a real `repos`
registry, real per-ticket installation-token minting, and a real native GitHub webhook
route. No live GitHub App is registered in this environment and no live customer
repo exists — every GitHub API interaction is `respx`-fault-injection-tested at the
HTTP boundary (same T-202 `packages/llm_router` precedent) plus a real local bare git
repo standing in for "the customer repo" in orchestrator tests, not a live github.com
round-trip (see docs/06-tech-stack.md's implementation-status note for the full list
of disclosed gaps).

1. **Connect (default):** the org owner calls `GET /orgs/{id}/repos/connect-url`
   (state-token-protected, ≤10min TTL — doubles as CSRF protection for the browser
   redirect) and installs our GitHub App on their repo(s). GitHub redirects to
   `GET /repos/connect-callback`, which mints a real installation token, enumerates the
   selected repos, checks each one's default-branch protection
   (`GET .../branches/{branch}/protection`), and creates one `repos` row per repo.
   Minimal permissions: `contents:write` + `pull_requests:write` on selected repos
   only — the App never requests broader scope for a customer's own repos.
   Unprotected-branch repos are still connected (warn-and-allow, `repos.
   protected_branch_rules_verified=false`, persistent UI banner) rather than refused —
   our own code (`git_ops.py`'s `agent/*`-only push guard) holds regardless of
   GitHub-side protection.
2. **Provisioned:** `POST /orgs/{id}/repos/provisioned` creates a repo under the
   platform's own org from a template, using the platform's own App installation (the
   only installation that ever requests the broader `administration:write` permission,
   needed for `export(mode="transfer")` — never granted for a customer's connected
   repo). Export (`POST /orgs/{id}/repos/{repo_id}/export`) supports `mode="archive"`
   (returns GitHub's own tarball download URL — no new platform artifact storage was
   built, since none exists anywhere in this codebase yet) or `mode="transfer"`
   (ownership transfer; whether an App installation token can actually call GitHub's
   transfer endpoint is a disclosed, not-live-verified assumption).
3. **Per-ticket tokens (AC2):** the orchestrator's only way to a usable GitHub
   credential is `GET /tickets/{id}/github-install-token` (service-principal-only,
   mirrors T-202's `runtime-keys` endpoint) — mints a fresh installation token scoped
   to exactly that ticket's repo, asserted ≤1h TTL before it's ever returned. Never
   persisted anywhere (BYOK's "fetched at run start, held in memory" doctrine, extended
   verbatim). The dev agent's `git push`/`gh pr create` calls receive it via a
   subprocess-scoped `env=`/`git -c http.extraheader=` override — never argv, never a
   transcript payload, never `.git/config`.
4. **Uninstall handling (AC4):** GitHub's native `installation.deleted` webhook
   (`POST /webhooks/github`, HMAC-verified against `GITHUB_APP_WEBHOOK_SECRET`) marks
   the affected `repos` row disconnected and force-transitions every in-flight ticket
   to `blocked` (actor `system:github`, the one disclosed exception to "blocked is
   human-only" — see docs/03-state-machine.md) synchronously, in the same request —
   satisfies "within 60s" by construction, not by polling.
5. **Dogfood path preserved:** `tickets.repo_id` is nullable; every orchestrator entry
   point falls back to today's ambient-`GITHUB_TOKEN` behavior when it's null — this
   platform's own monorepo (what every ticket targeted before T-203) keeps working
   unmodified.

## Sandbox isolation (real, T-204)

**T-204 status**: real org-aware egress, a real no-co-location scheduler, a real
pre-warmed provisioning pool, real per-org artifact storage ACLs, a formal escape-test
suite, and — closing the gap disclosed since T-105/106/107 — the orchestrator's real
dev-agent run now actually executes inside this isolated sandbox instead of on the bare
host. No real Firecracker/Kata hypervisor is registered in this environment; the
runtime swap is built and pluggable but not live-verified (same disclosed-gap category
as T-202's "no OpenAI credits" / T-203's "no live GitHub App").

1. **Runtime.** `apps/sandbox/src/sandbox/runtime.py`'s `SandboxRuntime` interface has
   two implementations: `DockerRuntime` (real, live-tested, today's default — network-
   per-ticket, read-only rootfs, tmpfs, CPU/RAM limits, no docker-socket access) and
   `MicroVMRuntime` (built against Firecracker/Kata's real `ctr` CLI shapes, proven only
   via subprocess-boundary fault injection — no hypervisor here to boot a real VM
   against). Swapping is a `SandboxConfig.runtime` flag, not a rebuild.
2. **Scheduling (AC2).** `HostPool` (`apps/sandbox/src/sandbox/scheduler.py`) admits
   every real sandbox provisioning through a fixed pool of logical slots with real
   `threading.Lock`s — two different orgs' leases can never hold the same slot at once
   (concurrency-tested, 100 rounds, and gated into `SandboxClaudeCodeRunner`'s actual
   `run()` path, not just its own isolated tests). Honest scope: one process/host,
   matching today's actual single-runner-VM deployment (`docs/06-tech-stack.md`'s
   "Runner pool → Kubernetes" Phase-2 activation) — true multi-host coordination is
   deferred to whenever that activation fires.
3. **Pre-warming (AC4).** `SandboxPool` keeps idle network+proxy pairs ready ahead of a
   request (the genuinely slow parts to provision) and live-reconfigures Squid's
   allow-list per org at hand-out time (`squid -k reconfigure`, no container restart) —
   proven against real Docker with a concurrent load test.
4. **Egress (AC3).** A base allow-list (unchanged) plus org-approved additions,
   staff-gated (`org_egress_rules`, `POST/DELETE /orgs/{id}/egress-rules`) — reuses the
   exact `ActorContext.is_platform_staff` check T-201 impersonation established, no new
   auth concept. An org's own additions are proven not to leak into another org's list.
5. **Storage ACLs (AC5).** Per-org MinIO bucket-prefix ACLs minted via a real STS
   `AssumeRole` call with an inline session policy (`apps/api/src/api/
   artifact_storage.py`) — the denial an org-A credential hits reading org-B's prefix is
   MinIO's own policy engine, proven against a real MinIO container, not a hand-rolled
   check. Worktree storage gets per-org path scoping + OS permissions only, not real
   disk-level encryption (LUKS/dm-crypt needs host provisioning beyond a rootless
   container) — a disclosed gap.
6. **Escape-test suite (AC1).** Host-fs escape, docker-socket invisibility, and
   cross-org network unreachability all run for real against `DockerRuntime`
   (`apps/sandbox/tests/integration/test_escape_probes.py`, `make escape-test`); the
   same suite against `MicroVMRuntime` is honestly skipped (no hypervisor), not faked.
7. **Orchestrator wiring.** `orchestrator/sandbox_runner.py`'s `SandboxClaudeCodeRunner`
   implements the same `ClaudeCodeRunner` protocol the bare-host
   `SubprocessClaudeCodeRunner` does — `agents/dev.py`'s call site is unchanged beyond
   threading `org_id`/`ticket_id` through. `scripts/run_pilot.py --sandbox` opts a real
   pilot run into it; the default stays the bare-host path.

## Billing & metering
- BYOK means tokens are the customer's cost. We charge platform usage: subscription
  tier (seats, parallel tickets) + metered units (agent-run minutes, sandbox minutes,
  active tickets). Stripe subscriptions + usage records fed nightly from cost_ledger /
  runner metrics.
- Hard spend guards remain per ticket/org even on customer keys — runaway loops burn
  THEIR money and OUR reputation.

## Isolation & abuse
- Multi-tenant sandboxes require VM-grade isolation (Firecracker/Kata) at GA — gVisor
  acceptable only for the closed beta. As of T-204, every isolation mechanism AROUND
  the runtime (scheduling, egress, storage ACLs, escape-tests) is real; the hypervisor
  swap itself is the one piece still not live-verified — see "Sandbox isolation" above.
- Acceptable-use policy; automated screening of idea/task content at intake (malware,
  scraping farms, credential attacks, spam infrastructure → reject + audit event).
- Per-org egress allow-list additions require human platform-staff approval — real as of
  T-204 (`org_egress_rules`, staff-only `POST/DELETE /orgs/{id}/egress-rules`).
