# evals/planner

Seeded by T-103 (SPEC-102): 15 hand-authored synthetic idea fixtures — no real ideas
existed to seed this from (the same honesty-over-padding precedent as T-101's dev set).
Each case pairs a small idea (title + description + budget) with a reference
`PlannerPlan` (epics + TaskSpecs). Scored by `orchestrator/evals/planner_scorer.py`:
deterministic checks (schema validity, dependency-graph acyclicity, task-budget sum
within the idea's budget, every acceptance criterion carries a verification hint)
blended 60/40 with the shared haiku-class judge (`orchestrator/evals/judge.py`), same
ratio as the dev set. A `questions[]` response (the Planner declining to produce a
plan) is scored rather than crashing the harness — deterministic score is 0 (no plan
means none of the sanity checks apply) blended with the judge, which is instructed to
score low unless the questions identify a real, material gap.

**Enforced** (`evals/thresholds.yaml`, floor 70). Getting here surfaced two real bugs:
`planner_scorer.invoke_planner` originally crashed on a `questions[]` response instead
of scoring it, and `prompts/planner.md` (bumped to v0.2) never specified the exact
output JSON shape, so the live model returned rich question objects instead of plain
strings and asked unnecessary questions on well-specified ideas. After both fixes, a
full real run against live opus: 15/15 valid plans, zero errors, zero questions,
deterministic_score 100 on every case, combined score avg 88.6 (min 76.8, max 96.8).
