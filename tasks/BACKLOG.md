# Backlog — the board

States: `ready` | `in_progress` | `in_review` | `in_qa` | `bounced` | `escalated` | `done`
Rules: work top-to-bottom unless the human says otherwise. One task per branch/PR.
Done = acceptance criteria pass as tests, `make check` green, and `make eval` green if
anything under `prompts/` or model routing was touched.

---

# Phase 1 — core loop ✅ COMPLETE

## T-001 · Repo scaffold & tooling — `done`
## T-002 · Schemas package — `done`
## T-003 · Ticket API & state machine — `done`  (SPEC-001)
## T-004 · Board UI — `done`  (SPEC-002)
## T-005 · Sandbox runner — `done`  (SPEC-003)
## T-006 · Dev agent integration — `done`  (SPEC-004)
## T-007 · QA gate & bounce loop — `done`  (SPEC-005)
## T-008 · Cost, SSO & pilot dashboard — `done`  (SPEC-006)
## T-009 · Pilot run — `done`  (report: tasks/PILOT-REPORT.md)

Details and test evidence for T-001…T-009 live in `tasks/CHANGELOG.md`.

---

# Phase 2 — management layer (ACTIVE)

## T-101 · Eval harness & golden sets — `done`
**Spec:** SPEC-101  **Est:** L
Build `make eval` + seed dev/distiller golden sets. Seeded from 3 real Phase-1 pilot
PRs + hand-authored synthetic cases sized like real tickets, not "20-30 pilot tickets"
as originally scoped — the pilot itself was descoped to 3 real tickets
(`tasks/PILOT-REPORT.md`), so there was never more real data to seed from.
**Acceptance criteria**
- [x] Degrading `prompts/failure-distiller.md` (deleting the Rules section) turns
      `make eval` red on the distiller set (verified for real: 70.6 vs floor 75)
- [x] Restoring the prompt turns it green; both runs visible in Langfuse Cloud with
      distinct prompt versions (verified for real: 86.5-86.7 vs floor 75)
