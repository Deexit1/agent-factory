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
| in_qa | done | merge-queue processor merges the PR | CI-green alone only enqueues a `merge_queue_entries` row (T-107); `done` requires a real `merged` entry, written after a genuine rebase-and-retest against the target branch — human deploy gate still applies |
| in_qa | bounced | any CI suite fails, OR a queue rebase conflicts | bounce_count < 3; FailureReport attached (`kind=conflict` for a rebase conflict, shares the same bounce_count) |
| bounced | in_progress | orchestrator | same agent profile, FailureReport injected |
| bounced | in_qa | HUMAN | overrides a review-block bounce straight into QA; records an `Approval(gate=review)` row |
| in_review / in_qa | escalated | block/fail | bounce_count == 3 |
| in_progress | escalated | system | budget exhausted OR wall-clock timeout |
| escalated | ready | HUMAN | requeues the task for Delivery Manager (re)assignment; distinct from `bounced → in_progress`'s same-agent retry |
| any | cancelled | HUMAN | |
| any | blocked | HUMAN or `system:github` or `system:billing` | T-203 (SPEC-203 AC4): the GitHub webhook handler force-blocks in-flight tickets when their repo's App installation is uninstalled. T-205 (SPEC-205 AC4) adds the second, otherwise-identical exception: an org whose Razorpay payment grace period expires gets force-blocked by `billing_service.pause_org_for_nonpayment`. Both are exact-string allowlist entries (not a `startswith("system:")` blanket rule) so this doesn't silently widen to any future system actor. Synchronous, same-request — no polling, satisfies the 60s bound by construction. T-206 (SPEC-206 AC5) adds a THIRD force-block trigger, `abuse_service.strike_org` — but reuses the existing `human:` actor path below rather than a new system-actor entry: a strike is staff-*initiated* (a human clicking "strike" in the admin UI), so `is_human_actor` already covers it. |
| blocked | ready | HUMAN | T-206 (SPEC-206 AC5): the first-ever whitelisted exit from `blocked` — closes the gap this table used to describe as permanent. `abuse_service.resolve_appeal(decision="reinstate")` reactivates every currently-`BLOCKED` ticket for an org whose staff-decided appeal succeeded. Human-only by construction (`state_machine._check_guard`'s new `BLOCKED → READY` branch) — deliberately NOT extended to any system actor, since an abuse-strike appeal is always a platform-staff judgment call, never automated. Known, disclosed limitation: this reactivates every `BLOCKED` ticket for the org, not just ones blocked by *this* strike — no `blocked_reason` column exists yet to distinguish an abuse-block from a simultaneous billing-block (docs/09-saas-model.md). |

## Bounce accounting
Review blocks and QA failures share the same `bounce_count` (a ticket gets 3 total
attempts, not 3 per gate).
