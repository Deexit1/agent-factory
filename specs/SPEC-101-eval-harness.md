# SPEC-101 — Golden-Set Eval Harness (build FIRST)

## Goal
`make eval`: a blocking CI check that scores agent prompts/routing against versioned
golden sets, per docs/08-evals.md. Nothing in SPEC-102+ merges without this existing.

## In scope
- `evals/` layout: one folder per agent (`planner/`, `dev/`, `review/`, `distiller/`),
  cases as YAML (input payload + reference output + rubric weights),
  `thresholds.yaml` with per-set floors.
- Runner (`apps/orchestrator/evals/`): loads cases, invokes the agent with its CURRENT
  prompt version, scores with (a) deterministic checks, (b) haiku-judge rubric at temp 0.
- Outputs: JUnit XML for CI, markdown summary comment on the PR, scores logged to
  Langfuse with prompt version tag.
- CI wiring: triggers on `prompts/**`, `evals/**`, or routing-config diffs.
- Seed the dev golden set from 10+ Phase-1 pilot tickets (snapshot fixtures).

## Acceptance criteria
1. A deliberate degradation of `prompts/failure-distiller.md` (delete the rules section)
   turns `make eval` red on the distiller set.
2. Restoring the prompt turns it green; both runs visible in Langfuse with versions.
3. Lowering a threshold in `thresholds.yaml` without the CODEOWNERS approval rule fails CI.
4. Judge scoring is reproducible: two runs on identical inputs differ by < 2%.
5. PR comment shows per-set scores and worst-3 failing cases with diffs.
