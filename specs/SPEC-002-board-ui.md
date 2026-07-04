# SPEC-002 — Board UI

## Goal
React kanban board over SPEC-001: columns per state, drag-drop for HUMAN-allowed
transitions only, ticket drawer with live event feed.

## In scope
- Columns: Ready / In Progress / In QA / Bounced / Escalated / Done.
- Drag-drop (dnd-kit) allowed only for transitions marked HUMAN in the whitelist;
  others render as read-only badges.
- Ticket drawer: spec, acceptance criteria checklist, event feed via WebSocket
  (`/ws/tickets/{id}`), bounce counter, spent/budget bar.
- Approval buttons (approve/reject with note) visible to `approver` role at gates.

## Acceptance criteria
1. Board renders tickets grouped by state from the API (mock-free integration test).
2. Dragging a ticket through an illegal transition snaps back and shows the API reason.
3. New ticket_events appear in an open drawer within 2s (Playwright e2e with WS).
4. Approver sees approval buttons on `awaiting_human_go`/`escalated`; viewer does not.
5. Lighthouse a11y score ≥ 90 on the board page.
