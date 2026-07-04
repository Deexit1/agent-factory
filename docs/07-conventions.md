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
- Alembic, one migration per PR max, always reversible.

## Errors & logging
- Structured JSON logs; every log line carries `ticket_id` where applicable.
- No silent excepts. Orchestrator failures write a `ticket_events` row.
