# evals/planner

Seeded by T-103 (SPEC-102): 15 hand-authored synthetic idea fixtures — no real ideas
existed to seed this from (the same honesty-over-padding precedent as T-101's dev set).
Each case pairs a small idea (title + description + budget) with a reference
`PlannerPlan` (epics + TaskSpecs). Scored by `orchestrator/evals/planner_scorer.py`:
deterministic checks (schema validity, dependency-graph acyclicity, task-budget sum
within the idea's budget, every acceptance criterion carries a verification hint)
blended 60/40 with the shared haiku-class judge (`orchestrator/evals/judge.py`), same
ratio as the dev set.

**Not yet enforced** (`evals/thresholds.yaml`'s `planner.not_yet_enforced: true`).
A real run against live opus (2 of the 15 cases, to bound API spend) showed the model
consistently answering these fixtures with `questions[]` instead of a plan, and
`planner_scorer.invoke_planner` only handles the plan path — it raises instead of
scoring a `questions[]` response gracefully. Before a floor can be set, someone needs
to: (a) decide how a legitimate `questions[]` response should score (partial credit?
a separate pass/fail dimension?) and implement it in `planner_scorer.py`, and/or
(b) check whether these synthetic fixtures are simply under-specified relative to
what the live prompt expects, and enrich them. See `tasks/CHANGELOG.md` (T-103) for
the full finding.
