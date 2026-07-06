# 00 — Vision

## One-liner
A platform where every ticket is executed by AI agents: an executive layer appraises
whether an idea can make money, a management layer plans and splits work, developer
agents build, and a QA layer refuses to let bad code through.

## End state: a multi-tenant SaaS
The finished product is a SaaS where **any user signs up, brings an idea and their own
LLM API keys (BYOK), connects or receives a GitHub repo, and the factory plans, builds,
tests and delivers the project automatically** — with the user sitting at the human
checkpoints. The internal single-tenant factory we are building first is the engine of
that product, dogfooded on our own backlog. See `docs/09-saas-model.md` for the tenancy,
key-handling, repo and billing model.

Two SaaS-readiness rules apply from NOW (not later):
1. Every domain table carries `org_id`; all queries are tenant-scoped.
2. Every LLM call goes through the provider router module — no direct provider clients.

## Why
Tickets today wait for humans. In the factory, a ticket is an execution contract picked
up by a specialised agent within seconds. Humans move from executing every task to
supervising at a few high-leverage checkpoints.

## Non-negotiable human checkpoints
1. Go / no-go on every idea the exec agents appraise
2. Budget approval before a plan enters the dev queue
3. Escalation after 3 failed QA bounces on a ticket
4. Deploy sign-off — nothing reaches production unreviewed

## Success metrics (pilot phases)
- First-pass QA rate ≥ 50% (tickets closed with ≤ 1 bounce)
- Median cost per closed ticket below one loaded engineer-hour
- Zero security incidents (egress violations, credential/key leaks, unauthorized pushes)
- Zero escaped defects within 2 weeks of ticket close

## Phasing
- **Phase 1 (done):** the core loop — board, one dev agent, full QA gate, bounce loop.
- **Phase 2 (active):** management layer — planner + delivery manager, specialised dev
  agents, review agent, eval harness, parallelism.
- **Phase 2.5 (SaaS foundation):** multi-tenancy, BYOK + provider router, GitHub
  connect, hardened tenant isolation, billing/metering, onboarding + abuse controls.
- **Phase 3:** executive layer — CEO/CFO/CPO appraisal agents producing business cases
  for the user's go/no-go — and public beta.
