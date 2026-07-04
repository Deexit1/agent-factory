# SPEC-004 — Dev Agent Integration

## Goal
Run Claude Code headless inside the sandbox against a TaskSpec; collect a PR.

## In scope
- `apps/orchestrator/agents/dev.py`: builds the agent context from TaskSpec
  (+ FailureReport on bounce), invokes Claude Code headless with a token budget,
  streams transcript lines into ticket_events.
- On completion: commit, push `agent/T-xxx`, open PR via GitHub API, transition
  ticket → `in_qa`.
- Budget metering: every model call recorded in agent_runs + cost_ledger; exceeding
  budget kills the run and transitions → `escalated`.
- Wall-clock timeout (config, default 45 min) with the same escalation path.

## Acceptance criteria
1. Given a toy repo and a TaskSpec ("add /health endpoint returning 200"), the agent
   produces a PR whose diff adds the endpoint and a test (recorded fixture run).
2. Transcript events stream into ticket_events during the run (not only at the end).
3. Setting budget_usd=0.01 causes escalation before completion; state == `escalated`.
4. On bounce, the injected context contains the FailureReport and attempt number.
5. cost_ledger total for the ticket equals the sum of agent_runs.cost_usd.
