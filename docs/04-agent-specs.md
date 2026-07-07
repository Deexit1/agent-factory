# 04 — Agent Specifications

Every agent = versioned system prompt (in `prompts/`) + tool allow-list + model +
structured output schema (in `packages/schemas`) + eval suite. Prompt or model changes
must pass the golden-set eval in CI before merge.

| Agent | Default model | Tools | Contract (input → output) |
|---|---|---|---|
| Exec panel (CEO/CFO/CPO) | opus-class | web search, market data, cost tables | Idea → `BusinessCase` (opportunity, costs, risks, recommendation, cited sources) |
| Product Planner | opus-class | repo read-only | Approved idea → epics + `TaskSpec[]` (with `required_skills` domain tags, T-105) with machine-checkable `AcceptanceCriteria` |
| Delivery Manager | sonnet-class | board API, capacity registry | `TaskSpec[]` → skill-matched assignments + dependency order |
| Dev agent | Claude Code headless (assigned profile's model; opus if `complexity=high`) | git, terminal, editor, test runner (sandbox only) | `TaskSpec` (+ `FailureReport` on bounce) → branch + PR + checklist |
| Test author | sonnet-class | repo, coverage report | `AcceptanceCriteria` → new/updated tests in the same PR |
| Failure distiller | haiku-class | CI logs, artifacts | raw logs → `FailureReport` (failing test, expected vs actual, suspect files) |
| Review agent | sonnet-class | PR diff, style guide, Semgrep output (T-106: an injectable string param today — CI's real Semgrep output isn't wired back to the agent yet) | PR → `ReviewResult` (comments + scope_violations + approve/block verdict; human may override) |

## Shared schema contracts (`packages/schemas`)
- `TaskSpec`: id, title, context, constraints, acceptance_criteria[], complexity,
  budget_usd, depends_on[] (sibling task ids), estimate_days (nullable; >1 is a
  non-blocking review flag, not a hard gate), epic_id (nullable), repo, required_skills[]
  (T-105: domain tags matched against capability_registry.yaml profiles by the
  Delivery Manager; empty matches any profile — a routing filter, not a hard gate)
- `AcceptanceCriterion`: id, description, verification ("test name/pattern that proves it")
- `Epic` (T-103): id, title, description, budget_usd
- `PlannerPlan` (T-103): epics[], tasks[] — the Planner's normal output
- `PlannerQuestions` (T-103): questions[] — Planner output when the idea is under-specified
- `FailureReport`: ticket_id, failing_suite, failing_tests[], expected_vs_actual, suspect_files[], attempt_no
- `ReviewResult` (T-106): verdict (approve|block), comments[] (`ReviewComment`: file, line, comment), scope_violations[]
- `BusinessCase`: idea_id, opportunity, market_evidence[cited], cost_estimate, risks[], recommendation

Schemas are versioned; hand-offs validate or the orchestrator rejects the transition.

## End-to-end verification (T-109)
The full chain above (idea → planner → budget approval → Delivery Manager → 2 parallel
profile agents → review → QA → merge queue → done) has one real, nightly-verified
integration test:
`apps/orchestrator/tests/integration/test_e2e_management_flow.py`, run by
`.github/workflows/nightly-e2e.yml` (`workflow_dispatch`-triggerable on demand). Every
LLM call in it is mocked/fixture-replayed (zero real Anthropic spend); only the
merge-queue step runs real, unmodified git mechanics — deliberate, so a scheduled run
can never fail on provider billing instead of a real regression.
