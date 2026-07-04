# Changelog — one entry per completed task

Format:
## T-xxx · <title> — <date>
- What changed:
- Files touched:
- Test evidence: (suites run, key results)
- Notes / follow-ups:

## T-001 · Repo scaffold & tooling — 2026-07-04
- What changed: Initialized git. Scaffolded the monorepo layout (`apps/api`, `apps/web`,
  `apps/orchestrator`, `apps/sandbox`, `packages/schemas`). Built a FastAPI stub (`/health`)
  and a Vite+React+TS stub (with Vitest unit test and a Playwright `@smoke` e2e test).
  Added docker-compose (postgres, redis, minio, api, web), `.env.example`, a minimal Alembic
  scaffold (no models yet), a Makefile (`dev`/`test`/`check`/`e2e`/`migrate`), pre-commit
  (ruff, project eslint, gitleaks, basic hygiene hooks), and a GitHub Actions CI workflow
  (`make check` + gitleaks on PRs/push to main).
- Files touched: `.gitignore`, `.env.example`, `.pre-commit-config.yaml`, `Makefile`,
  `docker-compose.yml`, `.github/workflows/ci.yml`, `apps/api/**`, `apps/web/**`,
  `apps/orchestrator/README.md`, `apps/sandbox/README.md`, `packages/schemas/README.md`.
- Test evidence: `pytest` (api, 1 passed), `ruff check` + `mypy --strict` (api, clean),
  `npm run typecheck|lint|test|build` (web, clean), `npm run e2e` (Playwright smoke, 1
  passed), `pre-commit run --all-files` (clean), gitleaks confirmed blocking a planted AWS
  key (then removed), `docker compose up --build` verified live: postgres/redis/minio
  healthy, `GET /health` → 200 `{"status":"ok"}`, web dev server → 200; stack torn down
  after verification.
- Notes / follow-ups: Verified via the underlying commands directly (pytest/ruff/mypy,
  npm scripts, docker compose, gitleaks) rather than the literal `make` binary — this
  Windows dev machine has no admin rights to install GNU Make (choco/winget both blocked
  by permissions). The Makefile itself is POSIX-oriented and untested end-to-end locally;
  CI (Linux runners) will exercise `make check`/`make dev` for real on the first PR — watch
  that run closely. No SQLAlchemy models exist yet, so `migrations/versions/` is empty
  (T-002/T-003 will add the first real revision).

## T-002 · Schemas package — 2026-07-04
- What changed: Built `packages/schemas` (Pydantic v2, Python 3.12): `TaskSpec`,
  `AcceptanceCriterion`, `FailureReport`, `BusinessCase` (+ `MarketEvidence`, `Complexity`),
  each carrying a `schema_version` field (currently `"1.0"`) so future breaking changes bump
  the version instead of mutating a shape in place. Added a `schemas export` console-script
  CLI (argparse) that writes one JSON Schema file per model; defaults to
  `apps/web/src/generated/schemas/` (gitignored, regenerated on demand — nothing in the web
  app consumes it yet, that lands with T-003/T-004).
- Files touched: `packages/schemas/**` (new), `Makefile` (added schemas venv/lint/typecheck/
  test steps), `.pre-commit-config.yaml` (ruff hook now also covers `packages/schemas/`),
  `apps/web/.gitignore` (ignore `/src/generated/`).
- Test evidence: `pytest` (11 passed — round-trip via `model_dump`/`model_dump_json` for all
  four models, validation-error tests asserting exact `loc` field paths including nested
  errors inside `acceptance_criteria[]`/`market_evidence[]`, CLI export tests), `ruff check`
  + `mypy --strict` (clean, using the `pydantic.mypy` plugin), `pre-commit run --all-files`
  (clean). Manually ran both `python -m schemas.cli export` and the installed `schemas`
  console script and inspected the generated JSON Schema output.
- Notes / follow-ups: Not yet installed as a dependency of `apps/api` or `apps/orchestrator`
  — that wiring happens naturally when T-003/T-006 need to validate `TaskSpec`/`FailureReport`
  payloads. `schema_version` is a plain `Literal` field per model rather than a separate
  versioning/migration mechanism; revisit if/when a breaking schema change is needed.

