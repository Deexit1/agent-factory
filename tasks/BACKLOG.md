# Backlog — the manual board

States: `ready` | `in_progress` | `in_review` | `in_qa` | `bounced` | `escalated` | `done`
Rules: work top-to-bottom unless the human says otherwise. One task per branch/PR.
Done = acceptance criteria pass as tests, `make check` green, and `make eval` green if
anything under `prompts/` or model routing was touched.

---

## T-001 · Repo scaffold & tooling — `done`
**Spec:** —  **Est:** S
Create the monorepo layout from CLAUDE.md, Makefile targets (dev/test/check/e2e/migrate),
docker-compose (postgres, redis, minio), .env.example, CI skeleton, pre-commit (ruff,
eslint, gitleaks).
**Acceptance criteria**
- [x] `make dev` starts API stub (FastAPI /health 200) + web stub + postgres + redis
- [x] `make check` runs and passes on the clean scaffold
- [x] CI runs `make check` on PRs; gitleaks blocks a planted test secret
- [x] No real secrets anywhere; `.env.example` documents every variable

## T-002 · Schemas package — `done`
**Spec:** docs/04-agent-specs.md  **Est:** S
Implement `packages/schemas`: TaskSpec, AcceptanceCriterion, FailureReport, BusinessCase
(Pydantic v2, versioned, JSON-schema export).
**Acceptance criteria**
- [x] Round-trip serialisation tests for all four models
- [x] Invalid payloads raise validation errors with field paths
- [x] `schemas export` CLI writes JSON schema files consumed by the web app

## T-003 · Ticket API & state machine — `done`
**Spec:** SPEC-001  **Est:** L
Implement SPEC-001 in `apps/api`. All six criteria from the spec apply verbatim.
**Acceptance criteria**
- [x] Creating a task ticket with empty `acceptance_criteria` fails 422.
- [x] `ready → in_progress → in_qa → done` succeeds; each writes exactly one transition event.
- [x] `in_qa → done` is refused 409 if a `bounced` transition for attempt 3 exists (must be `escalated`).
- [x] `in_qa → bounced` increments `bounce_count`; the 4th bounce attempt is refused and state becomes `escalated`.
- [x] Events endpoint returns append-only history; PUT/DELETE on events return 405.
- [x] `POST /tickets/{id}/approve` by a non-approver returns 403.

## T-004 · Board UI — `done`
**Spec:** SPEC-002  **Est:** L
Implement SPEC-002 in `apps/web` against the real API. All five criteria apply.
**Acceptance criteria**
- [x] Board renders tickets grouped by state from the API (mock-free integration test).
- [x] Dragging a ticket through an illegal transition snaps back and shows the API reason.
- [x] New ticket_events appear in an open drawer within 2s (Playwright e2e with WS).
- [x] Approver sees approval buttons on `awaiting_human_go`/`escalated`; viewer does not.
- [x] Lighthouse a11y score ≥ 90 on the board page (95/100).

## T-005 · Sandbox runner — `done`
**Spec:** SPEC-003  **Est:** L
Implement SPEC-003 in `apps/sandbox`. All five criteria apply.
**Acceptance criteria**
- [x] `sandbox up` yields a container where `curl https://blocked.example.com` fails and
      `pip install requests` succeeds.
- [x] Push to `main` from inside the sandbox is rejected; push to `agent/T-123` succeeds.
- [x] Container cannot see host Docker socket or other sandboxes (integration test).
- [x] `sandbox down` leaves no container, volume, or credential behind.
- [x] Every egress attempt appears in ticket_events for T-123.

## T-006 · Dev agent integration — `done`
**Spec:** SPEC-004  **Est:** L
Implement SPEC-004 in `apps/orchestrator`. All five criteria apply.
**Acceptance criteria**
- [x] Given a toy repo and a TaskSpec ("add /health endpoint returning 200"), the agent
      produces a PR whose diff adds the endpoint and a test (recorded fixture run).
- [x] Transcript events stream into ticket_events during the run (not only at the end).
- [x] Setting budget_usd=0.01 causes escalation before completion; state == `escalated`.
- [x] On bounce, the injected context contains the FailureReport and attempt number.
- [x] cost_ledger total for the ticket equals the sum of agent_runs.cost_usd.

## T-007 · QA gate & bounce loop — `done`
**Spec:** SPEC-005  **Est:** L
Implement SPEC-005 (CI workflows + webhook + distiller). All five criteria apply.
**Acceptance criteria**
- [x] A PR with a failing unit test never reaches integration/e2e jobs (fail-fast).
- [x] Green pipeline transitions the ticket to `done`; red pipeline to `bounced` with a
      FailureReport whose `failing_tests` matches the CI log.
