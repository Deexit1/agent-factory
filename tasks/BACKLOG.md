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

## T-003 · Ticket API & state machine — `ready`
**Spec:** SPEC-001  **Est:** L
Implement SPEC-001 in `apps/api`. All six criteria from the spec apply verbatim.

## T-004 · Board UI — `ready`
**Spec:** SPEC-002  **Est:** L
Implement SPEC-002 in `apps/web` against the real API. All five criteria apply.

## T-005 · Sandbox runner — `ready`
**Spec:** SPEC-003  **Est:** L
Implement SPEC-003 in `apps/sandbox`. All five criteria apply.

## T-006 · Dev agent integration — `ready`
**Spec:** SPEC-004  **Est:** L
Implement SPEC-004 in `apps/orchestrator`. All five criteria apply.

## T-007 · QA gate & bounce loop — `ready`
**Spec:** SPEC-005  **Est:** L
Implement SPEC-005 (CI workflows + webhook + distiller). All five criteria apply.

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
