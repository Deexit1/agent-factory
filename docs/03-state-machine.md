# 03 — Ticket State Machine (Phase 2: planning states ACTIVE)

The orchestrator owns transitions. Agents REQUEST; orchestrator VALIDATES and APPLIES.
Illegal requests are logged (`kind=transition`, `payload.rejected=true`) and refused.

## States
`proposed → exec_review → awaiting_human_go → approved → planning → ready →
in_progress → in_review → in_qa → done` plus `bounced`, `escalated`, `blocked`,
`cancelled`.

> Phase 2 change: `approved → planning → ready` is now live (Planner + Delivery
> Manager). `proposed/exec_review/awaiting_human_go` remain Phase 3 — ideas enter at
> `approved` via a human. NEW state `in_review` inserted between dev and QA.

## Transition whitelist
| from | to | trigger | guard |
|---|---|---|---|
| approved | planning | orchestrator | idea has a human-approved budget |
| planning | ready | Planner done | every task has acceptance_criteria + verification hints; TaskSpec[] passes schema + eval sanity checks |
| planning | escalated | Planner outputs questions[] | human answers, then re-plan |
| ready | in_progress | Delivery Manager assigns | budget > 0 and not yet spent, dependencies done, profile + repo capacity available (capability_registry.yaml) |
| in_progress | in_review | dev agent opens PR | diff non-empty |
| in_review | in_qa | Review agent approves OR human overrides | review comments recorded |
| in_review | bounced | Review agent blocks | bounce_count < 3; review notes attached as FailureReport(kind=review) |
| in_qa | done | ALL CI suites pass | merge-queue slot acquired; human deploy gate still applies |
| in_qa | bounced | any CI suite fails | bounce_count < 3; FailureReport attached |
| bounced | in_progress | orchestrator | same agent profile, FailureReport injected |
| in_review / in_qa | escalated | block/fail | bounce_count == 3 |
| in_progress | escalated | system | budget exhausted OR wall-clock timeout |
| escalated | ready | HUMAN | requeues the task for Delivery Manager (re)assignment; distinct from `bounced → in_progress`'s same-agent retry |
| any | blocked / cancelled | HUMAN | |

## Bounce accounting
Review blocks and QA failures share the same `bounce_count` (a ticket gets 3 total
attempts, not 3 per gate).