## T-003 · Ticket API & state machine — 2026-07-04
- What changed: Implemented SPEC-001 in `apps/api`. SQLAlchemy 2 models + Alembic migration
  for `tickets`/`ticket_events`/`approvals` (native Postgres enums storing lowercase values
  matching `docs/03-state-machine.md`, plus a `ticket_seq` sequence backing human-readable
  `T-001`/`E-001`/`I-001` ids). A pure `domain/state_machine.py` module enforces the full
  transition whitelist from the docs (including the `blocked`/`cancelled` human-only guard)
  plus concrete guards: `budget_usd > 0` before `in_progress`, non-empty
  `acceptance_criteria` before `ready`, and `bounce_count < 3` before `done` or another
  `bounced`. `services/ticket_service.py` wraps repository + state machine calls in one
  DB transaction per request, writes a `rejected: true` transition event on every illegal
  request (per `docs/03`), and auto-escalates a ticket that hits its 4th bounce attempt.
  Added FastAPI routers (`POST/GET /tickets`, `GET /tickets/{id}`,
  `POST /tickets/{id}/transition`, `POST /tickets/{id}/approve`,
  `GET /tickets/{id}/events`) and a stub `X-Actor`/`X-Actor-Role` header auth dependency
  (SPEC-006 adds real SSO later) enforcing approver/admin-only on the approve gate.
