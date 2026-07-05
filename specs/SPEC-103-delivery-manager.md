# SPEC-103 — Delivery Manager Agent

## Goal
Assign `ready` tasks to the right dev-agent profile in dependency order, respecting
capacity, budgets and repo locks.

## In scope
- Capability registry (config): profile → skills, base image, model, max parallel.
- LangGraph node `delivery_manager` (sonnet-class): input = ready tasks + registry +
  in-flight state; output = assignment decisions with reasons (recorded as events).
- Orchestrator enforcement (code, not prompt): dependencies done, budget > 0, per-repo
  concurrency limit, sandbox availability — an assignment violating any is refused.
- Re-assignment on escalation: escalated-and-returned tasks can be routed to a
  different profile or flagged human-only.
- Board: assignment queue view with per-profile utilisation.

## Acceptance criteria
1. Given a seeded dependency chain A→B→C, B is never assigned before A is `done`.
2. Profile max-parallel = 1 with two eligible tasks → second stays `ready` (integration test).
3. An assignment decision event always includes the reason and the considered alternatives.
4. Orchestrator refuses an assignment to a task with spent ≥ budget even if the agent
   proposes it (fault-injection test).
5. Utilisation view matches the DB state under 10 concurrent seeded tasks.
