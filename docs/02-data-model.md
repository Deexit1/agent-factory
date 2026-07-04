# 02 — Data Model (Postgres 16)

All timestamps UTC. All agent payloads JSONB validated against `packages/schemas`.

## tickets
| column | type | notes |
|---|---|---|
| id | text PK | `T-001` style, human-readable |
| type | enum | `idea` \| `epic` \| `task` |
| parent_id | text FK→tickets | ideas parent epics parent tasks |
| state | enum | see 03-state-machine.md |
| title | text | |
| spec | jsonb | TaskSpec for tasks, BusinessCase for ideas |
| acceptance_criteria | jsonb | array of machine-checkable criteria |
| assignee_agent | text | agent role id, nullable |
| budget_usd / spent_usd | numeric | hard cap / running total |
| bounce_count | int | max 3 then `escalated` |
| created_by | text | user id or agent id |

## ticket_events (append-only, partitioned monthly)
| column | type | notes |
|---|---|---|
| id | bigserial PK | |
| ticket_id | text FK | |
| ts | timestamptz | |
| actor | text | `agent:dev-1` \| `human:uid` \| `system` |
| kind | enum | `message` \| `tool_call` \| `test_result` \| `transition` \| `cost` |
| payload | jsonb | |

## agent_runs
one row per agent invocation: `id, ticket_id, agent_role, model, started_at, ended_at,
status, tokens_in, tokens_out, cost_usd, trace_id` (links to Langfuse).

## cost_ledger
`id, ticket_id, agent_run_id, provider, model, usd, ts` — source of truth for $/ticket.

## approvals
`id, ticket_id, gate (idea|budget|deploy|escalation), decided_by, decision, note, ts`.

## artifacts
`id, ticket_id, kind (diff|ci_log|trace|coverage), s3_key, ts`.

## Rules
- No updates or deletes on `ticket_events` and `cost_ledger` — append-only, enforced by
  DB grants.
- Every state change writes a `transition` event in the same DB transaction.