- Files touched: `apps/api/src/api/db/**` (new), `apps/api/src/api/domain/**` (new),
  `apps/api/src/api/repositories/**` (new), `apps/api/src/api/services/**` (new),
  `apps/api/src/api/contracts.py`, `apps/api/src/api/auth.py`,
  `apps/api/src/api/routers/tickets.py`, `apps/api/src/api/main.py`,
  `apps/api/migrations/env.py` (now points `target_metadata` at `Base.metadata`),
  `apps/api/migrations/versions/c7cefaf17891_*.py`, `apps/api/pyproject.toml` (added
  `testcontainers[postgres]`, ignored ruff B008 for FastAPI's `Depends()`/`Query()` idiom),
  `apps/api/tests/domain/**` (new), `apps/api/tests/integration/**` (new). Also fixed a
  real environment bug found along the way: `.env.example`/`docker-compose.yml` had the
  `api` container's `DATABASE_URL` using the docker-network hostname (`postgres:5432`),
  which host-side tools like `make migrate` can't resolve at all — split into a host-side
  `DATABASE_URL` in `.env` (now on port 55432, not 5432, to dodge a locally installed
  Postgres already squatting that port) vs. an internal one built from `POSTGRES_*` vars
  inside `docker-compose.yml`'s `api` service.
- Test evidence: `pytest` (23 passed — 10 pure state-machine unit tests, 5 repository
  integration tests, 7 full-HTTP-API integration tests, 1 health check), all against a
  **real Postgres via Testcontainers** (not mocked). The 7 API tests map 1:1 onto SPEC-001's
  six acceptance criteria (plus a get/list/404 sanity test), including walking a ticket
  through 3 full bounce cycles to hit the 4th-bounce-refusal-and-auto-escalate path and the
  bounce-count-maxed `done` refusal path. `ruff check` + `mypy --strict` clean on `src` (and
  on `tests`, though only `src` gates `make check`). Also manually verified live end-to-end
  against `docker compose up`: created a ticket, transitioned it, listed its events, and
  confirmed an illegal transition returns 409 — all through the real HTTP API, not just
  the test client. `pre-commit run --all-files` clean.
- Notes / follow-ups: `spec`/`acceptance_criteria` are stored as passthrough JSONB, not
  validated against `packages/schemas.TaskSpec`/`BusinessCase` — SPEC-001 doesn't require
  that wiring, and doing it now would need a cross-package install story (Docker build
  context is per-app; `apps/api`'s Dockerfile can't see `packages/schemas` today). Revisit
  when the planner (T-006) actually constructs `TaskSpec` payloads. Guards for
  "sandbox available" (`ready→in_progress`) and "diff non-empty" (`in_progress→in_qa`)
  are not enforced yet — those subsystems don't exist until T-005/T-006. RBAC is a stub
  header, not real auth — SPEC-006 replaces it with OIDC SSO.

## T-004 · Board UI — 2026-07-04
- What changed: Implemented SPEC-002 in `apps/web` against the real `apps/api`. Found and
  closed a real gap first: SPEC-002 needs a live event feed over WebSocket
  (`/ws/tickets/{id}`), which `apps/api` didn't have — added an in-process pub/sub
  broadcaster (`api/ws/broadcaster.py`) plus the WS route, publishing on every transition
  (including rejected ones), and a CORS policy for the Vite dev origin. On the frontend:
  Tailwind v4 (via `@tailwindcss/vite`) + TanStack Query + dnd-kit, a typed API client
  matching `apps/api`'s Pydantic contracts, a localStorage-backed "acting as" actor/role
  context mirroring the backend's stub `X-Actor`/`X-Actor-Role` auth, a 6-column board
  (Ready/In Progress/In QA/Bounced/Escalated/Done) with dnd-kit drag-drop, a ticket drawer
  (spec, acceptance-criteria checklist, bounce counter, budget bar, live WS event feed,
  approve/reject buttons), and a Lighthouse accessibility CLI script.
  Scope interpretation worth flagging: rather than pre-computing which transitions are
  "human-allowed" (docs/03's whitelist trigger column marks almost nothing on the visible
  6 columns as literally HUMAN-triggered), the board lets any card be dragged to any column
  and defers entirely to the API's verdict — legal drags commit, illegal ones snap back
  with the API's rejection reason. This matches AC #2's literal behavior and reuses T-003's
  guards as the single source of truth instead of duplicating them client-side.
- Files touched: `apps/api/src/api/ws/**` (new), `apps/api/src/api/routers/ws_tickets.py`
  (new), `apps/api/src/api/main.py` (lifespan hook binding the broadcaster's event loop,
  CORS), `apps/api/src/api/services/ticket_service.py` (publish after commit),
  `apps/api/tests/integration/test_tickets_ws.py` (new), `apps/api/scripts/e2e-server.sh`
  (new — self-contained postgres+migrate+API bootstrap for e2e/CI), `apps/web/src/api/**`
  (new — types, fetch client, TanStack Query hooks), `apps/web/src/auth/**` (new),
  `apps/web/src/board/**` (new), `apps/web/src/index.css`, `apps/web/vite.config.ts`
  (Tailwind plugin), `apps/web/src/{main,App}.tsx`, `apps/web/e2e/{api.ts,board.spec.ts}`
  (new), `apps/web/playwright.config.ts` (second `webServer` entry for the real API),
  `apps/web/scripts/lighthouse-a11y.mjs` (new), `Makefile` (`a11y` target),
  `.github/workflows/ci.yml` (new `e2e` and `a11y` jobs).
- Test evidence: `pytest` (25 passed, +2 WS tests: connect + receive on both a successful
  and a rejected transition). `npm run typecheck|lint|test|build` clean. Playwright e2e (5
  passed) run twice — once against manually-started servers, once from a fully cold start
  where Playwright's `webServer` config itself brings up docker-compose postgres, runs
  alembic, starts uvicorn, *and* the Vite dev server — covering all four testable SPEC-002
  criteria (AC #4's `awaiting_human_go` half is untestable in Phase 1, which never reaches
  that state; `escalated` is covered). Lighthouse accessibility: **95/100** (threshold 90).
  Also manually drove the full stack in a real browser (screenshots): board renders live
  ticket data, click-to-open drawer, illegal drag snaps back with the reason banner, legal
  drag moves the card and the WS event feed updates live, and approval buttons correctly
  appear only for the approver role on an escalated ticket (driven there via 4 real bounce
  cycles through the actual API).
- Notes / follow-ups: WS pub/sub is in-process (single API replica) per
  docs/06-tech-stack.md's own caveat — move to Redis pub/sub before running multiple API
  replicas. Used Tailwind directly with hand-built accessible primitives instead of running
  shadcn/ui's CLI generator (no interactive scaffolding step available here); functionally
  equivalent for this task's needs. `apps/api/scripts/e2e-server.sh` and the CI `a11y` job
  duplicate some Makefile venv-bootstrap logic — worth consolidating if a third consumer
  shows up. dnd-kit's `PointerSensor` needed an 8px activation distance or it swallowed
  card click events (zero-distance "drags") — worth remembering for any future draggable
  interactive element.
