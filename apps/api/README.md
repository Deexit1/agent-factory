# apps/api

FastAPI backend (Python 3.12). Owns the ticket state machine, agent-run/cost ledger,
auth, and the CI-result webhook — the layer-5 system of record described in
[docs/01-architecture.md](../../docs/01-architecture.md). See also
[docs/06-tech-stack.md](../../docs/06-tech-stack.md) and
[docs/07-conventions.md](../../docs/07-conventions.md).

```bash
pip install -e ../../packages/schemas
pip install -e ".[dev]"
alembic upgrade head
pytest tests --ignore=tests/integration   # unit tests, no Docker
pytest tests/integration                  # real Postgres via testcontainers
```

## Layout

- `src/api/main.py` — FastAPI app assembly: CORS (dev-only, allows the Vite origin),
  `SessionMiddleware` (holds Authlib's transient OAuth state, not our own session token),
  and router registration.
- `src/api/auth.py` — `get_actor_context` dependency: verifies the bearer token on every
  route except `/health`, `/webhooks/*` and `/auth/*`.
- `src/api/contracts.py` — Pydantic request/response models for every router.
- `src/api/domain/state_machine.py` — the ticket state machine (`docs/03-state-machine.md`)
  as pure functions; routers/services never encode transitions themselves.
- `src/api/db/models.py` — SQLAlchemy models (`Ticket`, `TicketEvent`, `Approval`,
  `AgentRun`, `CostLedgerEntry`, `User`, `EscapedDefectReport`) and their enums.
- `src/api/db/session.py` — engine/session factory, reads `DATABASE_URL`.
- `src/api/repositories/` — SQLAlchemy query layer, one module per aggregate.
- `src/api/services/` — business logic (ticket transitions, agent-run/cost accounting,
  dashboard metrics, CI-webhook handling, failure distillation); routers stay thin.
- `src/api/routers/` — HTTP surface, one module per resource (see below).
- `src/api/ws/broadcaster.py` — in-process pub/sub fanning ticket events out to
  `/ws/tickets/{ticket_id}` subscribers.
- `migrations/` — Alembic migrations; `env.py` reads `DATABASE_URL` and targets
  `Base.metadata` from `db/models.py` directly (no separate metadata duplication).
- `tests/integration/conftest.py` — spins up a real `PostgresContainer`, runs
  `alembic upgrade head` against it once per session, and truncates tables between tests.
- `scripts/e2e-server.sh` — boots postgres + a migrated API for Playwright's mock-free
  e2e suite (`make e2e`).

## Routers

| Router | Prefix | Auth | Notes |
|---|---|---|---|
| `health` | `/health` | none | liveness check |
| `auth` | `/auth` | mixed | `/login` + `/callback` (OIDC), `/dev-login`, `/me` |
| `tickets` | `/tickets` | bearer | create/list/get, `transition`, `approve`, `return-to-dev`, events |
| `agent_runs` | `/tickets/{id}/agent-runs`, `/cost-ledger`, `/cost-summary` | bearer | agent-run lifecycle + cost accounting |
| `webhooks` | `/webhooks` | HMAC signature | `POST /webhooks/ci-result` |
| `dashboard` | `/dashboard` | bearer | pilot metrics, CSV export, escaped-defect reports |
| `ws_tickets` | `/ws/tickets/{ticket_id}` | none (Phase 1) | live ticket-event stream |

`tickets.approve` and `tickets.return-to-dev` additionally require the actor's role to be
`approver` or `admin` (403 otherwise) — every other authenticated route is open to any
role.

## Auth model (SPEC-006)

Every route depends on `get_actor_context` (`src/api/auth.py`) except `/health`,
`/webhooks/*`, and `/auth/*`. It expects `Authorization: Bearer <token>` and accepts
exactly two kinds of token:

- **Service token** — the shared secret in `AGENT_FACTORY_SERVICE_TOKEN`, compared with
  `hmac.compare_digest`. Used by `apps/orchestrator` and `apps/sandbox` to call the API as
  a trusted machine principal (`actor="system"`, `role="admin"`). There is no per-service
  identity in Phase 1 — anything holding the token is fully trusted.
- **Session JWT** — a short-lived (12h) HS256 token signed with `SESSION_JWT_SECRET`,
  minted by either:
  - `GET /auth/login` → `/auth/callback` — the real OIDC authorization-code flow via
    Authlib. Returns 501 until `OIDC_ISSUER_URL`, `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET`
    are all set. On success, `user_service.get_or_create_user` upserts a `User` row
    (`role` defaults to `viewer`) and redirects to `WEB_LOGIN_SUCCESS_URL#token=<jwt>`.
  - `POST /auth/dev-login` — mints a session token for an arbitrary email/role without a
    real IdP round-trip. Only enabled when `AUTH_DEV_MODE=true`; 404s otherwise. Local/CI
    only — never set that flag in a deployed environment.

  A decoded session token carries `sub` (email) and `role`; `get_actor_context` turns it
  into `ActorContext(actor=f"human:{email}", role=role)`.

The CI webhook (`POST /webhooks/ci-result`) uses neither: it's authenticated by an
HMAC-SHA256 signature over the raw body (`X-Hub-Signature-256`, GitHub convention) checked
against `CI_WEBHOOK_SECRET`. An unset secret disables verification (Phase 1 local/dev
convenience).

See `.env.example` for every auth-related variable (`SESSION_JWT_SECRET`,
`AGENT_FACTORY_SERVICE_TOKEN`, `OIDC_*`, `AUTH_DEV_MODE`, `ADMIN_EMAILS`,
`CI_WEBHOOK_SECRET`).

## Migrations

Alembic targets `Base.metadata` directly from `src/api/db/models.py` — there's no
separate schema to keep in sync. `DATABASE_URL` is read at runtime by `migrations/env.py`;
`alembic.ini` itself carries no connection string.

```bash
alembic upgrade head                       # apply, from apps/api/
alembic revision --autogenerate -m "..."   # generate a new migration
```

From the repo root, `make migrate` does the same against the `docker compose` postgres
using `DATABASE_URL` from `.env`.

## Tests

- `tests/` (outside `tests/integration/`) — unit tests for the state machine and failure
  distiller; no Docker required. Run via `make test-unit` or
  `pytest tests --ignore=tests/integration`.
- `tests/integration/` — full-stack tests against a real, migrated Postgres
  (`testcontainers.postgres.PostgresContainer`, see `conftest.py`) and the real FastAPI
  app via `TestClient`. Covers tickets, agent-runs, auth (OIDC callback, dev-login, service
  token), the CI webhook, the dashboard, and the tickets websocket. Run via
  `make test-integration` or `pytest tests/integration` (requires Docker).
- From the repo root, `make check` runs lint + typecheck + both test tiers across every
  package; that's the gate a task must pass to be done.
