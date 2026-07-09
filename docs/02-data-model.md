# 02 — Data Model (Postgres 16)

All timestamps UTC. All agent payloads JSONB validated against `packages/schemas`.
Every table below carries `org_id` (FK → `orgs.id`, NOT NULL) — SaaS-readiness rule 1
(docs/00-vision.md). T-102 seeded a single default org and backfilled every existing
row to it; real per-request org resolution, invites, per-org RBAC, quotas, and staff
impersonation auditing are T-201.

## orgs
`id (PK), name, created_at, max_parallel_tickets, llm_fallback_order, plan,
pending_plan, pending_plan_effective_at, current_period_end, billing_status,
dunning_grace_until, razorpay_customer_id, razorpay_subscription_id` — the tenant.
`max_parallel_tickets` (nullable = unlimited, T-201) is the one ticket-count quota
that's actually enforced today; org-scoped egress and per-org artifact storage ACLs ARE
real as of T-204 (see `org_egress_rules` below and `apps/api/src/api/
artifact_storage.py`), and `apps/sandbox` is now wired into the real dev-agent path
(`orchestrator/sandbox_runner.py`, opt-in via `--sandbox`) — closing the T-105-disclosed
gap this note used to describe. `llm_fallback_order` (T-202, nullable JSONB array of
provider names e.g. `["anthropic", "openai"]`) is the org's BYOK provider priority
order — a single small setting, not a separate ordering table (same judgment as
`max_parallel_tickets`); `None`/empty means "whatever `provider_keys` rows exist,
anthropic first". `plan` (T-205, default `"free"`, `billing_plans.PLANS` key) plus
`pending_plan`/`pending_plan_effective_at` (a deferred downgrade, applied by
`apply_pending_plan_sweep` once `current_period_end` passes — plain strings, no new
Postgres enum, avoiding the documented two-migration ADD-VALUE-then-USE split);
`current_period_end` (nullable, lazily initialized `created_at + 30d` for orgs that
predate this column); `billing_status` (`active`/`past_due`/`paused`) +
`dunning_grace_until` (T-205's dunning path); `razorpay_customer_id`/
`razorpay_subscription_id` (nullable — stay null for `free`-plan orgs, which never
touch Razorpay).

## usage_events (T-205)
`id, org_id (FK), ticket_id (FK), kind (str), quantity (Numeric), ts` — a sibling to
`cost_ledger`, not an overload of `ticket_events` (whose `kind` is a Postgres enum).
Only `kind="sandbox_minutes"` is written today, via `POST /tickets/{id}/usage-events`
(service-token auth), posted by `apps/orchestrator`'s `SandboxClaudeCodeRunner` after
each real sandbox lease. `agent_run_minutes` needs no row here — the metering job
derives it directly from `agent_runs.started_at`/`ended_at`.

## billing_usage_reports (T-205)
`id, org_id (FK), report_date (date), kind (str), quantity (Numeric),
razorpay_addon_id (nullable str), created_at` — unique on `(org_id, report_date,
kind)`. This unique constraint *is* SPEC-205 AC1's idempotency mechanism: the nightly
metering job (`scripts/run_billing_metering.py`) upserts-if-absent per day/kind, so a
second run for the same day is provably a no-op.

## org_members (T-201)
`id, org_id (FK orgs), user_email (FK users.email), role (user_role enum), created_at`
— unique on `(org_id, user_email)`. A user's role is per-org now, not global; replaces
the old `users.role`/`users.org_id` pair. `user_role` is `owner | approver | member |
viewer` (renamed from T-102-era `admin/approver/viewer` — `admin` → `owner`, `member`
is new).

## org_invites (T-201)
`id, org_id, email, role, invited_by, token (unique), status (pending|accepted|
revoked), created_at, accepted_at` — an owner-issued invite. No email-sending exists in
this system yet, so the acceptance token is returned directly in the invite-creation
API response (a real deployment would email a link instead).

## staff_audit_log (T-201 AC5)
`id, staff_email, org_id, action, path (nullable), ts` — one row per platform-staff
impersonation action: `impersonate_start` when a "view as org" session begins, and one
`page_view` row (with `path`) per page the frontend visits while impersonating.

## provider_keys (T-202)
`id, org_id (FK orgs), provider, last4, status (active|invalid|revoked), created_at,
created_by, rotated_at (nullable)` — unique on `(org_id, provider)`. Audit-only
metadata for an org's BYOK provider key; the secret itself lives ONLY in Vault at
`tenants/<org_id>/llm/<provider>`, never in this table, a log, an event, or a trace.
`status` drives dispatch: only `active` keys are ever returned by the runtime-keys
resolution endpoint agents fetch from at run start — a `revoked`/`invalid` key drops
out immediately, the enforcement behind SPEC-202 AC6's "paused within 60s" (every
dispatch re-fetches fresh, so there's no cache to go stale).

## provider_eval_opt_ins (T-202 AC5)
`id, org_id (FK orgs), agent_role, provider, opted_in_by, ts` — unique on `(org_id,
agent_role, provider)`. An org's explicit opt-in to dispatch a (role, provider) combo
that has no green eval floor yet ("unverified quality"). A standing, org-level
decision — distinct from `ticket_events` (ticket-scoped) and `staff_audit_log` (a
staff action).

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
| repo_id | int FK→repos, nullable | T-203: which connected/provisioned repo this ticket delivers to. `null` = the pre-T-203 dogfood path (this platform monorepo itself, via the ambient `GITHUB_TOKEN`/`spec.repo`) — never backfilled. |

## repos (T-203)
`id (PK), org_id (FK orgs), mode (connected|provisioned), github_installation_id,
github_repo_id (nullable until resolved), github_full_name, clone_url, default_branch,
ci_mode (platform_runners|customer_ci), protected_branch_rules_verified (bool),
protected_branch_rules_verified_at, status (active|disconnected|exported),
disconnected_at, disconnected_reason, created_at, created_by` — unique on
`(org_id, github_repo_id)`. `connected` repos come from a customer's GitHub App
install (`POST /orgs/{id}/repos/connect-url` → GitHub → `GET /repos/connect-callback`);
`provisioned` repos are created under the platform's own org from a template
(`POST /orgs/{id}/repos/provisioned`). Never holds a GitHub token or the App's private
key — those are minted on demand (`apps/api/src/api/github_app_client.py`) and never
persisted anywhere, mirroring `provider_keys`' "audit-only metadata, secret lives
elsewhere" shape. `protected_branch_rules_verified` is a real result of a
connect-time `GET .../branches/{branch}/protection` check — false doesn't block the
connect (warn-and-allow, matches T-202's precedent), since the platform's own code
(`git_ops.py`'s `agent/*`-only push guard) refuses direct pushes to any other branch
regardless of what GitHub-side protection is configured.

## org_egress_rules (T-204)
`id (PK), org_id (FK orgs), domain, approved_by, approved_at, created_at` — unique on
`(org_id, domain)`. One org-approved addition to the sandbox egress allow-list, on top
of `sandbox.config.DEFAULT_ALLOWED_DOMAINS` (the base list every org gets). Only
platform staff may create/remove rows here (`ActorContext.is_platform_staff`, the same
gate `staff_audit_log`'s impersonation flow uses — no new auth concept). The
orchestrator fetches the merged base+org list at sandbox-provision time via the
service-token-only `GET /orgs/{id}/egress-rules/effective`.

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
status, tokens_in, tokens_out, cost_usd, trace_id, prompt_version, provider` (links to
Langfuse). `agent_role` is the dev agent's assigned capability-registry profile id
(`dev-frontend`/`dev-backend`/`dev-devops`/`dev-generalist`) when one was assigned,
else the generic role (`planner`/`review`/`delivery-manager`/`dev`) — this doubles as
the "spend by profile" dimension (T-108). `prompt_version` is parsed from the agent's
own prompt file's `# ... · vX.Y` header at run time; `null` for runs that predate T-108.
`provider` (T-202, nullable — `null` for runs that predate BYOK) is which provider
actually served the run (`anthropic`/`openai`), dynamic now instead of the old
hard-coded `"anthropic"` literal.

## cost_ledger
`id, ticket_id, agent_run_id, provider, model, usd, ts` — source of truth for $/ticket.
`provider` (real since T-202 — previously always the literal `"anthropic"`) is the
provider that actually served the run, threaded from `agent_runs.provider`.

## cost rollups (T-108)
No new tables — `GET /tickets/{id}/cost-rollup` sums `cost_ledger` over a ticket and
every descendant (`ticket_repository.get_descendants`, walking `parent_id`), closing
the idea-drawer rollup gap. `GET /dashboard/spend-by-profile` and
`GET /dashboard/spend-by-prompt-version` group `cost_ledger` by `agent_runs.agent_role`
and `agent_runs.prompt_version` respectively — the org-level "spend by model & agent
role" view originally promised in SPEC-006 but never built until now. Eval harness
runs (`apps/orchestrator/.../evals/`) never call the ticket API or write `agent_runs`/
`cost_ledger` rows, so these metrics are ticket-work-only by construction (T-108 adds a
regression test for this).

## approvals
`id, ticket_id, gate (idea|budget|deploy|escalation|review), decided_by, decision, note, ts`.

## merge_queue_entries (T-107)
`id, ticket_id, repo, status (queued|merged|conflict), enqueued_at, resolved_at` — one
FIFO slot per ticket whose CI went green. `in_qa -> done` requires a `merged` row here;
CI-green alone only creates a `queued` one. Written by `apps/orchestrator`'s
`merge_queue.py` after a real rebase-and-retest, not by the CI webhook directly.

## artifacts
`id, ticket_id, kind (diff|ci_log|trace|coverage), s3_key, ts`. Still not a real
SQLAlchemy model/table (unchanged since T-203's disclosure) — no code writes rows here
yet. T-204 makes the underlying STORAGE mechanism real and org-scoped
(`apps/api/src/api/artifact_storage.py`'s per-org MinIO bucket-prefix ACLs via a real
STS `AssumeRole`), but that's a credential-minting service, not this tracking table;
wiring actual artifact writes through it remains a disclosed gap.

## users
`email (PK), is_platform_staff, created_at` — OIDC-authenticated humans (SPEC-006). A
global identity table only — role and org membership live on `org_members` (T-201),
not here. First login auto-joins the seeded default org as `viewer` unless the email
is pre-seeded via `ADMIN_EMAILS` (→ `owner`) or the user already has a membership from
an accepted invite. `is_platform_staff` (bootstrapped via `PLATFORM_STAFF_EMAILS`,
mirroring `ADMIN_EMAILS`'s pattern) is a separate, cross-org concept — staff
impersonation, not an org role. T-206: `apps/web`'s `OnboardingWizard` now gives a
freshly auto-joined viewer a real self-serve path OUT of that seeded default org —
`POST /orgs` (ToS acceptance bundled transactionally) → `POST /auth/switch-org` →
BYOK key → repo → first idea — closing the gap where org creation was API-only with
no UI entry point.

## escaped_defect_reports
`id, ticket_id, note, reported_by, ts` — manual entry feeding the pilot dashboard's
"escaped defects" metric (docs/00-vision.md); a defect found after a ticket reached
`done` that QA didn't catch.

## tos_acceptances (T-206)
`id, org_id (FK), accepted_by, tos_version, accepted_at` — unique on
`(org_id, tos_version)`, mirroring `provider_eval_opt_ins`'s "one row per (tenant,
versioned-dimension)" shape. Written transactionally by `org_service.create_org`
(bundled into org creation — an org can't exist before ToS acceptance) and by
`POST /orgs/{id}/tos/accept` (re-acceptance after `api.tos.CURRENT_TOS_VERSION`
bumps). An org with NO row here at all (every pre-T-206 org, including the seeded
default org) is grandfathered — `ticket_service._is_org_tos_current` only re-prompts
orgs that have accepted a version before and have since gone stale.

## intake_reviews (T-206)
`id, org_id (FK), ticket_type, title, parent_id (nullable FK tickets), spec (jsonb),
acceptance_criteria (jsonb), budget_usd, repo_id (nullable FK repos), submitted_by,
submitted_at, status (pending|approved|rejected), screening_reason, decided_by,
decided_at, decision_note` — one row per idea/task submission that didn't pass
`intake_screening_service.screen_content` cleanly (a pure, dependency-free keyword/
regex engine covering SPEC-206's four named categories: malware, credential attacks,
scraping farms, spam infra — no LLM call, no live Anthropic credit needed).
Hard-rejects are decided immediately (`status=rejected`, `decided_by="system:
intake-screener"`); borderline matches wait `pending` for a platform-staff decision
(`POST /admin/intake-reviews/{id}/approve|reject`). A clean `pass` writes no row here
at all, so this table stays a real audit/review signal, not routine noise.

## org_strikes (T-206)
`id, org_id (FK), reason, struck_by, struck_at, status (active|appealed|reinstated|
denied), appeal_note, appealed_by, appealed_at, appeal_decided_by, appeal_decided_at` —
a platform-staff-imposed abuse strike (`POST /admin/orgs/{id}/strikes`), which
force-blocks every in-flight ticket via the same loop `billing_service.
pause_org_for_nonpayment` (T-205) established. Appeal *request* is owner-initiated
self-service (`POST /orgs/{id}/strikes/{id}/appeal`); appeal *decision* is
platform-staff-only (`POST /admin/strikes/{id}/resolve-appeal`) — an org can never
un-strike itself. Reinstatement is org-wide, not per-strike-cause: no
`blocked_reason` column exists to distinguish an abuse-block from a simultaneous
billing-block, a disclosed limitation (see docs/09-saas-model.md).

## Rules
- No updates or deletes on `ticket_events` and `cost_ledger` — append-only, enforced by
  DB grants.
- Every state change writes a `transition` event in the same DB transaction.
