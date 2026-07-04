# SPEC-005 — QA Gate & Bounce Loop

## Goal
CI pipelines as a hard door: smoke → unit → integration → e2e → static gates; on failure,
distill logs into a FailureReport and bounce the ticket.

## In scope
- GitHub Actions workflows on `agent/*` PRs: ordered jobs, fail-fast smoke first;
  Semgrep, gitleaks, dependency audit as blocking checks.
- Coverage floor on changed lines (80%) via diff-cover.
- Webhook receiver in the API: CI result → transition (`in_qa → done` or `→ bounced`).
- Failure distiller (haiku-class) converting raw logs + artifacts into FailureReport;
  attached to the ticket and the bounce event.
- 3rd failure → `escalated` (orchestrator rule, per state machine).

## Acceptance criteria
1. A PR with a failing unit test never reaches integration/e2e jobs (fail-fast).
2. Green pipeline transitions the ticket to `done`; red pipeline to `bounced` with a
   FailureReport whose `failing_tests` matches the CI log.
3. A planted secret in the diff blocks the pipeline via gitleaks.
4. Changed-lines coverage below 80% fails the gate.
5. Third consecutive red pipeline ends with ticket `escalated`, not `bounced`.