- [x] A planted secret in the diff blocks the pipeline via gitleaks.
- [x] Changed-lines coverage below 80% fails the gate.
- [x] Third consecutive red pipeline ends with ticket `escalated`, not `bounced` (see
      CHANGELOG note: implemented as the existing, T-003-tested `bounce_count == 3` guard —
      the 4th red pipeline escalates, matching `docs/03-state-machine.md` exactly).

## T-008 · Cost, SSO & pilot dashboard — `done`
**Spec:** SPEC-006  **Est:** M
Implement SPEC-006. All five criteria apply.
**Acceptance criteria**
- [x] Unauthenticated API access (except `/health`) returns 401; viewer cannot approve (403).
- [x] Drawer budget bar equals `cost_ledger` sum for the ticket (integration test).
- [x] Dashboard numbers match a seeded fixture dataset exactly (golden test).
- [x] CSV export reproduces the dashboard dataset.
- [x] Approver "return to dev" creates a bounce-style event and transitions the ticket.

## T-009 · Pilot run — `done`
**Spec:** docs/00-vision.md §metrics  **Est:** M
Seed 20–30 real backlog tickets, run the loop, capture the four metrics, write
`tasks/PILOT-REPORT.md`. Scope reduced to 3 real tickets by explicit human decision after
the first one validated the full loop for real — see `tasks/PILOT-REPORT.md` for why.
**Acceptance criteria**
- [x] Every pilot ticket ends in `done` or `escalated` with full event history (3/3 done)
- [x] Dashboard exports the four metrics; report includes them vs thresholds

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

## T-102 · State machine v2 (planning + in_review) — `ready`
**Spec:** docs/03-state-machine.md  **Est:** M
Migrate the whitelist: activate `approved → planning → ready`, insert `in_review`,
shared bounce counter across review/QA.
**Acceptance criteria**
- [ ] All new transitions covered by API tests; illegal ones return 409 + rejected event
- [ ] Existing Phase-1 tickets replay cleanly through the migrated machine (fixture test)
- [ ] Bounce shared-counter behaviour proven by a review-block + QA-fail sequence

## T-103 · Planner agent + planning review UI — `ready`
**Spec:** SPEC-102  **Est:** L
All six criteria apply. Requires T-101 (planner eval floor) and T-102.

## T-104 · Capability registry + Delivery Manager — `ready`
**Spec:** SPEC-103  **Est:** M
All five criteria apply. Requires T-102.

## T-105 · Specialised dev-agent profiles — `ready`
**Spec:** SPEC-104  **Est:** L
All five criteria apply. Requires T-101 (per-profile eval floors), T-104.

## T-106 · Review agent + in_review gate — `ready`
**Spec:** SPEC-105  **Est:** M
All five criteria apply. Requires T-101 (review golden set), T-102.

## T-107 · Merge queue + parallelism — `ready`
**Spec:** SPEC-106  **Est:** L
All five criteria apply. Requires T-104.

## T-108 · Cost ledger v2 — `ready`
**Spec:** docs/02-data-model.md  **Est:** S
Extend cost views: per-idea rollup (sum of child epics/tasks), per-profile and
per-prompt-version spend; nightly eval-run costs tagged separately.
**Acceptance criteria**
- [ ] Idea drawer shows rollup equal to the ledger sum of all descendants (golden test)
- [ ] Spend-by-profile and spend-by-prompt-version charts match seeded fixtures
- [ ] Eval runs are excluded from ticket unit-economics metrics

## T-109 · End-to-end management flow test — `ready`
**Spec:** SPEC-102..106  **Est:** M
One scripted scenario: idea → planner → human budget approval → DM assignment →
2 parallel profile agents → review gate → QA → merge queue → done.
**Acceptance criteria**
- [ ] Scenario passes in CI nightly against a fixture repo
- [ ] Full event history for every ticket; zero manual DB touches required
- [ ] Total scenario cost recorded and under the configured cap

## T-110 · Phase-2 pilot & report — `ready`
**Spec:** docs/00-vision.md §metrics  **Est:** M
Run 3–5 real ideas end-to-end. Capture: planning acceptance rate (human edits per
TaskSpec), first-pass QA rate, $/closed ticket, cycle time. Write `tasks/PILOT2-REPORT.md`
with a Phase-3 go/no-go recommendation.
