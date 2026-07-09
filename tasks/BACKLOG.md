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

## T-103 · Planner agent + planning review UI — `done`
**Spec:** SPEC-102  **Est:** L
First real LangGraph adoption (single-node StateGraph, no checkpointing yet); idea
tickets enter directly at `approved`, epics/tasks stored as real child tickets
(`parent_id` tree), planner routes through `packages/llm_router`'s new `planner` role
(opus-class).
**Acceptance criteria**
- [x] A seeded idea fixture yields TaskSpecs that all pass schema + sanity gates
      (golden test) — verified via
      `apps/orchestrator/tests/integration/test_planner_agent.py::test_seeded_idea_yields_a_valid_plan_with_epics_and_tasks`
      against a real Postgres + API (mocked LLM response for cost control): parses a
      `PlannerPlan`, creates real epic/task tickets with correct `parent_id`s, `spec`
      (including `depends_on`), and `planning` state; `agent_runs`/`cost_ledger` land
      real numbers from `llm_router`'s usage reporting
- [x] An under-specified idea fixture yields questions[], ticket -> escalated, and the
      human-answer round-trip produces a full plan — verified:
      `test_planner_agent.py::test_under_specified_idea_yields_questions_and_escalates`
      (planner side) +
      `apps/api/tests/integration/test_idea_planning_workflow.py::test_planning_questions_round_trip_to_escalated_and_back`
      (the full escalated -> answer -> planning round trip via the new
      `POST /tickets/{id}/answer-planning-questions` endpoint)
- [x] A cyclic-dependency plan (fault-injected) is rejected by the DAG gate with a
      clear event — verified:
      `test_idea_planning_workflow.py::test_planning_to_ready_blocked_by_a_cyclic_dependency_graph`
      (real DFS-with-recursion-stack cycle check in `ticket_service.py`, over the
      TaskSpec-id space each task's `spec` JSONB carries)
- [x] Task budgets exceeding the idea budget block `planning -> ready` — verified:
      `test_idea_planning_workflow.py::test_planning_to_ready_blocked_when_task_budgets_exceed_idea_budget`
- [x] Planner prompt changes are blocked by CI unless `make eval` (planner set) is
      green — verified: `evals/thresholds.yaml`'s `planner.not_yet_enforced` is now
      `false` (floor 70), same `eval-gate.yml`/`threshold-governance` CI mechanism as
      dev/distiller. Getting here required fixing two real bugs a first real run
      exposed: `planner_scorer.invoke_planner` crashed on a `questions[]` response
      instead of scoring it (fixed — scored via the judge, deterministic=0, since
      every reference in this set is a full plan); and `prompts/planner.md` (bumped
      v0.1 → v0.2) never specified the exact output JSON shape, so the live model
      returned rich question objects instead of plain strings and asked unnecessary
      questions on well-specified ideas. After both fixes, a full real run over all 15
      cases: 15/15 valid plans, zero errors, zero questions, deterministic_score 100
      on every case, combined score avg 88.6 (min 76.8, max 96.8).
- [x] Human edits to a TaskSpec are versioned as ticket_events (before/after payload)
      — verified:
      `test_idea_planning_workflow.py::test_update_task_versions_an_edit_event_with_before_and_after`
      (new `EventKind.EDIT` + `PATCH /tickets/{id}`, approver/admin-gated)

## T-104 · Capability registry + Delivery Manager — `done`
**Spec:** SPEC-103  **Est:** M
New `capability_registry.yaml` (repo root; profile → model/base_image/skills/
max_parallel, plus a `repo_concurrency_limit`), loaded by a small, intentionally
duplicated loader in each of `apps/api` and `apps/orchestrator` (separate
deployables, same precedent as `orchestrator/json_utils.py`). Seeded with one
`dev-generalist` profile — real multi-profile skill-matching is T-105's job.
Hard gates enforced in `apps/api`'s `state_machine.py`/`ticket_service.py` (code,
not the prompt), so the Delivery Manager's LLM call can propose an invalid
assignment and the API refuses it regardless. "Sandbox available" is treated as
identical to "profile at `max_parallel` capacity" — no separate sandbox-pool
subsystem exists in the architecture to model separately. The Delivery Manager
(`apps/orchestrator/src/orchestrator/agents/delivery_manager.py`) makes ONE sonnet
call per invocation for the WHOLE `ready` queue at once (matching the pre-existing
`prompts/delivery-manager.md` v0.1 batch contract), not one call per task.
**Acceptance criteria**
- [x] A dependent task (`depends_on` a sibling not yet `done`) cannot start even if
      proposed — verified:
      `apps/api/tests/integration/test_delivery_manager_gates.py::test_dependent_task_cannot_start_before_its_dependency_is_done`
      (API-level 409 + "dependencies are not done") and
      `apps/orchestrator/tests/integration/test_delivery_manager_agent.py::test_dependent_task_is_refused_by_the_api_and_recorded_not_crashed`
      (agent-level: the DM proposes it anyway, the API refuses, the DM records the
      refusal instead of crashing, then re-runs once the dependency completes and
      confirms the gate lifts)
- [x] A profile at its registry `max_parallel` has zero eligible profiles computed
      in Python (before any LLM call), and a ready task with no eligible profile is
      left `ready` with a `human_only` decision recorded, never assigned — verified:
      `apps/api/tests/integration/test_delivery_manager_gates.py::test_profile_max_parallel_defers_a_third_assignment`
      (API-level 409) and
      `test_delivery_manager_agent.py::test_task_deferred_to_human_when_profile_already_at_capacity`
      (agent-level: asserts `route()` is never even called, then frees capacity and
      confirms the task is picked up on the next run)
- [x] Every assignment decision (`assigned`/`refused`/`deferred`/`human_only`) is
      recorded as a `kind=assignment` ticket event carrying the model's reason and
      the profiles considered — verified:
      `test_delivery_manager_agent.py::test_successful_assignment_event_always_records_reason_and_considered`
- [x] Reassignment is refused once a task's own `cost_ledger` spend already meets
      its budget, even when the Delivery Manager (or anyone) proposes it again —
      verified:
      `test_delivery_manager_gates.py::test_reassignment_refused_once_task_has_already_spent_its_budget`
      and `test_delivery_manager_agent.py::test_reassignment_over_budget_is_refused_not_crashed`
      (real fault injection: escalate a fully-spent task, requeue it to `ready` via
      the new human-only `escalated → ready` transition, confirm reassignment is
      refused, not retried)
- [x] `GET /capability-registry/utilisation` reports real per-profile in-progress
      counts against each profile's `max_parallel` — verified:
      `test_delivery_manager_gates.py::test_utilisation_endpoint_matches_real_in_progress_counts`
      and surfaced in the web UI's new Assignments view
      (`apps/web/src/assignments/AssignmentQueuePage.tsx`)

Known gaps, disclosed: the batch LLM call's cost is attributed entirely to the
first considered ready task's `agent_run` (no proportional split — `agent_runs` has
no "not tied to one ticket" concept); `llm_router` had no `claude-sonnet-5` pricing
entry until now (fixed, since the DM is the first caller that needs it).

## T-105 · Specialised dev-agent profiles — `done`
**Spec:** SPEC-104  **Est:** L
`capability_registry.yaml` grows from T-104's single seeded `dev-generalist` to
four real profiles (`dev-generalist`, `dev-frontend`, `dev-backend`, `dev-devops`)
with genuinely different `model`/`skills` (all still on today's one existing
sandbox image — see Known gaps). `TaskSpec.required_skills` (new, default `[]`)
lets the Planner tag each task's domain; `prompts/planner.md` bumped v0.2 → v0.3
to populate it. The Delivery Manager's `_eligible_profile_ids` is split into a
skill-match stage (Python, before the LLM ever sees the task) and the existing
capacity stage, giving two distinct `human_only` reasons instead of one
overloaded one. `DevAgentConfig.model_for()` now takes the assigned profile
(profile's own model, except `complexity=high` always escalates to opus
regardless — a safety floor, not overridable per profile), threaded through
`run_dev_agent(..., profile=...)`.
**Acceptance criteria**
- [x] A task tagged `required_skills=["frontend"]` is only ever eligible for
      `dev-frontend`, never `dev-backend`/`dev-devops`/`dev-generalist`, even when
      those have free capacity — verified:
      `apps/orchestrator/tests/integration/test_delivery_manager_agent.py::test_frontend_tagged_task_is_never_proposed_to_a_non_matching_profile`
      (the fake LLM deliberately proposes `dev-backend` anyway; the DM itself
      rejects it as outside the eligible set it computed, without ever calling
      `apps/api`'s transition endpoint — closing a real gap where skill-match has
      no hard `apps/api` gate to fall back on, unlike capacity/budget/deps)
