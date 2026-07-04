# SPEC-001 — Ticket API & State Machine

## Goal
FastAPI service exposing tickets with the state machine from `docs/03-state-machine.md`
enforced server-side, and the append-only event log from `docs/02-data-model.md`.

## In scope
- Alembic migrations for: tickets, ticket_events, approvals (others in later specs).
- Endpoints:
  - `POST /tickets` (create; Phase 1 tasks start in `ready`)
  - `GET /tickets` (filter by state/type/assignee, paginated)
  - `GET /tickets/{id}` (with recent events)
  - `POST /tickets/{id}/transition` (body: `to_state`, `actor`; validates whitelist)
  - `POST /tickets/{id}/approve` (gate: idea|budget|deploy|escalation; RBAC `approver`)
  - `GET /tickets/{id}/events` (paginated, newest first)
- Transition + event written in one DB transaction.
- Illegal transitions → 409 with reason, and a rejected-transition event.

## Out of scope
Auth wiring beyond a stub user header (SPEC-006 adds SSO), UI, orchestrator.

## Acceptance criteria
1. Creating a task ticket with empty `acceptance_criteria` fails 422.
2. `ready → in_progress → in_qa → done` succeeds; each writes exactly one transition event.
3. `in_qa → done` is refused 409 if a `bounced` transition for attempt 3 exists (must be `escalated`).
4. `in_qa → bounced` increments `bounce_count`; the 4th bounce attempt is refused and
   state becomes `escalated`.
5. Events endpoint returns append-only history; PUT/DELETE on events return 405.
6. `POST /tickets/{id}/approve` by a non-approver returns 403.
