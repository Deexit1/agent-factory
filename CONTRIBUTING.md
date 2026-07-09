# Contributing

This repo runs on a ticket-board workflow, not ad-hoc PRs — the same process
the platform itself automates (see the "bootstrap trick" in
[README.md](README.md)). Read this file before opening a PR; it's shorter
than it looks because most of the substance lives in `docs/` and
[CLAUDE.md](CLAUDE.md).

## Before you write any code

1. **Read the docs, in order.** [CLAUDE.md](CLAUDE.md) first, then the
   reading order in [docs/07-conventions.md](docs/07-conventions.md)
   (`docs/00` and `01` for vision/architecture, `02`/`03` for data model and
   state machine, `04`/`08` for agent specs and evals, `06` for the locked
   tech stack, `05`/`07` for security and conventions, `09` for the SaaS
   model). Docs are the source of truth; code follows docs, not the other way
   around.
2. **Pick a task from [tasks/BACKLOG.md](tasks/BACKLOG.md).** It's the board:
   Phase 1 is done at the top, active/queued Phase-2 and Phase-2.5 work below
   it. Work the task you were pointed at — don't invent scope, and don't pick
   up a task whose spec you haven't read. A `specs/SPEC-xxx.md` exists for
   most tasks; read it alongside the backlog entry.
3. **One task = one branch = one PR.** Branch name: `task/T-xxx-short-slug`.
   Don't bundle unrelated tasks into one branch, and don't split one task
   across multiple PRs unless the task itself is explicitly staged that way.

## The two SaaS-readiness rules (apply to everything, no exceptions)

1. Every domain table carries `org_id`; every repository-layer query is
   tenant-scoped. CI enforces this for real — `scripts/check_tenant_scope_gate.py`
   is an AST walk (not a regex) over every function in
   `apps/api/src/api/repositories/*.py`. A genuinely global, non-tenant-scoped
   function needs an explicit, commented allowlist entry in that script, not a
   silent exemption.
2. Every LLM call goes through `packages/llm_router` — never import a
   provider SDK (Anthropic, OpenAI, etc.) anywhere else. `scripts/check_llm_router_gate.py`
   enforces this in CI. Provider keys are secrets: never in the database,
   logs, events, traces, or anything visible inside a sandbox.

Two more import-boundary gates exist for the same reason, scoped to their own
vendor: `scripts/check_github_app_gate.py` (only `github_app_client.py` may
reference `api.github.com`) and `scripts/check_razorpay_gate.py` (only
`razorpay_client.py` may reference `api.razorpay.com`). If your task adds a
new external vendor integration, add the matching gate in the same PR.

## Code conventions

Full detail in [docs/07-conventions.md](docs/07-conventions.md); the load-bearing points:

- **Python** (`apps/api`, `apps/orchestrator`, `apps/sandbox`,
  `packages/*`): Python 3.12, ruff + mypy strict, 100% type hints on public
  functions. Layering is `routers/ → services/ → repositories/` — no SQL in
  routers. Every request/response and agent contract is a Pydantic model.
  Unit tests live next to the code (`test_*.py`); integration tests
  (Testcontainers-backed, real Postgres) live in `tests/integration/`.
- **TypeScript** (`apps/web`): strict `tsconfig`, eslint, no `any`. Function
  components + hooks; server state goes through TanStack Query only, never ad
  hoc `useEffect` fetches. Unit tests: Vitest + React Testing Library. E2E:
  Playwright, in `apps/web/e2e`.
- **Migrations**: Alembic, one migration per PR (combine multiple new tables
  from one task into a single migration file, matching this repo's existing
  precedent), always reversible — verify with `upgrade head` →
  `downgrade -1` → `upgrade head` against a real database before you open the
  PR. Exception: adding a new Postgres enum value and then using that value in
  the same PR must be two separate migrations (each migration file runs in
  its own transaction; Postgres won't let you use a value you just added in
  the same one).
- **Commits**: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`,
  `chore:`), scoped to the task, e.g. `feat(T-206): onboarding wizard, intake
  screening, ToS, strikes, funnel`.
- **Errors & logging**: structured JSON logs, every line carries `ticket_id`
  where applicable. No silent `except`. Orchestrator failures write a
  `ticket_events` row — don't just log and swallow.
- **Prompts are versioned artifacts.** Anything under `prompts/` gets a
  version-header bump on every change, never a silent edit. CI runs the
  golden-set eval suite (`make eval`) on any `prompts/**` diff, and a red
  eval blocks merge exactly like a red unit test — the same bar as
  `evals/thresholds.yaml`, which additionally requires code-owner review
  (`CODEOWNERS`) to lower.

## Definition of done

Every task, no exceptions:

- [ ] Each acceptance criterion in the spec maps to at least one passing,
      real test — not a mock standing in for the thing you're actually
      supposed to prove.
- [ ] `make check` is green (lint + typecheck + unit + integration + all
      four static gates).
- [ ] `make eval` is green if you touched anything under `prompts/` or LLM
      routing.
- [ ] Docs are updated in the *same PR* if you changed schema, the state
      machine, or the tech stack — flag the change explicitly in the PR
      description if it touches a locked doc (`docs/06-tech-stack.md`).
- [ ] `tasks/BACKLOG.md` is updated (task state + evidence per acceptance
      criterion) and `tasks/CHANGELOG.md` has a new entry.
- [ ] For `apps/web` changes: actually run the feature in a browser (or
      Playwright against a real running stack) before calling it done. Type
      checks and unit tests verify code correctness, not feature
      correctness.

If a test fails, fix it and re-run — don't skip or weaken the test to make
CI pass. After 3 failed attempts at the same failure, stop and escalate with
a summary of what you tried instead of forcing a workaround.

## Disclosing gaps and limitations

This repo has a strong norm, visible throughout `docs/06-tech-stack.md` and
`tasks/BACKLOG.md`: when something can't be verified against real
infrastructure (no live OIDC IdP, GitHub App, Razorpay account, or Anthropic
credit in this environment), say so explicitly, name the alternative
verification strategy you used (HTTP-boundary fault injection, a real local
fixture standing in for the live thing, etc.), and never claim something is
live that isn't. Silent scope-narrowing is treated as a bug. If your task
runs into an architectural gap that isn't yours to close, disclose it in the
backlog entry rather than quietly working around it or leaving it unstated.

## Opening the PR

- PR description lists the task ID and pastes the acceptance-criteria
  checklist from the backlog entry, checked off against real evidence (test
  names, not just "done").
- Never bypass the merge queue for `agent/*` PRs (SPEC-106) — tickets run in
  parallel and the queue handles repo conflicts; force-merging around it
  defeats the mechanism this repo is dogfooding.
- No secrets in the repo, ever — not in code, not in test fixtures, not in a
  committed `.env`. `.env.example` documents every variable; real values only
  ever go in your local `.env` (gitignored) or Vault.
- Tests ship in the same commit as the code they cover, not as a follow-up.

## Getting a second opinion

For a deeper, multi-agent review of a branch or PR before merge, see
`/code-review ultra` (aliased as `/ultrareview`) if you're working with
Claude Code — it's user-triggered and reviews the actual diff, not a
substitute for the checklist above.