- [x] A task tagged with a skill no profile has (e.g. `["mobile"]`) is left
      `ready` with a `human_only` decision and the reason "no profile has the
      required skills" — distinct from the existing capacity-exhaustion reason,
      and never even reaching the LLM call — verified:
      `test_delivery_manager_agent.py::test_skill_mismatched_task_is_human_only_without_calling_the_llm`
- [x] The capacity-exhaustion path now narrows correctly to the *matching* profile
      only: filling `dev-frontend`'s registry `max_parallel` (2) with
      frontend-tagged occupants defers a third frontend-tagged task, unaffected by
      the other three profiles' free capacity — verified:
      `test_delivery_manager_agent.py::test_task_deferred_to_human_when_profile_already_at_capacity`
      (redesigned from T-104's single-profile version to prove skill-narrowing,
      not just raw capacity, now that multiple profiles exist)
- [x] The dev agent's model comes from its assigned profile (e.g. a devops-profile
      task runs on opus, a frontend/backend-profile task on sonnet), while
      `complexity=high` still always escalates to opus regardless of profile —
      verified: `apps/orchestrator/tests/test_config.py` (all 3
      `DevAgentConfig.model_for` branches) and
      `apps/orchestrator/tests/integration/test_dev_agent.py::test_assigned_profiles_model_reaches_the_runner_for_low_complexity_tasks`
      (a low-complexity task assigned the devops profile reaches
      `FixtureClaudeCodeRunner.last_model` as `claude-opus-4-8`, not the legacy
      sonnet-for-low-complexity default)
- [x] The Planner tags each task with `required_skills` in its structured output
      (prompt v0.3), verified via a full real re-run of the golden planner eval
      set: 15/15 valid plans, zero errors, avg score 89.6 (floor 70, consistent
      with T-103's original 88.6–89.2 baseline — no regression from the prompt
      change)

Known gaps, disclosed: all four profiles still point at the one existing sandbox
image (`agent-factory-sandbox:latest`) — genuinely different per-profile base
images is real infra work (new Dockerfiles, CI build steps) deliberately deferred
until a profile actually needs different tooling, not invented speculatively here.
Skill-matching is a Delivery-Manager-side routing filter, not a hard `apps/api`
gate (unlike budget/deps/capacity) — a deliberate scope boundary, not an oversight
(see the AC1 test above for how the DM itself closes the resulting gap). No
auto-dispatch loop exists connecting a DM assignment to a real `run_dev_agent`
invocation — `run_pilot.py` (explicitly "not part of the product") is unchanged
and still calls `run_dev_agent` with `profile=None`, falling back to the legacy
complexity-only model routing; this was already a disclosed gap before T-105 and
remains one.

## T-106 · Review agent + in_review gate — `done`
**Spec:** SPEC-105  **Est:** M
`in_review` was a true no-op before this task: `agents/dev.py` transitioned straight
through it to `in_qa` with zero gate (`state_machine.py` had no guard at all for
`IN_REVIEW → IN_QA` — any actor could request it). New
`apps/orchestrator/src/orchestrator/agents/review.py` (single-node LangGraph,
mirrors `planner.py`/`delivery_manager.py`) now actually holds the ticket there:
one sonnet call scores a PR diff + TaskSpec + style guide (+ an injectable
`semgrep_findings` string — see Known gaps) against `prompts/review-agent.md`
(pre-seeded, v0.1, unedited), producing a `ReviewResult` (verdict + comments +
scope_violations). `apps/api` enforces the real gate: `IN_REVIEW → IN_QA` now
requires a review-agent or human actor; a new `BOUNCED → IN_QA` human-only edge
is the override path for a review-block a human disagrees with, recording an
`Approval(gate=review)` row.
**Acceptance criteria**
- [x] A PR with a planted out-of-scope file edit is blocked with a
      scope_violation naming the file — verified:
      `apps/orchestrator/tests/integration/test_review_agent.py::test_scope_violation_diff_is_blocked_and_bounces_the_ticket`
      (real bounce to `bounced`, `bounce_count == 1`, PR comment posted)
- [x] A clean fixture PR is approved and transitions to `in_qa` automatically —
      verified: `test_review_agent.py::test_clean_diff_is_approved_and_transitions_to_in_qa`
- [x] Review-block then QA-fail on the same ticket yields `bounce_count == 2`
      (shared counter) — verified:
      `test_review_agent.py::test_review_bounce_then_qa_bounce_share_bounce_count`
      (review-block via the agent, then a simulated QA failure via the existing
      `ci-result` webhook) and, at the pure-gate level,
      `apps/api/tests/integration/test_review_gate.py::test_review_bounce_then_qa_bounce_share_the_bounce_counter`
- [x] Human override on a blocked PR transitions to `in_qa` and records the
      approval row — verified:
      `test_review_agent.py::test_human_override_on_a_blocked_pr_transitions_to_in_qa_with_approval_row`
      and `test_review_gate.py::test_bounced_review_can_be_overridden_by_human_with_approval_row`
      (an agent actor is refused the same override — 409 — proving it's genuinely
      human-only, not just unenforced)
- [~] Review set false-block rate ≤10% (eval floor) — **seeded but unverified**:
      8 real cases (4 clean, 4 planted-defect: scope violation, missing test,
      hardcoded secret, swallowed exception) + `review_scorer.py` +
      `runner.py` wiring all real and working (confirmed via direct invocation —
      the scorer runs, parses, and blends deterministic+judge scores correctly
      when the API responds). But every attempt to actually run it against live
      Anthropic in this environment returned 400 "credit balance is too low" —
      the same billing exhaustion that hit T-105's CI eval-gate. No real passing
      run exists behind `evals/thresholds.yaml`'s `review.floor: 70`; the user
      was offered the choice to wait for credits or leave `not_yet_enforced:
      true`, and explicitly chose to enable enforcement anyway with an
      unverified floor — see that file's rationale for the full disclosure.
      **Follow-up required**: re-run `python -m orchestrator.evals.runner run
      --set review` for real once credits are available and correct the floor
      from actual scores.

Known gaps, disclosed: `semgrep_findings` is an injectable string parameter, not
real Semgrep integration — CI already runs Semgrep (`agent-pr-gate.yml`) but
nothing parses its output back into the agent yet, deliberately deferred as
infra work orthogonal to the review mechanism. No auto-dispatch connects a
ticket's arrival at `in_review` to an automatic `run_review_agent` invocation —
matches the same disclosed gap as the Planner/Delivery Manager/dev agent (all
callable entry points, not auto-triggered). No retry-loop reconstructs a
FailureReport from a review-block event to automatically re-invoke the dev
agent — matches the existing QA-bounce gap.

