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
