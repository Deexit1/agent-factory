# 03 — Ticket State Machine

The orchestrator owns transitions. Agents REQUEST; orchestrator VALIDATES and APPLIES.
Illegal requests are logged (`kind=transition`, `payload.rejected=true`) and refused.

## States
`proposed → exec_review → awaiting_human_go → approved → planning → ready →
in_progress → in_qa → done` plus `bounced`, `escalated`, `blocked`, `cancelled`.

## Transition whitelist
| from | to | trigger | guard |
|---|---|---|---|
| proposed | exec_review | orchestrator | exec panel available |
| exec_review | awaiting_human_go | exec panel done | BusinessCase attached |
| awaiting_human_go | approved | HUMAN approves | approval row written |
| awaiting_human_go | cancelled | HUMAN rejects | |
| approved | planning | orchestrator | |
| planning | ready | planner done | every task has acceptance_criteria |
| ready | in_progress | assignment | budget > 0, sandbox available |
| in_progress | in_qa | dev agent opens PR | diff non-empty |
| in_qa | done | ALL CI suites pass | human deploy gate still applies |
| in_qa | bounced | any CI suite fails | bounce_count < 3; FailureReport attached |
| bounced | in_progress | orchestrator | same agent, FailureReport injected |
| in_qa | escalated | CI fails | bounce_count == 3 |
| in_progress | escalated | system | budget exhausted OR wall-clock timeout |
| any | blocked / cancelled | HUMAN | |

## Phase 1 note
In Phase 1 there is no exec/planning layer: tickets are created directly in `ready`
by humans, with hand-written acceptance criteria. States before `ready` activate in
Phases 2–3 without schema changes.
