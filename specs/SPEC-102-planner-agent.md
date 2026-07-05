# SPEC-102 — Product Planner Agent

## Goal
`approved` idea → epics + TaskSpec[] with machine-checkable acceptance criteria,
gated by schema validation and eval-derived sanity checks before any human sees it.

## In scope
- LangGraph node `planner`: input = idea ticket (title, description, human-approved
  budget), tools = repo read-only; output = epics[] + TaskSpec[] (packages/schemas),
  or questions[] when under-specified (→ `escalated` for human answers).
- Sanity gates in orchestrator code (not prompt): every task ≤ 1 day estimate flag,
  every criterion carries a `verification` hint, dependency graph is a DAG, sum of task
  budgets ≤ idea budget.
- Board UI: planning review screen — human sees the tree, can edit TaskSpecs inline,
  then approves budget (`planning → ready` writes approval row).
- Planner runs on opus-class model; every run recorded in agent_runs/cost_ledger.

## Acceptance criteria
1. A seeded idea fixture yields TaskSpecs that all pass schema + sanity gates (golden test).
2. An under-specified idea fixture yields questions[], ticket → `escalated`, and the
   human-answer round-trip produces a full plan.
3. A cyclic-dependency plan (fault-injected) is rejected by the DAG gate with a clear event.
4. Task budgets exceeding the idea budget block `planning → ready`.
5. Planner prompt changes are blocked by CI unless `make eval` (planner set) is green.
6. Human edits to a TaskSpec are versioned as ticket_events (before/after payload).
