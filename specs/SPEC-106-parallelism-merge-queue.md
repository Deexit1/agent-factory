# SPEC-106 — Parallel Tickets & Merge Queue

## Goal
Safely run multiple tickets at once on one repo: merge queue, rebase-and-retest,
and a second runner VM.

## In scope
- GitHub merge queue (or bors-style bot) required for all `agent/*` PRs; `in_qa → done`
  only after the queue's rebase-and-retest passes.
- Orchestrator: replace Phase-1 per-repo lock with per-repo concurrency limit (config,
  default 3) + queue-aware completion.
- Conflict path: queue rebase conflict → `bounced` with FailureReport(kind=conflict);
  dev agent resolves on its own branch.
- Runner capacity: second self-hosted runner VM via Terraform/Ansible; runner pool
  metrics (queue wait time) exported to Grafana.
- Load test: 5 concurrent seeded tickets on a fixture repo.

## Acceptance criteria
1. Two tickets editing the same file: first merges; second gets a conflict bounce and
   succeeds after agent rebase (integration test).
2. No ticket reaches `done` without a queue entry (audit query returns zero violations).
3. Concurrency limit 3 with 5 ready tickets → exactly 3 sandboxes exist (test).
4. Load test completes with all 5 tickets `done`/`escalated`, zero orphaned sandboxes,
   and queue wait time visible in Grafana.
5. Terraform apply from a clean state brings up both runners unattended.
