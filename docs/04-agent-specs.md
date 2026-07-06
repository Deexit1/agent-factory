# 04 — Agent Specifications

Every agent = versioned system prompt (in `prompts/`) + tool allow-list + model +
structured output schema (in `packages/schemas`) + eval suite. Prompt or model changes
must pass the golden-set eval in CI before merge.

| Agent | Default model | Tools | Contract (input → output) |
|---|---|---|---|
| Exec panel (CEO/CFO/CPO) | opus-class | web search, market data, cost tables | Idea → `BusinessCase` (opportunity, costs, risks, recommendation, cited sources) |
| Product Planner | opus-class | repo read-only | Approved idea → epics + `TaskSpec[]` with machine-checkable `AcceptanceCriteria` |
| Delivery Manager | sonnet-class | board API, capacity registry | `TaskSpec[]` → assignments + dependency order |
| Dev agent | Claude Code headless (sonnet; opus if `complexity=high`) | git, terminal, editor, test runner (sandbox only) | `TaskSpec` (+ `FailureReport` on bounce) → branch + PR + checklist |
| Test author | sonnet-class | repo, coverage report | `AcceptanceCriteria` → new/updated tests in the same PR |
| Failure distiller | haiku-class | CI logs, artifacts | raw logs → `FailureReport` (failing test, expected vs actual, suspect files) |
| Review agent | sonnet-class | PR diff, style guide, Semgrep output | PR → comments + block/approve recommendation (human may override) |

## Shared schema contracts (`packages/schemas`)
- `TaskSpec`: id, title, context, constraints, acceptance_criteria[], complexity,
  budget_usd, depends_on[] (sibling task ids), estimate_days (nullable; >1 is a
  non-blocking review flag, not a hard gate), epic_id (nullable)
- `AcceptanceCriterion`: id, description, verification ("test name/pattern that proves it")
- `Epic` (T-103): id, title, description, budget_usd
- `PlannerPlan` (T-103): epics[], tasks[] — the Planner's normal output
- `PlannerQuestions` (T-103): questions[] — Planner output when the idea is under-specified
- `FailureReport`: ticket_id, failing_suite, failing_tests[], expected_vs_actual, suspect_files[], attempt_no
- `BusinessCase`: idea_id, opportunity, market_evidence[cited], cost_estimate, risks[], recommendation

Schemas are versioned; hand-offs validate or the orchestrator rejects the transition.
