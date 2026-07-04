# 00 — Vision

## One-liner
A Jira-like platform where every ticket is executed by AI agents: an executive layer
appraises whether an idea can make money, a management layer plans and splits work,
developer agents build, and a QA layer refuses to let bad code through.

## Why
Tickets today wait for humans. In the factory, a ticket is an execution contract picked
up by a specialised agent within seconds. Humans move from executing every task to
supervising at a few high-leverage checkpoints.

## Non-negotiable human checkpoints
1. Go / no-go on every idea the exec agents appraise
2. Budget approval before a plan enters the dev queue
3. Escalation after 3 failed QA bounces on a ticket
4. Deploy sign-off — nothing reaches production unreviewed

## Success metrics (Phase 1 pilot)
- First-pass QA rate ≥ 50% (tickets closed with ≤ 1 bounce)
- Median cost per closed ticket below one loaded engineer-hour
- Zero security incidents (egress violations, credential leaks, unauthorized pushes)
- Zero escaped defects within 2 weeks of ticket close

## Phasing
- **Phase 1 (weeks 1–12):** the core loop — board, one dev agent, full QA gate, bounce loop.
  Humans write the tasks.
- **Phase 2 (months 4–6):** management layer — planner + delivery manager agents,
  specialised dev agents, review agent, cost ledger everywhere.
- **Phase 3 (months 7–9):** executive layer — CEO/CFO/CPO appraisal agents producing
  business cases for the human go/no-go.
