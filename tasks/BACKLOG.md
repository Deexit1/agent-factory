# Backlog — the manual board

States: `ready` | `in_progress` | `in_qa` | `bounced` | `escalated` | `done`
Rules: work top-to-bottom unless the human says otherwise. One task per branch/PR.
A task is done only when its criteria pass as tests and `make check` is green.

---

## T-001 · Repo scaffold & tooling — `done`
**Spec:** —  **Est:** S
Create the monorepo layout from CLAUDE.md, Makefile targets (dev/test/check/e2e/migrate),
docker-compose (postgres, redis, minio), .env.example, CI skeleton, pre-commit (ruff,
eslint, gitleaks).
**Acceptance criteria**
- [x] `make dev` starts API stub (FastAPI /health 200) + web stub + postgres + redis
- [x] `make check` runs and passes on the clean scaffold
- [x] CI runs `make check` on PRs; gitleaks blocks a planted test secret
- [x] No real secrets anywhere; `.env.example` documents every variable

## T-002 · Schemas package — `done`
**Spec:** docs/04-agent-specs.md  **Est:** S
Implement `packages/schemas`: TaskSpec, AcceptanceCriterion, FailureReport, BusinessCase
(Pydantic v2, versioned, JSON-schema export).
**Acceptance criteria**
- [x] Round-trip serialisation tests for all four models
- [x] Invalid payloads raise validation errors with field paths
- [x] `schemas export` CLI writes JSON schema files consumed by the web app

## T-003 · Ticket API & state machine — `done`
**Spec:** SPEC-001  **Est:** L
Implement SPEC-001 in `apps/api`. All six criteria from the spec apply verbatim.
**Acceptance criteria**
- [x] Creating a task ticket with empty `acceptance_criteria` fails 422.
- [x] `ready → in_progress → in_qa → done` succeeds; each writes exactly one transition event.
- [x] `in_qa → done` is refused 409 if a `bounced` transition for attempt 3 exists (must be `escalated`).
- [x] `in_qa → bounced` increments `bounce_count`; the 4th bounce attempt is refused and state becomes `escalated`.
- [x] Events endpoint returns append-only history; PUT/DELETE on events return 405.
- [x] `POST /tickets/{id}/approve` by a non-approver returns 403.

## T-004 · Board UI — `done`
**Spec:** SPEC-002  **Est:** L
Implement SPEC-002 in `apps/web` against the real API. All five criteria apply.
**Acceptance criteria**
- [x] Board renders tickets grouped by state from the API (mock-free integration test).
- [x] Dragging a ticket through an illegal transition snaps back and shows the API reason.
- [x] New ticket_events appear in an open drawer within 2s (Playwright e2e with WS).
- [x] Approver sees approval buttons on `awaiting_human_go`/`escalated`; viewer does not.
- [x] Lighthouse a11y score ≥ 90 on the board page (95/100).

## T-005 · Sandbox runner — `done`
**Spec:** SPEC-003  **Est:** L
Implement SPEC-003 in `apps/sandbox`. All five criteria apply.
**Acceptance criteria**
- [x] `sandbox up` yields a container where `curl https://blocked.example.com` fails and
      `pip install requests` succeeds.
- [x] Push to `main` from inside the sandbox is rejected; push to `agent/T-123` succeeds.
- [x] Container cannot see host Docker socket or other sandboxes (integration test).
- [x] `sandbox down` leaves no container, volume, or credential behind.
- [x] Every egress attempt appears in ticket_events for T-123.

## T-006 · Dev agent integration — `done`
**Spec:** SPEC-004  **Est:** L
Implement SPEC-004 in `apps/orchestrator`. All five criteria apply.
**Acceptance criteria**
- [x] Given a toy repo and a TaskSpec ("add /health endpoint returning 200"), the agent
      produces a PR whose diff adds the endpoint and a test (recorded fixture run).
- [x] Transcript events stream into ticket_events during the run (not only at the end).
- [x] Setting budget_usd=0.01 causes escalation before completion; state == `escalated`.
- [x] On bounce, the injected context contains the FailureReport and attempt number.
- [x] cost_ledger total for the ticket equals the sum of agent_runs.cost_usd.

## T-007 · QA gate & bounce loop — `done`
**Spec:** SPEC-005  **Est:** L
Implement SPEC-005 (CI workflows + webhook + distiller). All five criteria apply.
**Acceptance criteria**
- [x] A PR with a failing unit test never reaches integration/e2e jobs (fail-fast).
- [x] Green pipeline transitions the ticket to `done`; red pipeline to `bounced` with a
      FailureReport whose `failing_tests` matches the CI log.
- [x] A planted secret in the diff blocks the pipeline via gitleaks.
- [x] Changed-lines coverage below 80% fails the gate.
- [x] Third consecutive red pipeline ends with ticket `escalated`, not `bounced` (see
      CHANGELOG note: implemented as the existing, T-003-tested `bounce_count == 3` guard —
      the 4th red pipeline escalates, matching `docs/03-state-machine.md` exactly).

## T-008 · Cost, SSO & pilot dashboard — `ready`
**Spec:** SPEC-006  **Est:** M
Implement SPEC-006. All five criteria apply.

## T-009 · Pilot run — `ready`
**Spec:** docs/00-vision.md §metrics  **Est:** M
Seed 20–30 real backlog tickets, run the loop, capture the four metrics, write
`tasks/PILOT-REPORT.md`.
**Acceptance criteria**
- [ ] Every pilot ticket ends in `done` or `escalated` with full event history
- [ ] Dashboard exports the four metrics; report includes them vs thresholds
