# 09 — SaaS Model (tenancy, keys, repos, billing, abuse)

## Tenancy

**T-201 status**: real for orgs/org_members/invites/RBAC (owner/approver/member/
viewer)/the parallel-ticket quota/staff impersonation+audit — see docs/02-data-model.md
and docs/07-conventions.md's "Tenant scoping" section. Sandbox-minutes/agent-run-minutes
usage metering is real as of T-205 (see "Billing & metering" below) and enforced as a
hard cap for free-tier orgs (`ticket_service._org_over_usage_cap`); storage quotas are
still not real (no metering exists to enforce against).

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
  active tickets). Razorpay subscriptions + metered addons fed nightly from
  `agent_runs`/`usage_events`/`ticket_events`.
- Hard spend guards remain per ticket/org even on customer keys — runaway loops burn
  THEIR money and OUR reputation.

**T-205 status (SPEC-205), vendor swapped Stripe → Razorpay this session (human
decision, no live account for either):**
1. **Vendor client (AC2/AC4's plumbing).** `apps/api/src/api/razorpay_client.py` is the
   sole owner of any `api.razorpay.com` call (`scripts/check_razorpay_gate.py`, `make
   razorpay-gate`) — a hand-rolled `httpx` REST wrapper (this repo's own convention,
   not the vendor SDK), real HMAC-SHA256 webhook-signature verification. No live
   Razorpay account is reachable here; every call is respx HTTP-boundary fault-injection
   tested, same standing as T-202/T-203's GitHub/OpenAI live-infra gaps.
2. **Tiers are real placeholders.** `apps/api/src/api/billing_plans.py` defines
   `free`/`starter`/`team` with concrete ₹ figures and a pure `compute_invoice`
   function — the mechanism (plan storage, SPEC-201 quota mapping, metered overage
   math) is fully real; the numbers are explicit placeholders pending a real pricing
   decision, swappable in that one module without touching logic.
3. **Idempotent nightly metering job (AC1).** `apps/api/scripts/run_billing_metering.py`
   (`make billing-meter DATE=...`) — no scheduler daemon exists anywhere in this repo
   (`provider_health_service.py`'s own disclosed standing), so this is an externally
   triggered ops entrypoint, same framing as `run_pilot.py`. Per day, per org: records
   raw usage into `billing_usage_reports` (upsert-if-absent on `(org_id, report_date,
   kind)` — a second run for the same day is provably a no-op, real Postgres-tested).
4. **Golden-total invoice (AC2).** A seeded month of real `agent_runs`/`usage_events`/
   `ticket_events` fixtures, run through the real metering job, produces a total that
   matches a hand-computed golden figure via `compute_invoice` — proven at both the
   pure-function level and the full-pipeline level.
5. **Plan enforcement (AC3).** `billing_service.set_plan`: upgrades apply immediately
   to `orgs.max_parallel_tickets` (T-201's one enforced quota); downgrades defer to
   `orgs.current_period_end` and only tighten once the period-end sweep
   (`apply_pending_plan_sweep`, part of the same nightly job) runs past it — both sides
   tested against real Postgres.
6. **Dunning (AC4) reuses T-203's force-block precedent verbatim.** `POST
   /webhooks/razorpay` (HMAC-verified) → `payment.failed` starts a 7-day grace period
   (`billing_status=past_due`) → an expired grace period
   (`billing_service.expire_grace_periods`) pauses the org and force-transitions every
   in-flight ticket to `BLOCKED` via the exact same
   `ticket_service.request_transition`/`disconnect_repo`-style loop T-203 built, keyed
   off org instead of repo (`system:billing` is the second exact-string entry in
   `state_machine.py`'s `_SYSTEM_BLOCK_ACTORS`, next to `system:github`) →
   `payment.captured`/`subscription.charged` unpauses the org. Already-`BLOCKED`
   tickets are not auto-unblocked — a pre-existing gap since T-203, not created or
   closed here.
7. **Reconciliation (AC5) is a real two-path check, not a tautology.**
   `GET /orgs/{id}/billing/usage` (the org dashboard's data source) computes live from
   `usage_events`/`agent_runs`/`ticket_events`
   (`billing_service.compute_live_invoice_for_period`), independent of
   `billing_usage_reports`; the reconciliation test proves this agrees with what the
   metering job actually recorded as sent to Razorpay
   (`compute_invoice_for_period`, ledger-based) for the same period.
8. **Free-tier hard caps.** `max_parallel_tickets` (already enforced since T-201) plus a
   new `org_over_usage_cap` guard in `state_machine.py`/`ticket_service.py` — same
   rejection-not-hard-block shape as T-201's `org_at_quota`, applies only to
   `plan == "free"` orgs over their included agent-run-minutes/sandbox-minutes.
   **Not yet real:** seats (`PlanDefinition.seats_included`) are stored but not
   enforced — no AC requires seat-capacity enforcement; no new `apps/web` UI, matching
   T-201–204's own precedent exactly.

## Isolation & abuse
- Multi-tenant sandboxes require VM-grade isolation (Firecracker/Kata) at GA — gVisor
  acceptable only for the closed beta. As of T-204, every isolation mechanism AROUND
  the runtime (scheduling, egress, storage ACLs, escape-tests) is real; the hypervisor
  swap itself is the one piece still not live-verified — see "Sandbox isolation" above.
- Per-org egress allow-list additions require human platform-staff approval — real as of
  T-204 (`org_egress_rules`, staff-only `POST/DELETE /orgs/{id}/egress-rules`).

**T-206 status (SPEC-206), real as of this session:**
1. **Self-serve onboarding wizard (AC1).** `apps/web/src/onboarding/OnboardingWizard.tsx`
   chains the pieces T-201–205 already built into one guided flow: ToS accept →
   `POST /orgs` (ToS acceptance recorded transactionally) → `POST /auth/switch-org`
   (a real trap this UI has to handle — org creation does NOT re-mint the caller's
   session token) → the *existing* `ProviderKeysPage`/`RepoConnectPage` components
   rendered inside wizard chrome (reused, not duplicated) → a new
   `CreateFirstIdeaStep`, the first real ticket-creation UI surface in this app. A
   fresh OIDC/dev-login still auto-joins the seeded default org as `viewer`
   unchanged (T-008/T-201); the wizard is what gives that viewer a real path to
   their OWN org, closing the gap where org creation was API-only. Reached via an
   explicit "Get started" nav entry, NOT auto-triggered on login — an earlier design
   that auto-redirected any session without an `idea`-type ticket into the wizard was
   caught and reverted after it broke real usage (any org that only ever works with
   `task`-type tickets directly would have been permanently locked out of the board),
   surfaced for real by PR #21's own CI `e2e` job against the pre-existing Playwright
   suite.
2. **Automated intake screening (AC2), real, rule-based, zero LLM.**
   `api.services.intake_screening_service.screen_content` is a pure keyword/regex
   engine (malware, credential attacks, scraping farms, spam infra hard-reject;
   adjacent-but-legitimate terms like "web scraper"/"penetration testing" route to
   a staff review queue instead) — the only mechanism AC2 is verified against, since
   this environment has zero live Anthropic credit (same disclosed constraint as
   every other eval-gate here). A haiku-class LLM judgment layer for genuinely
   ambiguous cases was scoped but NOT built — no prompt/schema/router scaffolding
   exists for it, a disclosed gap (see docs/04-agent-specs.md). Hard-rejects and
   review-queue entries are audited in a new `intake_reviews` table; staff resolve
   via `POST /admin/intake-reviews/{id}/approve|reject` (`apps/web`'s new
   `IntakeReviewPage.tsx`).
3. **ToS acceptance + re-prompt (AC3), real.** New `tos_acceptances` table,
   `(org_id, tos_version)`-unique. Orgs that HAVE accepted before are re-prompted
   (ticket creation 403s) once `api.tos.CURRENT_TOS_VERSION` moves past their latest
   acceptance, until `POST /orgs/{id}/tos/accept`. Orgs with NO acceptance record at
   all (every pre-T-206 org, including the seeded default org) are grandfathered —
   not retroactively broken, same judgment as T-201's nullable
   `max_parallel_tickets`. `api.tos.py`'s policy text is an explicit placeholder,
   same framing as `billing_plans.py`'s pricing tiers.
4. **Strike/appeal (AC5), real, closes a gap disclosed since T-203.** A
   platform-staff-imposed strike (`POST /admin/orgs/{id}/strikes`, new
   `org_strikes` table) force-blocks every in-flight ticket — the exact
   `list_in_flight_by_org`/`request_transition`-to-`BLOCKED` loop
   `billing_service.pause_org_for_nonpayment` (T-205) already established, actor
   `human:{staff_email}` (already covered by `is_human_actor`, no new
   `_SYSTEM_BLOCK_ACTORS` entry needed). Appeal *request* is owner-initiated
   self-service (`POST /orgs/{id}/strikes/{id}/appeal`); appeal *decision* is
   platform-staff-only (`POST /admin/strikes/{id}/resolve-appeal`) — an org can
   never un-strike itself. `state_machine.py` gains the first-ever whitelisted exit
   from `BLOCKED` (`BLOCKED → READY`, human-only) — previously there was none at
   all, a gap disclosed since T-203/T-205. **Known, disclosed limitation:**
   reinstatement is org-wide, not per-strike-cause — no `blocked_reason` column
   exists yet to distinguish an abuse-block from a simultaneous billing-block.
5. **Funnel telemetry (AC4), real, derived — not an event log.** No new
   `funnel_events` table: `onboarding_service.compute_funnel_cohort` derives each
   stage's org count from existing timestamped rows (`orgs.created_at`,
   `tos_acceptances`, `provider_keys`, `repos`, first `idea`-type `tickets`, first
   `merge_queue_entries.status=merged`) for orgs created in a cohort window — simpler
   and lower-risk than a new write-hooked event table, and exactly reproducible from
   seeded fixture rows. `GET /dashboard/funnel`, staff-only (`apps/web`'s new
   `FunnelDashboardPage.tsx`), is a platform-wide cross-org aggregate, deliberately
   not gated by the caller's own `org_id` the way every other org-scoped route is.
6. **Not yet real / disclosed non-goals:** no real anonymous-visitor funnel
   (telemetry starts at org creation, per SPEC-206's own "org-level" wording); no
   real product-analytics vendor; no live OIDC IdP registered in this environment
   (unchanged since T-008/T-201); no real legal ToS/AUP text. The orchestrator's
   dev-agent pipeline (planner → Delivery Manager → dev → review → merge queue)
   still cannot run against a freshly created, non-default org — `dispatch_gate.
   resolve_dispatch`'s service-principal-only `runtime-keys` check and
   `ticket_service`'s actor-derived `org_id` scoping can't both be satisfied by one
   `ApiClient` instance today. This is the same "orchestrator isn't multi-org-aware"
   gap T-202/T-205 already disclosed, not something T-206 created or closes — see
   `apps/orchestrator/tests/integration/test_e2e_onboarding_flow.py`'s own
   docstring for the full explanation. That test proves the real, new onboarding
   mechanics (signup → ToS → org → intake screening, landing a real ticket in the
   correct new org); `test_e2e_management_flow.py` (T-109) independently, already
   proves the full idea-to-done pipeline mechanics, nightly, against the one org the
   orchestrator can currently dispatch against.