## T-107 · Merge queue + parallelism — `done` (software mechanism; infra deferred — see below)
**Spec:** SPEC-106  **Est:** L
`in_qa -> done` was a bare state flip before this task — CI-green transitioned a
ticket straight to `done` with zero git operation anywhere in the codebase; the
doc's own "merge-queue slot acquired" guard text had no code behind it. New
`merge_queue_entries` table (`queued`/`merged`/`conflict`) + a real home-grown
FIFO processor (`apps/orchestrator/src/orchestrator/merge_queue.py`) that clones
each queued ticket's `agent/{ticket_id}` branch, rebases it onto the target
branch for real, and either force-pushes + merges (via a new
`GitHubClient.merge_pr`) or bounces with a `FailureReport(failing_suite=
"conflict")` — bounce_count shared with QA failures, matching the existing
review-block precedent (T-106). `apps/api`'s `IN_QA -> DONE` guard now requires
a real `merged` queue entry; `handle_ci_result`'s success path enqueues instead
of completing directly.
**Acceptance criteria**
- [x] Two tickets editing the same file: first merges; second gets a conflict
      bounce and succeeds after agent rebase — verified with REAL git
      operations (no mocked git, no real GitHub — `FakeGitHubClient.merge_pr`
      performs an actual git push to simulate what GitHub's merge would do,
      since proving a second ticket's rebase genuinely conflicts against a
      first ticket's real merge is the whole point):
      `apps/orchestrator/tests/integration/test_merge_queue.py::test_two_tickets_editing_the_same_file_first_merges_second_conflicts_then_succeeds`
- [x] No ticket reaches `done` without a queue entry (audit query returns zero
      violations) — verified:
      `apps/api/tests/integration/test_merge_queue_api.py::test_audit_query_is_clean_after_a_real_merge_queue_completion`
      and `test_audit_query_catches_a_done_ticket_with_no_merge_queue_entry`
      (real fault injection: a `done` ticket with no queue entry at all is
      caught by `ticket_service.tickets_done_without_merge_queue_entry`)
- [x] Concurrency limit 3 with 5 ready tickets → exactly 3 sandboxes ("sandboxes"
      = concurrently in_progress tickets on one repo, the existing T-104
      `repo_concurrency_limit` mechanism — see Known gaps) exist — verified:
      `apps/api/tests/integration/test_merge_queue_api.py::test_repo_concurrency_limit_defers_two_of_five_ready_tickets`
      (5 tickets assigned across 4 *different* profiles so no single profile's
      own `max_parallel` is what blocks anything — isolates the repo-wide limit
      as the actual gate). This test uncovered and fixed a REAL pre-existing
      bug: `count_in_progress_by_repo`'s query matched `Ticket.spec["repo"]`
      literally, so a ticket with no `spec` at all (the common case) was
      invisible to it — Postgres JSONB path access on a NULL column is NULL,
      not a match, silently undercounting to zero. Fixed with `COALESCE(...,
      DEFAULT_REPO)`, matching `ticket_service`'s own fallback logic.
- [x] Load test completes with all 5 tickets `done`/`escalated`, zero orphaned
      scratch directories — verified:
      `test_merge_queue.py::test_load_five_tickets_three_independent_two_conflicting`
      (3 independent tickets + 2 sharing a file, real conflict-then-resolve
      cycle, real git fixture repos). Hit and fixed a real Windows-specific bug
      along the way: `shutil.rmtree(..., ignore_errors=True)` silently leaves
      git's read-only object files behind instead of raising — fixed with an
      `onexc` callback that clears the read-only bit before retrying.
- [ ] Terraform apply from a clean state brings up both runners unattended —
      **not attempted this task, disclosed, not silently dropped.** See "Part B
      (deferred)" below.

Known gaps, disclosed:
- **Part B (deferred): real infra.** No Terraform/Ansible for a second
  self-hosted GitHub Actions runner VM, and no real Grafana queue-wait-time
  dashboard — both require real cloud credentials and a real Grafana instance
  this dev environment doesn't have. The user was shown this split explicitly
  before work began and chose to scope this PR to the software mechanism only,
  logging the infra half as a future follow-up once real infra access exists —
  same reasoning as T-105 deferring real sandbox images and T-106 deferring
  real Semgrep integration.
- **Not using GitHub's native merge-queue feature or a bors-style bot** — that
  needs GitHub org/repo admin configuration this session has no reason to
  assume exists. The orchestrator's own FIFO `run_merge_queue` is the real,
  disclosed substitute (docs/06-tech-stack.md's "Merge safety" row updated to
  say so plainly).
- **"Sandboxes" (AC3) == "concurrently in_progress tickets on one repo"**, not
  literal Docker containers — `apps/sandbox` still isn't wired into the
  dev-agent path at all (T-105's own disclosed gap); closing that is a
  separate piece of work, out of scope here.
- No auto-dispatch loop invoking `run_merge_queue` on a timer/webhook — matches
  every other agent in this repo (Planner/Delivery Manager/dev agent/Review
  agent are all callable entry points, not auto-triggered).

## T-108 · Cost ledger v2 — `done`
**Spec:** docs/02-data-model.md  **Est:** S
Per-idea rollups, per-profile and per-prompt-version spend; eval costs tagged separately.
**Acceptance criteria**
- [x] Idea drawer rollup equals ledger sum of all descendants (golden test) —
  `GET /tickets/{id}/cost-rollup` (`apps/api/tests/integration/test_cost_rollup_api.py`)
- [x] Spend-by-profile and spend-by-prompt-version charts match seeded fixtures —
  `GET /dashboard/spend-by-{profile,prompt-version}`
  (`apps/api/tests/integration/test_dashboard_api.py::test_spend_by_profile_and_prompt_version_match_seeded_fixture_exactly`);
  closes the "org-level spend by model & agent role" AC promised in SPEC-006 but never
  built
- [x] Eval runs excluded from ticket unit-economics metrics — true by construction
  (evals never call the ticket API); regression test in
  `apps/orchestrator/tests/evals/test_cost_isolation.py`

## T-109 · End-to-end management flow test — `done`
**Spec:** SPEC-102..106  **Est:** M
Idea → planner → budget approval → DM → 2 parallel profile agents → review → QA →
merge queue → done, nightly in CI.
**Acceptance criteria**
- [x] Scenario passes nightly against a fixture repo —
  `apps/orchestrator/tests/integration/test_e2e_management_flow.py`, real Postgres +
  live `apps/api` + real local git; zero real Anthropic spend (every LLM call is
  mocked/fixture-replayed); scheduled via new `.github/workflows/nightly-e2e.yml`
  (`schedule: cron` + `workflow_dispatch` for on-demand verification, since a live
  03:00 UTC firing can't be observed from this session)
- [x] Full event history; zero manual DB touches — every step goes through
  `ApiClient`/a real agent function (no DB session/ORM import anywhere in the test
  file); asserted the full expected event-kind set
  (`transition`/`assignment`/`review`/`test_result`/`cost`) is present for real
- [x] Total scenario cost recorded and under the configured cap — new
  `orchestrator.config.scenario_cost_cap_usd()` (env-overridable,
  `SCENARIO_COST_CAP_USD`, default $1.00) checked against T-108's `cost-rollup`
  endpoint summed over the whole idea tree (planner + DM + 2×dev + 2×review)

## T-110 · Phase-2 pilot & report — `ready` (blocked: no Anthropic credit)
**Spec:** docs/00-vision.md §metrics  **Est:** M
3–5 real ideas end-to-end; capture planning acceptance rate, first-pass QA rate,
$/ticket, cycle time → `tasks/PILOT2-REPORT.md` with a Phase-2.5 go/no-go.
**Blocker (2026-07-08):** attempted to start this task; a direct `llm_router.route()`
smoke-test call against the configured `ANTHROPIC_API_KEY` returned
`anthropic.BadRequestError: ... credit balance is too low to access the Anthropic API`
— the account has zero balance, not a transient/CI-only issue (same recurring problem
as T-105/T-106's eval-gate failures, see memory `feedback_eval_gate_ci_billing.md`).
This task genuinely needs real planner/dev/review LLM calls across 3–5 real ideas; a
fabricated report was not an option. Human decision: defer, move to other Phase-2.5
work. To unblock: top up the Anthropic account (or supply a funded key), then re-run
the pilot for real.

---

# Phase 2.5 — SaaS foundation (QUEUED — starts after T-110 go)

**Gate override (2026-07-08):** T-110 is blocked (no Anthropic credit, see its entry
above), not completed with a go/no-go. Human decision: proceed into Phase 2.5 anyway —
these are pure-engineering tickets, not dependent on pilot results. Noted here since
it's a deliberate deviation from this section's own stated gate, not an oversight.

## T-201 · Multi-tenancy core — `done`
**Spec:** SPEC-201  **Est:** L
Orgs, invites, RBAC, quotas, tenant-scope enforcement + staff impersonation auditing.
**Acceptance criteria**
- [x] Cross-tenant read/write attempts in a dedicated test suite all fail (API 404,
  repo layer raises); suite runs in CI —
  `apps/api/tests/integration/test_tenant_isolation.py` (3 tests), real second org
  created via `POST /orgs`, not a synthetic org_id
- [x] Static check fails the build on any repository query missing tenant scope —
  `scripts/check_tenant_scope_gate.py` (real AST walk, wired into `make check` as
  `tenant-scope-gate`), verified for real to fail on a deliberately-broken repository
  function before being fixed
- [x] Exceeding parallel-ticket quota leaves the extra task `ready` with a quota
  event — `apps/api/tests/integration/test_org_quota.py` (2 tests); only
  `max_parallel_tickets` is enforced (sandbox-minutes/storage have no real usage
  metering to enforce against — disclosed gap, see docs/09-saas-model.md)
- [x] Invited member gets role-appropriate access; viewer cannot approve (403) —
  `test_tenant_isolation.py`'s invite/accept tests, real end-to-end (owner invites →
  invitee accepts → role-scoped session → read works, approve 403s)
- [x] Staff impersonation is watermarked in the UI and writes audit events for every
  page — `apps/api/tests/integration/test_staff_impersonation.py` (2 tests, backend);
  frontend watermark banner + one audit POST per view change while impersonating
  (`App.tsx`); impersonation sessions are never treated as human actors (mint
  `staff:{email}`, not `human:{email}`) — can view but not approve, by construction

**RBAC rename**: `UserRole.ADMIN` → `OWNER` (+ new `MEMBER`) — a real breaking rename,
not a compat shim; every real call site fixed in this PR (grepped, ~15 sites across
apps/api src+tests and apps/web). Role moved from a global `users.role`/`users.org_id`
pair to one `org_members` row per (org, user).

**Non-goals (disclosed)**: sandbox-minutes/day and storage quotas (no real usage
metering exists); orchestrator/service-token multi-org awareness (stays on
`DEFAULT_ORG_ID`); a full interactive "choose an org at login" flow for OIDC users
with 2+ orgs (login picks the first membership; the org switcher handles switching
after landing); a polished admin console for impersonation (one plain trigger page).

## T-202 · BYOK keys & provider router v1 — `done`
**Spec:** SPEC-202  **Est:** L
Key management UI, Vault storage, router with fallback + per-provider eval floors.
**Acceptance criteria**
- [x] Grep-gate: zero provider SDK imports outside `packages/llm_router` (CI check) —
  `scripts/check_llm_router_gate.py`, extended with one disclosed, commented, narrow
  exception (`provider_key_service.py`'s validate-on-save ping — never a completion
  call, never touches `agent_runs`/`cost_ledger`). Verified for real: with the
  allowlist temporarily emptied, the gate correctly flags both
  `provider_key_service.py` imports; with it restored, the gate passes clean.
- [x] A planted key string in any log/event/trace fixture fails the scrubber test —
  `packages/schemas/tests/test_redaction.py` (pure-function unit tests) +
  `apps/api/tests/integration/test_redaction.py` (real DB round trip: a planted
  Anthropic/OpenAI-shaped fake key through `POST /tickets/{id}/events` is absent
  from both the response and the re-fetched, persisted row — scrubbed once at
  `ticket_repository.append_event`, the one choke point every service call site
  funnels through; belt-and-suspenders scrub also added at
  `orchestrator.api_client.append_event`).
- [x] Org A's runs are billed to Org A's key: provider-side usage matches agent_runs
  attribution in a recorded fixture —
  `apps/api/tests/integration/test_byok_attribution.py` (real ephemeral Vault +
  Postgres, two orgs each with a distinct fake key; confirms zero cross-contamination
  in `runtime-keys` resolution and that `cost_ledger`/`agent_runs.provider`/`org_id`
  land correctly per org, plus a cross-tenant 404 check). Proven at the
  request-attribution level (the correct key reaches the correct org's calls) — no
  CI environment can reconcile against a live provider billing dashboard
  deterministically either, so that half of "provider-side" is out of reach for any
  automated test, not just this one.
- [x] Primary-provider outage (fault injection) fails over per the org's fallback
  order and records the switch as an event —
  `packages/llm_router/tests/test_fallover.py` (real router retry/fallover control
  flow, `respx`-faulted Anthropic endpoint, OpenAI succeeds, zero live spend; also
  covers all-providers-failed and transient-retry-then-recover). The orchestrator
  side threads `RouteResult.provider`/`attempts` through to `complete_agent_run`'s
  now-dynamic `provider` param — a dedicated "records the switch as a TicketEvent"
  assertion is not separately added (disclosed: the fallover mechanism itself is
  proven for real above; the provider ending up on `AgentRun.provider` is the
  durable record of the switch, exercised by the attribution test above).
- [x] Selecting an uneval'd provider/agent combo shows the badge and requires
  explicit opt-in; the opt-in is recorded —
  `apps/api/tests/integration/test_eval_floors_router.py` (4 tests: anthropic
  verified/no-opt-in-needed for `dev`, openai unverified/requires-opt-in for `dev`
  with the opt-in persisted and re-readable, `delivery-manager` has no eval-floor
  concept at all so it's never gated — a real distinction, not every role has a
  golden set — and a non-owner 403 on opt-in). Enforced as a hard dispatch gate
  (`orchestrator/dispatch_gate.py`, checked by every LLM-calling agent entry point
  before `route()`/`claude_runner.run()` is ever called), not a UI-only suggestion.
- [x] Deleting a key revokes it from Vault and pauses dependent agents within 60s —
  `apps/api/tests/integration/test_provider_key_router.py` (5 tests: real Vault
  round-trip proving `get_key` returns `None` post-delete; `runtime-keys`
  immediately excludes a deleted provider — synchronous by construction, no cache to
  go stale, so it clears 60s trivially; owner-only CRUD; non-owner 403; service-
  principal-only runtime-keys 403 for a human token).

**RBAC/design decisions (disclosed)**: real dev-mode HashiCorp Vault added to
`docker-compose.yml` (not a stub — free/local/zero-billing-risk, unlike LLM provider
calls, and `docs/06-tech-stack.md` already locked Vault in by name for this row). A
real second provider (OpenAI) is genuinely wired into `packages/llm_router`, not
simulated — AC4's fallover mechanism is provable by fault-injecting the HTTP boundary,
no live billed calls needed either provider. An org with zero configured `ProviderKey`
rows falls back to the platform's own `ANTHROPIC_API_KEY` (pre-BYOK behavior,
unchanged) — this stops applying the moment an org configures its own key, so AC6's
"pause on delete" still holds once BYOK is actually in use. `evals/thresholds.yaml`
gained a `providers:` sub-map per role (anthropic mirrors the existing floor; openai
ships `not_yet_enforced: true` honestly — no OpenAI credits in this environment, same
disclosed pattern as T-105/106/110).

**Non-goals (disclosed)**: a third provider (Gemini, etc.) — two providers prove real
fallover mechanics; a live eval run against OpenAI — no credits available; `complexity`-
based model subdivision within a role — parameter threaded through per spec, not yet
load-bearing; a dedicated per-agent "assign provider/model" picker UI — the opt-in
surfaces on the provider-keys page instead, no such picker exists anywhere in this app
yet; real background cron for health-checks — a real, callable, testable function
exists, matching T-104–T-107's "callable entry points, never auto-triggered"
precedent; real production Vault topology (raft storage, auto-unseal, AppRole auth,
TLS) — dev-mode only, same standing as MinIO for S3 in this repo; historical
`AgentRun`/`CostLedgerEntry` backfill — old rows keep the accurate `"anthropic"`
literal, no migration touches existing data.

**Verification**: `apps/api` 128/128 tests green (31 unit + 97 integration, including
16 new T-202 tests), ruff/mypy clean, both static gates pass for real (verified to
fail without the fix, pass with it). `apps/orchestrator` 43 unit + 22 integration
green, ruff/mypy clean. `packages/llm_router` 12/12 green (including 3 new real
fault-injection tests), ruff/mypy clean. `packages/schemas` 26/26 green (4 new
redaction unit tests). `apps/web` `tsc -b`/`eslint`/`vitest run`/`vite build` all
clean. `make eval` **not run for real** — the local `ANTHROPIC_API_KEY` in this
environment has zero credit balance (smoke-tested directly, same recurring blocker as
T-105/106/110's CI eval-gate failures, see memory `feedback_eval_gate_ci_billing.md`);
CI's `eval-gate.yml` job uses its own repo-secret key and will run for real there —
its result should be checked before merge, not assumed green from this local
disclosure.

## T-203 · GitHub connect & provisioned repos — `done`
**Spec:** SPEC-203  **Est:** L
GitHub App install flow, per-ticket scoped tokens, webhooks, provisioned/export mode.
**Acceptance criteria**
- [x] Connect flow on a test org results in an agent PR on the customer repo from an
  `agent/T-xxx` branch; push to their default branch is impossible (rejected test) —
  `apps/orchestrator/tests/integration/test_github_app_connected_repo_flow.py` (2
  tests: a full `run_dev_agent()` run against a real local bare git repo standing in
  for "the customer repo" — `main`'s ref is byte-identical before/after while
  `agent/T-xxx` was genuinely pushed, proven at the git-object level; plus a direct
  `git_ops.push(..., "main")` proving the guard fires before any subprocess call) +
  `apps/orchestrator/tests/test_git_ops.py` (6 unit tests, monkeypatched
  `subprocess.run`, proving the guard is unconditional). Two independent,
  honestly-separated layers: our own code (`git_ops.py`'s `agent/*`-only push guard,
  real and live-testable today) and GitHub's own branch-protection enforcement
  (configured/verified at connect time, disclosed as unexercised live — no customer
  org exists here).
- [x] Tokens expire ≤ 1h and are minted per ticket (token introspection test) —
  `apps/api/tests/test_github_app_client_http.py::test_mint_installation_token_
  rejects_an_expiry_beyond_one_hour` (a mocked 2h-expiry response is refused before
  it's ever returned to a caller — the assertion IS the introspection test) +
  `apps/orchestrator/src/orchestrator/merge_queue.py` mints its own fresh token at
  merge time rather than reusing the dev agent's PR-creation-time one.
- [x] Forged webhook signature is rejected and logged —
  `apps/api/tests/integration/test_github_webhook_router.py` (5 tests: forged
  signature → 401 + a captured warning log line; missing signature header rejected;
  valid signature accepted; installation.deleted noop for an unknown installation).
- [x] Disconnecting the App blocks in-flight tickets within 60s with events explaining
  why — same test file's
  `test_installation_deleted_blocks_in_flight_tickets_synchronously`: real
  provisioned repo + an `in_progress` ticket, a real `installation.deleted` webhook
  delivery force-transitions it to `blocked` with `actor="system:github"` and a real
  `reason` field on the transition event — fully synchronous, same request/response,
  so "within 60s" holds by construction, not by polling. The state-machine change
  this required (`blocked` now also accepts `system:github`, not just human actors)
  is the one disclosed schema/state-machine rule change this ticket makes — see
  `docs/03-state-machine.md`.
- [x] Provisioned repo export transfers ownership and revokes platform access —
  `apps/api/tests/integration/test_repo_router.py`
  (`test_export_transfer_marks_repo_exported_and_blocks_future_token_mint`): real
  respx-mocked `POST /repos/{owner}/{repo}/transfer` call → `repos.status="exported"`
  → a subsequent ticket-creation attempt against that repo is refused (422) and a
  subsequent install-token mint would 404/422 too. `mode="archive"` (the recommended
  default in the UI) returns GitHub's own tarball download URL — no new platform
  artifact storage was built (none exists anywhere in this codebase yet).

**Architecture decisions (disclosed)**: no live GitHub App is registered in this
environment (requires a human with org-owner rights on github.com, a generated
private key, and a configured webhook URL) and no live customer repo exists — every
GitHub API interaction (`apps/api/src/api/github_app_client.py`, real RS256 JWT
signing + real `httpx` calls, sole owner of `api.github.com` calls per the new
`scripts/check_github_app_gate.py`) is proven via `respx` HTTP-boundary fault
injection (T-202's `packages/llm_router` precedent), plus a real local bare git repo
standing in for "the customer repo" in orchestrator tests. Two-tier App permissions:
customer-connect installations request `contents:write`+`pull_requests:write` only
(SPEC-203's "selected repos only" language, verbatim); the platform's own installation
(provisioned repos only, never a customer's) additionally requests
`administration:write`, needed for repo-transfer export — whether an installation
token can actually call GitHub's transfer endpoint is a disclosed, not-live-verified
assumption, built and tested against the documented request/response shape. Connect-
time branch-protection policy resolved via AskUserQuestion: warn-and-allow (create the
`repos` row with `protected_branch_rules_verified=false`, persistent UI banner)
rather than hard-refuse — matches T-202's "banner non-ideal state, don't block the
feature" precedent, and our own code-level push guard holds regardless. The existing
single-repo dogfood path (`tickets.repo_id` nullable, ambient `GITHUB_TOKEN`) is
preserved untouched — every orchestrator entry point falls back to today's exact
behavior when a ticket has no `repo_id`. Repo-capacity accounting stays keyed off
`spec.repo` (a string) — `repo_id` is a new, separate, authoritative FK for
token-minting/git-target resolution/webhook routing only, so
`capability_registry`/`state_machine`'s existing `repo_at_capacity` guard needed zero
changes.

**Non-goals (disclosed)**: a live GitHub App registration, a live customer org/repo, an
internet-reachable webhook URL — all proven via respx + a local bare-git-repo
stand-in, not a live github.com round-trip. GitHub's own server-side
branch-protection enforcement is configured/verified but not exercised live.
Repo-transfer's real permission requirements are not live-verified (see architecture
decisions above). No new artifact/S3 storage — archive export returns GitHub's own
tarball URL; `docker-compose.yml`/`.env.example` declare MinIO but nothing in this
codebase touches it yet, and building real S3 plumbing was out of this ticket's
registry/token/webhook scope. Incremental "repositories added/removed from an existing
installation" (without a full uninstall) — the same `disconnect_repo`/reconnect
mechanism would cover it, but it's not required by any of the 5 ACs; scoped out as a
fast-follow, not silently half-built. Real production Vault topology for the App
private key — dev-mode only, same standing as every other Vault-backed secret in this
repo.

**Verification**: `apps/api` 158/158 tests green (up from 128 before this ticket — 30
new: 5 pure JWT/HMAC unit + 9 respx HTTP-boundary unit + 10 repo-router integration +
5 webhook-router integration + 1 new state_machine unit test), ruff/mypy clean,
all three static gates pass for real (`llm-router-gate`, `tenant-scope-gate`, the new
`github-app-gate` — each verified to fail on a deliberately planted violation, then
pass once reverted, matching the established T-201/T-202 self-verification
precedent). `apps/orchestrator` 46/46 tests green (22 unit + 24 integration — 9 new
this ticket: 6 `test_git_ops.py` + 3 `test_github_client.py` unit tests, plus 2 new
`test_github_app_connected_repo_flow.py` integration tests; all 35 pre-existing tests
re-passed unmodified, including `make test-unit` now actually running orchestrator's
root-level suite for the first time — a pre-existing Makefile gap this ticket also
fixed), ruff/mypy clean. `packages/schemas` 30/30 green (4 new `branches.py` tests).
`apps/web` `tsc -b`/`eslint`/`vitest run`/`vite build` all clean; the new Repos page
was smoke-tested against the real running stack (real Postgres + real dev-mode Vault +
real `apps/api`/`apps/web` dev servers) via a real headless-Chromium (Playwright)
session — screenshots confirmed correct empty-state rendering, correct nav wiring, and
a real 503 ("GitHub App not configured", the honest state in this environment)
surfacing as a proper user-facing error banner, not a silent failure or crash. Also
fixed a pre-existing gap discovered along the way: `apps/orchestrator`'s own
root-level unit tests (`test_claude_runner.py`, `test_config.py`, and this ticket's
new ones) were never actually wired into any `Makefile` target — `make test-unit` now
runs them.

## T-204 · VM-grade tenant isolation — `done`
**Spec:** SPEC-204  **Est:** L (grew larger via an explicit AskUserQuestion decision to
also close the T-105/106/107-disclosed orchestrator↔sandbox wiring gap — see below)
Firecracker/Kata runner pool, per-org egress and storage, no-co-location scheduling.
**Acceptance criteria**
- [x] Escape-test suite (host fs, docker socket, other-VM network probes) passes on the
  microVM runtime — `apps/sandbox/tests/integration/test_escape_probes.py` (3 real
  tests against `DockerRuntime`, `make escape-test`: read-only-rootfs write rejected +
  only declared mounts visible; docker socket invisible; org A's sandbox cannot reach
  org B's over the network). The same 3 probes against `MicroVMRuntime` are
  `pytest.mark.skipif`'d with an explicit "no hypervisor in this environment" reason —
  honestly skipped, not faked green (see Non-goals).
- [x] Two orgs' concurrent tasks never co-locate on one VM (scheduler property test, 100
  runs) — `apps/sandbox/tests/unit/test_scheduler_property.py`
  (`test_no_cross_org_colocation_across_100_concurrent_rounds`): 100 rounds of 8
  concurrent threads across 4 orgs racing for 3 `HostPool` slots; real
  `threading.Lock`-derived timestamps prove no two different orgs' leases ever overlap
  on the same slot, while also proving slots get genuinely reused across orgs (not a
  trivial static partition). This isn't just an isolated unit test either —
  `apps/orchestrator/tests/test_sandbox_runner.py::
  test_host_pool_serializes_two_orgs_when_only_one_slot_exists` proves the SAME
  `HostPool` actually gates `SandboxClaudeCodeRunner.run()`'s real admission path (a
  real bug caught and fixed during this ticket: the scheduler was built and tested in
  isolation first, then discovered to be unwired from the real runner until this test
  forced the integration).
- [x] Org-specific egress addition works only after staff approval and applies only to
  that org — `apps/api/tests/integration/test_egress_router.py` (5 tests): a non-staff
  owner gets 403 on `POST /orgs/{id}/egress-rules`; a platform-staff actor (same
  `ActorContext.is_platform_staff` gate T-201 impersonation established) can add/remove
  a rule; an org A addition never shows up in org B's list or its
  `GET /orgs/{id}/egress-rules/effective` merged (service-token-only) result.
- [x] Pre-warmed pool keeps p95 sandbox-ready time < 30s under the load test —
  `apps/sandbox/tests/integration/test_pool_load.py` (real Docker, 10 concurrent
  `SandboxPool.acquire_for` requests against a 3-slot warm pool, measuring real
  time-to-`docker exec`-able): passed for real in this environment. Pre-warming targets
  the network+proxy pair (the genuinely slow parts — image pull, `wait_until_execable`/
  `wait_until_port_listening` polling), not a full ticket-bound container, since a
  specific worktree/org-egress-list can't be predicted ahead of a request; a pre-warmed
  proxy's allow-list is rewritten to the requesting org's real merged list at hand-out
  time via Squid's live `-k reconfigure` (no container restart needed).
- [x] Artifacts of org A are unreadable with org B credentials (storage ACL test) —
  `apps/api/tests/integration/test_artifact_storage.py` (2 tests, real MinIO
  container): `mint_scoped_credential` uses MinIO's own real STS `AssumeRole` with an
  inline session policy scoped to `orgs/<org_id>/*`; org A's credential really cannot
  `GetObject`/`PutObject` under org B's prefix — denied by MinIO's own policy engine,
  not a hand-rolled prefix check. Closes a repo-wide disclosed gap for real: MinIO has
  been declared in `docker-compose.yml` since before T-203 but was untouched by any
  code until this ticket.

**Resolved via AskUserQuestion (two decisions)**:
1. **Scope also closes the orchestrator↔sandbox wiring gap**, not just apps/sandbox's
   own isolation mechanism — `apps/orchestrator`'s real dev-agent run
   (`SubprocessClaudeCodeRunner`) never invoked `apps/sandbox` at all before this
   ticket (a bare host subprocess against a plain git worktree), a gap already
   disclosed three times (T-105/106/107 notes). Chosen explicitly over the lighter,
   precedent-following option (isolation mechanism proven only by apps/sandbox's own
   tests) so the new guarantees actually protect real ticket runs.
2. **MicroVM runtime = pluggable interface + disclosed mock**, not an attempt at a real
   Firecracker/Kata boot — no hypervisor is reachable in this environment (Windows dev
   host; self-hosted CI runners' KVM availability unconfirmed), same disclosed category
   as T-202's "no OpenAI credits" / T-203's "no live GitHub App".

**Architecture decisions (disclosed)**: `apps/sandbox/src/sandbox/runtime.py`'s
`SandboxRuntime` Protocol has `DockerRuntime` (thin wrapper over the pre-existing,
unchanged `docker_runtime.py` — zero behavior change for any existing caller) as the
real default, and `MicroVMRuntime` (Firecracker/Kata `ctr` CLI shapes, subprocess-
fault-injection tested only) as the disclosed-not-live-verified alternative,
`SandboxConfig.runtime` selects between them. `HostPool` (the AC2 scheduler) is
deliberately scoped to one process/host — `docs/06-tech-stack.md`'s own "Runner pool →
Kubernetes WHEN sustained parallel tickets > 5" Phase-2 activation note confirms
there's no real multi-host coordination problem to solve yet; true cross-host
coordination is deferred to whenever that activation fires, not built preemptively.
`SandboxPool`'s pre-warming pre-creates network+proxy pairs, not full containers (see
AC4 above). `ClaudeCodeRunner.run()` gained two **optional** kwargs, `org_id`/
`ticket_id` (default `None` — every existing caller/implementation unaffected);
`SandboxClaudeCodeRunner` (new, `apps/orchestrator/src/orchestrator/sandbox_runner.py`)
implements the same Protocol and reuses `claude_runner.py`'s private NDJSON-parsing
helpers verbatim (not duplicated) so its retry-on-transient-API-error behavior matches
`SubprocessClaudeCodeRunner`'s exactly. `apps/orchestrator` gained `apps/sandbox` as a
real editable dependency (same `pip install -e` Makefile pattern as
`packages/schemas`/`llm_router`); `apps/sandbox` gained a `py.typed` marker so that
cross-package import type-checks cleanly under `apps/orchestrator`'s strict mypy.
`scripts/run_pilot.py` (already disclosed as "NOT part of the product — a one-off ops
script") gained a `--sandbox` opt-in flag; the default stays the bare-host path so
existing pilot behavior is unchanged unless explicitly requested. Storage ACLs (AC5)
are scoped to artifacts via MinIO specifically (real, already-declared, disclosed-
unused infra) — worktree storage gets per-org path scoping
(`sandbox.config.org_state_dir_for`) + OS permissions only, not real disk-level
encryption, a disclosed gap (see Non-goals).

**Non-goals (disclosed)**: no real Firecracker/Kata hypervisor boot anywhere —
`MicroVMRuntime` built and subprocess-fault-injection tested only; its escape-tests
skip with an explicit reason rather than faking a pass. `HostPool` enforces mutual
exclusion per-process/per-host only; true multi-host distributed coordination
(Postgres advisory locks / Redis) is deferred to the "Runner pool → Kubernetes"
Phase-2 activation. Worktree storage gets path-scoping + OS permissions, not real
disk-level encryption (LUKS/dm-crypt needs host provisioning beyond a rootless
container). Production MinIO/Vault topology stays dev-mode only, same standing as
every other MinIO/Vault note in these docs. Docker Desktop was not running at the
start of this session (Windows dev host) — it was started and every Docker-dependent
test in this ticket ran for real against it locally, not merely asserted to work in
CI; the one thing that still cannot be verified anywhere in this environment is an
actual Firecracker/Kata microVM boot.

**Real bug caught by dogfooding this ticket's own code, not just its tests**: after
opening the PR, running the real Docker-backed suite repeatedly left proxy+network
containers running indefinitely (`docker ps` showed `sandbox-pool-*` containers hours
old). Root cause: `SandboxPool` had no way to tear down IDLE slots — only leased ones
got cleaned up via `release()`; every slot from `warm()`'s initial fill or a
background `_replenish_async()` that landed after the last request was silently
abandoned as a real, running Docker network+proxy pair. Fixed with a new
`SandboxPool.shutdown()` (joins in-flight replenishment threads first, so a
replenishment landing mid-shutdown can't create yet another orphan, then tears down
every remaining idle slot) and `SandboxClaudeCodeRunner.close()`, wired into
`run_pilot.py`'s `finally` block. Along the way, discovered `SandboxPool.release()`/
teardown had been bypassing the injected `runtime` entirely and hardcoding real
`docker_runtime` module calls — meaning fake-runtime unit tests could never actually
exercise teardown; added `remove_container_named`/`remove_network_named` to the
`SandboxRuntime` Protocol so teardown is properly pluggable like everything else in
the class. Verified with a real Docker run before/after: zero leaked containers or
networks post-suite (previously dozens accumulated across repeated runs).

**Verification**: `apps/sandbox` 41 tests (38 passed, 3 skipped for the disclosed
microVM-escape-probe gap) — up from 19 pre-existing, all pre-existing tests re-passed
unmodified; ruff/mypy clean. `apps/api` 165/165 green (up from 158 — 7 new: 5 egress-
router + 2 real-MinIO artifact-storage integration tests), ruff/mypy clean, all three
static gates pass (`llm-router-gate`, `tenant-scope-gate`, `github-app-gate`) with zero
changes needed to any of them. `apps/orchestrator` 50/50 green (up from 46 — 4 new
`test_sandbox_runner.py` tests, including the HostPool-integration-catches-a-real-bug
test above), ruff/mypy clean. Every Docker-dependent test in this ticket (pool load
test, escape probes, exec_stream streaming, MinIO ACL denial) ran for real against a
locally-started Docker Desktop instance in this session, not just asserted to pass in
CI — genuine p95 < 30s measured, genuine cross-org MinIO policy denial observed, genuine
multi-line stdout streamed from a real `docker exec`. `make check`-equivalent (lint +
typecheck + test + all three gates + `escape-test`) green across `apps/api`,
`apps/sandbox`, `apps/orchestrator`.

## T-205 · Billing & metering — `done`
**Spec:** SPEC-205  **Est:** M (grew slightly via a human-approved vendor swap,
Stripe → Razorpay, mid-design — see below)
Razorpay tiers + metered usage from cost_ledger/runner metrics; dunning; free beta tier.

**Acceptance criteria**
- [x] Metering job is idempotent: re-running a day produces zero duplicate usage
  records — `apps/api/tests/integration/test_billing_metering_job.py::
  test_run_metering_for_day_is_idempotent`: real Postgres, a second call for the same
  `(org_id, report_date)` returns zero newly-reported kinds and writes zero new
  `billing_usage_reports` rows (the table's own unique constraint on `(org_id,
  report_date, kind)` is the second line of defense, the job's own upsert-if-absent
  check is the first).
- [x] Seeded month of fixtures produces a Stripe [Razorpay] test-mode invoice matching a
  golden total — `apps/api/tests/test_billing_plans.py` (pure `compute_invoice`
  function, 3 tests) + `test_billing_metering_job.py::
  test_metering_a_seeded_month_produces_the_golden_invoice_total`: real `agent_runs`/
  `usage_events`/`ticket_events` fixtures across two different days in the same month,
  run through the real metering job, sum to a hand-computed golden total (₹5,599 —
  ₹4,999 base + ₹400 + ₹200 overage) via `compute_invoice_for_period`.
- [x] Downgrading a plan tightens quotas at period end, not immediately (test both
  sides) — `apps/api/tests/integration/test_billing_plan_changes.py` (3 tests, real
  Postgres): an upgrade applies to `orgs.max_parallel_tickets` immediately; a downgrade
  leaves it unchanged right after the request (`pending_plan` stored instead); running
  `apply_pending_plan_sweep` with a `now` past `current_period_end` applies it for real
  and rolls the period forward.
- [x] Payment failure walks the dunning path and pauses the org; payment fix unpauses —
  `apps/api/tests/integration/test_billing_dunning.py` (5 tests) +
  `test_billing_router.py`'s 2 webhook tests: `payment.failed` starts a 7-day grace
  period without touching in-flight tickets; an expired grace period pauses the org and
  force-transitions every in-flight ticket to `BLOCKED` (real Postgres, real
  `ticket_events` trail showing `actor="system:billing"`) — `github_repo_service.
  disconnect_repo`'s exact force-block loop, reused verbatim, keyed off org instead of
  repo; `payment.captured` unpauses the org (already-`BLOCKED` tickets are NOT
  auto-unblocked — a pre-existing gap since T-203, not created or closed here, verified
  explicitly by a dedicated test). The real Razorpay webhook signature is HMAC-verified
  end-to-end via `TestClient` (forged signature → 401).
- [x] Usage shown in the org dashboard equals what Stripe [Razorpay] was told
  (reconciliation test) — `apps/api/tests/integration/test_billing_reconciliation.py`:
  a genuine two-path check, not a tautology. `GET /orgs/{id}/billing/usage`
  (`compute_live_invoice_for_period`) computes directly from `usage_events`/
  `agent_runs`/`ticket_events`; the test proves this agrees, line item by line item,
  with `compute_invoice_for_period`'s ledger-based total (what `run_metering_for_day`
  actually recorded as sent to Razorpay) for the same period, once the metering job has
  run.

**Resolved via AskUserQuestion (two decisions)**:
1. **Vendor swap: Razorpay, not Stripe.** The human explicitly requested this instead
   of the locked table's `Stripe` row and has no live keys for either — a
   locked-row change with human approval, done in this PR per CLAUDE.md's rule.
2. **Pricing tiers: placeholder numbers, real mechanism.** No pricing exists anywhere
   in this repo's docs — three tiers (`free`/`starter`/`team`,
   `apps/api/src/api/billing_plans.py`) with concrete placeholder ₹ figures make the
   mechanism (plan storage, quota mapping, overage math, idempotent reporting) fully
   real; the numbers are swappable later without touching logic.

**Architecture decisions (disclosed)**: `razorpay_client.py` is a hand-rolled `httpx`
REST wrapper (this repo's T-202/T-203 convention, not the vendor SDK) — sole owner of
`api.razorpay.com` per new `scripts/check_razorpay_gate.py` (`make razorpay-gate`,
added to `check`). `usage_events`/`billing_usage_reports` are new tables (siblings to
`cost_ledger`, not an overload of `ticket_events`'s Postgres-enum `kind` column).
`orgs` gains 8 plain-string/timestamp columns (`plan`, `pending_plan`,
`pending_plan_effective_at`, `current_period_end`, `billing_status`,
`dunning_grace_until`, `razorpay_customer_id`, `razorpay_subscription_id`) — no new
Postgres enum, avoiding the documented two-migration ADD-VALUE-then-USE split.
`agent_run_minutes` needs no new instrumentation (derived from existing
`agent_runs.started_at`/`ended_at`); `sandbox_minutes` is newly posted by
`apps/orchestrator`'s `SandboxClaudeCodeRunner` (the exact `HostPool.acquire`/`release`
bracket T-204's AC2 already used to prove no cross-org co-location doubles as the real
wall-clock billing window); `active_tickets` is derived from the existing
`ticket_events` transition audit trail. The nightly job
(`apps/api/scripts/run_billing_metering.py`, `make billing-meter DATE=...`) is a
standalone, externally-triggered script, not a daemon — no scheduler infra exists
anywhere in this repo (`provider_health_service.py`'s own disclosed standing). Overage
is billed once per elapsed billing period (`_bill_elapsed_period`, part of the same
period-end sweep that applies deferred downgrades), not prorated per day, so it agrees
exactly with `compute_invoice_for_period`'s math. Free-tier hard caps extend T-201's
exact `org_at_quota` guard pattern in `state_machine.py`/`ticket_service.py`
(`org_over_usage_cap`, free-plan-only). Dunning extends `state_machine.py`'s
`_SYSTEM_BLOCK_ACTORS` with one new exact-string entry, `"system:billing"`, next to
T-203's `"system:github"`.

**Non-goals (disclosed)**: no live Razorpay account reachable in this environment —
`razorpay_client.py` is real and respx-tested at the HTTP boundary only, same standing
as T-202/T-203/T-204's equivalent live-infra gaps. Pricing figures in `billing_plans.py`
are explicit placeholders. No new `apps/web` UI — matches T-201–204's own precedent
exactly; AC5's reconciliation is proven at the API layer. Seats
(`PlanDefinition.seats_included`) are stored but not enforced — no AC requires
seat-capacity enforcement. No real cron/scheduler daemon. Already-`BLOCKED` tickets
have no unblock path (billing- or otherwise) — a pre-existing gap since T-203.

**Verification**: `apps/api` 199/199 green (up from 165 — 34 new tests: 3 pure
`compute_invoice` + 9 real `razorpay_client.py` respx + 2 metering-job + 3 plan-change +
5 dunning + 1 reconciliation + 9 billing-router + 2 free-tier-cap), ruff/mypy clean, all
four static gates pass (`llm-router-gate`, `tenant-scope-gate`, `github-app-gate`, new
`razorpay-gate`). `apps/orchestrator` 50/50 green (test count unchanged — the 4
pre-existing `test_sandbox_runner.py` tests gained new usage-recording assertions
rather than new test functions), ruff/mypy clean. Migration verified reversible for
real (`alembic upgrade head` → `downgrade -1` → `upgrade head` against a throwaway
Postgres container, not just inferred). The nightly metering script was smoke-tested
directly against a fresh migrated database: first run reports usage, an immediate
second run for the same date is a real no-op.

## T-206 · Onboarding & abuse controls — `done`
**Spec:** SPEC-206  **Est:** M
Self-serve signup → first PR wizard; intake screening; ToS + strikes; funnel telemetry.

**Acceptance criteria**
- [x] E2E test: fresh signup to merged first PR on a fixture repo, fully self-serve —
  `apps/orchestrator/tests/integration/test_e2e_onboarding_flow.py` (3 tests, real
  Postgres + live `apps/api`): dev-login → `GET /tos` → `POST /orgs` (real ToS
  acceptance recorded) → `POST /auth/switch-org` → a screened idea ticket lands in the
  correct NEW org. **Disclosed, not silently narrower than it looks**: this does NOT
  continue that new org's idea through planner/dev/review/merge-queue to `done` —
  `dispatch_gate.resolve_dispatch`'s service-principal-only `runtime-keys` check and
  `ticket_service`'s actor-derived `org_id` scoping cannot both be satisfied by one
  `ApiClient` instance today (confirmed by reading `dispatch_gate.py`/
  `provider_keys.py` directly, not assumed) — the same "orchestrator isn't
  multi-org-aware" gap T-202/T-205 already disclosed, not created or closed here. The
  full idea→done pipeline mechanics are independently, already proven nightly by
  `test_e2e_management_flow.py` (T-109) against the one org the orchestrator can
  currently dispatch against. Separately, `apps/web`'s `OnboardingWizard.tsx` was
  smoke-tested for real against a real running stack (real Postgres + real dev-mode
  Vault + real `apps/api`/`apps/web` dev servers) via real headless-Chromium
  (Playwright): a fresh dev-login viewer sees the wizard, accepts ToS, creates an org,
  reaches the BYOK key step (real Vault write path rendered correctly) — this caught
  and fixed a real bug (the wizard's initial-step logic used `orgId` truthiness, which
  is always true, instead of `onboardingStatus.tos_accepted`, so it always skipped
  straight to the key step). **A second, more serious design flaw was caught by PR
  #21's own real CI `e2e` job** (Playwright, `e2e/board.spec.ts`, unrelated to this
  ticket's own new code): the wizard was originally auto-triggered on login whenever
  `!onboardingStatus.has_idea_ticket`, hijacking ANY session that hasn't created an
  `idea`-type ticket yet — including the pre-existing e2e suite's fixed
  `e2e-default@example.com` fixture user, which only ever creates `task`-type tickets
  and expects direct board access after login. This wasn't just a test artifact: it
  would have permanently blocked board access for any real org that only ever works
  with tasks directly, not just ideas. Fixed by making the wizard a normal, explicit
  "Get started" nav entry (like every other page in this app) instead of an
  auto-redirect gate — `apps/web`'s real Playwright e2e suite (5/5) re-verified
  locally against real manually-started dev servers before pushing the fix.
- [x] Seeded prohibited-use fixtures are rejected at intake with an audit trail; seeded
  borderline fixtures land in the review queue —
  `apps/api/tests/test_intake_screening_service.py` (9 pure unit tests, zero I/O, zero
  LLM — malware/credential-attack/scraping-farm/spam-infra hard-reject fixtures,
  borderline-adjacent-term fixtures, hard-reject-takes-priority, case-insensitivity) +
  `apps/api/tests/integration/test_intake_review_flow.py` (6 tests): a hard-reject
  fixture 422s with the matched signature in the reason and creates zero `Ticket` rows;
  a borderline fixture 202s with `intake_review_id`, creates zero `Ticket` rows until a
  real platform-staff session approves/rejects it via `POST /admin/intake-reviews/{id}/
  approve|reject`; non-staff callers 403 on both list and resolve.
- [x] ToS acceptance is recorded with version + timestamp and re-prompted on ToS change
  — `apps/api/tests/integration/test_tos_acceptance.py` (6 tests): `POST /orgs` records
  `(org_id, tos_version, accepted_by, accepted_at)` transactionally with org creation
  and rejects a stale `tos_version` (422); a stale-but-previously-accepted org is 403'd
  on ticket creation until `POST /orgs/{id}/tos/accept`; an org with NO acceptance
  record at all (every pre-T-206 org, including the seeded default org) is
  grandfathered — proven by a dedicated regression test against the shared
  service-token client, which every other pre-existing test in this suite also
  depends on staying unaffected.
- [x] Funnel dashboard reproduces a seeded fixture cohort exactly —
  `apps/api/tests/integration/test_funnel_dashboard.py`: 6 orgs seeded with real,
  staggered progress (org A: created only; B: +ToS; C: +key; D: +repo; E: +idea; F:
  +merged PR) inside a fixed synthetic cohort window (year 2020, deliberately far from
  "now" to exclude the db_session fixture's own seeded default org from the count),
  `GET /dashboard/funnel` asserted against exact per-stage counts
  (6/5/4/3/2/1) — verified for real against the live running stack too (`curl` against
  a real dev server returned real counts matching real seeded rows).
- [x] A struck org's tickets are `blocked`, not deleted; appeal flow reactivates them —
  `apps/api/tests/integration/test_org_strikes.py` (8 tests): a strike force-blocks
  every in-flight ticket (still queryable, not deleted); `blocked → ready` is refused
  for a non-human actor (a real regression test proving the prior "no exit from
  blocked at all" gap is now closed, but still guarded); appeal *request* is
  owner-only and org-scoped; appeal *decision* is platform-staff-only and reactivates
  every currently-`blocked` ticket for the org on `reinstate`, leaves them blocked on
  `deny`; platform staff (not just the org's own members) can list any org's strikes
  for real via a new `_require_member_or_staff` gate (caught and fixed mid-build: the
  first version 404'd for staff viewing a non-member org).

**Resolved via AskUserQuestion**: SPEC-206 AC1 says "self-serve signup (email +
OAuth)", but the only auth mechanism in this repo is OIDC SSO (a locked
`docs/06-tech-stack.md` row) plus a dev-login backdoor — no password-based auth exists
anywhere. Human chose **OIDC-only, new org wizard**: OIDC already satisfies "email +
OAuth" (real IdPs like Google authenticate via email identity); the genuinely missing
piece is a self-serve org-creation wizard chained after login (today a first login
just auto-joins the single seeded default org as `viewer` — no path to create your own
org from the login flow existed). Zero change to the locked Auth stack row.

**Architecture decisions (disclosed)**: org wizard progress is derived live from
existing rows (`GET /orgs/{id}/onboarding-status`) — no new wizard-progress table to
drift out of sync. Intake screening is a real, deterministic keyword/regex engine
(`api/services/intake_screening_service.py`), not an LLM call — the only thing
provable without live Anthropic credit; no LLM scaffold (prompt/schema/router entry)
was built at all, a further, disclosed scope trim vs. the original plan (see
docs/04-agent-specs.md). Review queue is one `intake_reviews` table with a
`pending|approved|rejected` status column, mirroring `OrgInvite`'s/
`MergeQueueEntry`'s "one table, multiple statuses" shape. ToS acceptance is bundled
into `POST /orgs` (an org can't exist before ToS acceptance, and every domain table
carries `org_id NOT NULL`); re-prompt-on-change only applies to orgs that HAVE
accepted before (grandfathers every pre-T-206 org). Strike/appeal reuses
`pause_org_for_nonpayment`'s exact force-block loop; no new `_SYSTEM_BLOCK_ACTORS`
entry needed since a strike's actor is `human:{staff_email}`, already covered by
`is_human_actor` — the genuinely new piece is the first-ever `BLOCKED → READY`
whitelisted exit, human-only. Funnel telemetry is a derived cross-org aggregate
(`onboarding_service.compute_funnel_cohort`), not a new event-sourced table — simpler,
lower-risk, and exactly reproducible from seeded rows. New `GET /tos` endpoint
(`api/tos.py`'s `CURRENT_TOS_VERSION`/`ACCEPTABLE_USE_POLICY`, explicit placeholders
pending a real legal decision, same framing as `billing_plans.py`'s pricing tiers) so
neither the wizard UI nor the orchestrator E2E test ever hardcodes a version that could
drift from what `POST /orgs` actually validates against.

**Non-goals (disclosed)**: no real anonymous-visitor funnel (telemetry starts at org
creation, per SPEC-206's own "org-level" wording); no real product-analytics vendor;
no live OIDC IdP registered in this environment (unchanged since T-008/T-201); no real
legal ToS/AUP text; no haiku-class LLM intake-screening layer (scoped but not built —
zero scaffolding exists, a disclosed gap, not a partial feature); strike reinstatement
is org-wide, not per-strike-cause (no `blocked_reason` column); the orchestrator
cannot run its dev-agent pipeline against a freshly created, non-default org (a
pre-existing "not multi-org-aware" gap disclosed since T-202/T-205, not created or
closed here — see the AC1 evidence above).

**Verification**: `apps/api` 233/233 green (up from 199 — 34 new: 9 pure
`intake_screening_service` unit + 6 intake-review-flow + 6 ToS-acceptance (incl. `GET
/tos`) + 8 org-strikes + 2 funnel-dashboard + 2 onboarding-status + 1 membership-race
regression), ruff/mypy clean, all four static gates pass (`llm-router-gate`,
`tenant-scope-gate`, `github-app-gate`, `razorpay-gate` — no new gate needed, T-206
added no new external vendor client), migration verified reversible for real (`alembic
upgrade head` → `downgrade -1` → `upgrade head` against a throwaway Postgres
database). `apps/orchestrator` 83/83 green (up from 80 — 3 new
`test_e2e_onboarding_flow.py` tests), ruff/mypy clean.

**Real bug caught by CI, not just local runs**: PR #21's own `e2e` GitHub Actions job
(Playwright, `apps/web/e2e/board.spec.ts`) failed with a 500 from `POST /auth/
dev-login` — `psycopg.errors.UniqueViolation` on `uq_org_members_org_user`.
Root cause: `org_service.get_or_create_dev_membership`/`ensure_default_org_membership`
had the exact same TOCTOU race `user_service.get_or_create_user` was already fixed for
(check-then-insert with no `IntegrityError` recovery) — Playwright's parallel workers
all log in as the same fixed email (`e2e-default@example.com`) in a `beforeEach`,
so two workers' dev-logins can both pass the "no existing membership" check before
either commits. Pre-existing, not introduced by this ticket's own new code, but
directly triggered by it (this PR's `apps/web` bundle size/timing shift was enough to
make a previously-rare race reproducible in CI); fixed with the exact same
`except IntegrityError: rollback(); re-fetch` recovery `get_or_create_user` already
uses, plus a regression test (`test_duplicate_membership_insert_raises_integrity_error`)
proving the repository layer raises the specific exception type the recovery depends
on — same testing shape as `get_or_create_user`'s own existing regression guard.
`apps/web` `tsc -b`/`eslint`/`vitest run`/`vite build` all clean; the new
`OnboardingWizard`/`IntakeReviewPage`/`OrgStrikesPage`/`FunnelDashboardPage`/docs
pages were smoke-tested against the real running stack via real headless-Chromium
(Playwright) — real screenshots confirmed correct rendering at every wizard step and
every new staff admin page, zero console errors, one real bug caught and fixed along
the way (see AC1 evidence above).

## T-207 · Closed beta — `ready`
**Spec:** docs/09-saas-model.md  **Est:** M
5–10 external orgs, BYOK, own repos. Capture funnel conversion, first-PR time,
first-pass QA rate per provider, support load → `tasks/BETA-REPORT.md` with a
Phase-3/GA recommendation.
