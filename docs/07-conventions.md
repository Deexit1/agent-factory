# 07 — Conventions

## Repo layout
Monorepo: `apps/api`, `apps/web`, `apps/orchestrator`, `apps/sandbox`, `packages/schemas`.

## Python (api, orchestrator)
- Python 3.12, ruff + mypy strict; 100% type hints on public functions.
- Layering: `routers/ → services/ → repositories/`. No SQL in routers.
- Pydantic models for every request/response and every agent contract.
- Tests: pytest; unit next to code (`test_*.py`); integration in `tests/integration`
  (Testcontainers).

## TypeScript (web)
- Strict tsconfig, eslint, no `any`.
- Components: function components + hooks; server state via TanStack Query only.
- Tests: Vitest + React Testing Library; e2e in `apps/web/e2e` (Playwright).

## Git
- Branch: `task/T-xxx-short-slug`. One task, one branch, one PR.
- Commits: Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- PR description must list the task ID and paste the acceptance-criteria checklist.

## Migrations
- Alembic, one migration per PR max, always reversible. Exception: adding a new
  Postgres enum value and then using that value (e.g. in a backfill `INSERT`/`UPDATE`)
  must be two separate migrations — Postgres won't let a transaction use an enum value
  it just `ADD VALUE`d, and each migration file runs in its own transaction (T-201).

## Tenant scoping (T-201)
- Every `apps/api/src/api/repositories/*.py` function that touches the database must
  reference `org_id` — checked in CI by `scripts/check_tenant_scope_gate.py` (`make
  tenant-scope-gate`, part of `make check`), a real AST walk (not a text/regex scan)
  over every repository function. A genuinely global function (no tenant-scoped row
  involved, e.g. `next_ticket_id`, `user_repository.get_user`) needs an explicit,
  commented entry in that script's small allowlist — not a silent exemption.
- `users` is the one global, non-org-scoped table (a user's identity, not their
  membership) — role and org membership live on `org_members` instead.

## Errors & logging
- Structured JSON logs; every log line carries `ticket_id` where applicable.
- No silent excepts. Orchestrator failures write a `ticket_events` row.