- [x] Lowering a threshold in `evals/thresholds.yaml` without a CODEOWNERS approval
      fails CI — verified for real: a local dry run against PR #6's real (zero) reviews
      correctly failed with the exact codeowner login named. The reverse ("approve, then
      it passes") can't be demonstrated on this repo: GitHub categorically blocks
      self-approval, and @Deexit1 is the only codeowner/contributor, so this project can
      never produce a qualifying approval on its own PRs. Mitigation:
      `enforce_admins: false` on branch protection means the admin can still merge via
      an explicit override — the rule still forces a conscious, visible decision to
      bypass rather than a silent threshold change, which is what AC3 is actually for.
- [x] Judge scoring is reproducible: two runs on identical inputs differ by < 2%
      (verified for real: 86.7 → 86.5, ~0.2% drift)
- [x] PR comment shows per-set scores and worst-3 failing cases with diffs (verified
      for real on PR #6 — includes each case's full candidate output, not just a score)

## T-102 · State machine v2 + SaaS groundwork — `done`
**Spec:** docs/03-state-machine.md, docs/00-vision.md §SaaS-readiness  **Est:** M
Migrate the whitelist (activate `approved → planning → ready`, insert `in_review`,
shared bounce counter) AND lay the two SaaS-readiness foundations in the same migration.
`approved → planning → ready` was already whitelisted and guarded since T-003 — the
real remaining state-machine work was inserting `in_review` between dev and QA.
**Acceptance criteria**
- [x] All new transitions covered by API tests; illegal ones return 409 + rejected event
      (verified: `test_tickets_api.py`'s new `in_progress`→`in_review`→`in_qa`→`done`
      happy path and `test_in_progress_can_no_longer_skip_the_review_gate`, 409 +
      rejected event)
- [x] Existing Phase-1 tickets replay cleanly through the migrated machine (fixture
      test) — verified for real:
      `test_migration_replay.py::test_phase1_ticket_survives_migration_and_replays_through_new_machine`
      spins up its own Postgres container, runs migrations only to the pre-T-102
      revision, inserts a ticket row in the exact Phase-1 shape (no `org_id` column, no
      `in_review` state), upgrades to head, confirms `org_id` backfilled to `default`,
      then drives it through `in_progress→in_review→in_qa→done` for real
- [x] Bounce shared-counter behaviour proven by a review-block + QA-fail sequence
      (verified: `test_review_bounce_and_qa_bounce_share_one_counter_and_auto_escalate` —
      1 review-bounce + 2 QA-bounces hit `bounce_count == 3`; a 4th bounce from either
      gate is refused 409 and auto-escalates)
- [x] `org_id` (NOT NULL, FK to new `orgs` table; single default org backfilled) added
      to every domain table; all repository queries tenant-scoped (verified: 70/70
      `apps/api` tests green after threading `org_id` through every repository/service/
      router; `test_ticket_queries_are_tenant_scoped` proves a second org's ticket is
      invisible via `get_ticket`/`list_tickets` scoped to the default org, and vice
      versa. Scoped to groundwork, not full multi-tenancy: callers use a
      `DEFAULT_ORG_ID` constant until T-201 wires real per-request org resolution from
      auth — see `api/tenancy.py`)
- [x] `packages/llm_router` skeleton exists and ALL current LLM calls route through it
      (grep-gate: no provider SDK imports outside the router) — verified:
      `scripts/check_llm_router_gate.py` passes for real (0 violations) after migrating
      the two real direct-SDK call sites (`orchestrator/evals/judge.py`,
      `orchestrator/evals/distiller_scorer.py`) to `llm_router.route()`; re-ran the
      distiller eval set for real post-migration (86.7 avg vs floor 75, consistent with
      the T-101 baseline). Known, disclosed gap: `claude_runner.py`'s CLI-subprocess
      invocation of the `claude` binary has no SDK import for the grep-gate to catch —
      BYOK key-injection into that path is T-202's job, not this skeleton's

## T-103 · Planner agent + planning review UI — `ready`
**Spec:** SPEC-102  **Est:** L
All six criteria apply. Requires T-101, T-102.

## T-104 · Capability registry + Delivery Manager — `ready`
**Spec:** SPEC-103  **Est:** M
All five criteria apply. Requires T-102.

## T-105 · Specialised dev-agent profiles — `ready`
**Spec:** SPEC-104  **Est:** L
All five criteria apply. Requires T-101, T-104.

## T-106 · Review agent + in_review gate — `ready`
**Spec:** SPEC-105  **Est:** M
All five criteria apply. Requires T-101, T-102.

## T-107 · Merge queue + parallelism — `ready`
**Spec:** SPEC-106  **Est:** L
All five criteria apply. Requires T-104.

## T-108 · Cost ledger v2 — `ready`
**Spec:** docs/02-data-model.md  **Est:** S
Per-idea rollups, per-profile and per-prompt-version spend; eval costs tagged separately.
**Acceptance criteria**
- [ ] Idea drawer rollup equals ledger sum of all descendants (golden test)
- [ ] Spend-by-profile and spend-by-prompt-version charts match seeded fixtures
- [ ] Eval runs excluded from ticket unit-economics metrics

## T-109 · End-to-end management flow test — `ready`
**Spec:** SPEC-102..106  **Est:** M
Idea → planner → budget approval → DM → 2 parallel profile agents → review → QA →
merge queue → done, nightly in CI.
**Acceptance criteria**
- [ ] Scenario passes nightly against a fixture repo
- [ ] Full event history; zero manual DB touches
- [ ] Total scenario cost recorded and under the configured cap

## T-110 · Phase-2 pilot & report — `ready`
**Spec:** docs/00-vision.md §metrics  **Est:** M
3–5 real ideas end-to-end; capture planning acceptance rate, first-pass QA rate,
$/ticket, cycle time → `tasks/PILOT2-REPORT.md` with a Phase-2.5 go/no-go.

---

# Phase 2.5 — SaaS foundation (QUEUED — starts after T-110 go)

## T-201 · Multi-tenancy core — `ready`
**Spec:** SPEC-201  **Est:** L
Orgs, invites, RBAC, quotas, tenant-scope enforcement + staff impersonation auditing.
All five criteria apply. Requires T-102 (org_id groundwork).

## T-202 · BYOK keys & provider router v1 — `ready`
**Spec:** SPEC-202  **Est:** L
Key management UI, Vault storage, router with fallback + per-provider eval floors.
All six criteria apply. Requires T-101, T-102, T-201.

## T-203 · GitHub connect & provisioned repos — `ready`
**Spec:** SPEC-203  **Est:** L
GitHub App install flow, per-ticket scoped tokens, webhooks, provisioned/export mode.
All five criteria apply. Requires T-201.

## T-204 · VM-grade tenant isolation — `ready`
**Spec:** SPEC-204  **Est:** L
Firecracker/Kata runner pool, per-org egress and storage, no-co-location scheduling.
All five criteria apply. Requires T-201; supersedes gVisor for multi-tenant.

## T-205 · Billing & metering — `ready`
**Spec:** SPEC-205  **Est:** M
Stripe tiers + metered usage from cost_ledger/runner metrics; dunning; free beta tier.
All five criteria apply. Requires T-201.

## T-206 · Onboarding & abuse controls — `ready`
**Spec:** SPEC-206  **Est:** M
Self-serve signup → first PR wizard; intake screening; ToS + strikes; funnel telemetry.
All five criteria apply. Requires T-202, T-203.

## T-207 · Closed beta — `ready`
**Spec:** docs/09-saas-model.md  **Est:** M
5–10 external orgs, BYOK, own repos. Capture funnel conversion, first-PR time,
first-pass QA rate per provider, support load → `tasks/BETA-REPORT.md` with a
Phase-3/GA recommendation.
