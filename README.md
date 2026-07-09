# Autonomous Agent Factory

A Jira-style delivery platform where AI agents run the full ticket lifecycle —
plan → build → test → ship — under human supervision at hard checkpoints. The
end state is a multi-tenant SaaS: a user signs up, brings an idea and their own
LLM API keys (BYOK), connects a GitHub repo, and the factory plans, builds,
tests and delivers the project, with the user approving at a few high-leverage
checkpoints. See [docs/00-vision.md](docs/00-vision.md).

## Status

Phase 1 (core loop), Phase 2 (management layer), and Phase 2.5 (SaaS
foundation) are done. T-207 (closed beta) is next. See
[tasks/BACKLOG.md](tasks/BACKLOG.md) for the full task-by-task history and
[tasks/CHANGELOG.md](tasks/CHANGELOG.md) for what shipped when.

| Track | Scope | Status |
|---|---|---|
| Phase 1 (T-001–T-009) | Board, one dev agent, full QA gate, bounce loop | done |
| Phase 2 (T-101–T-110) | Planner + Delivery Manager, specialised dev agents, review agent, eval harness, merge queue, parallelism | done (T-110 blocked on live Anthropic credit) |
| Phase 2.5 (T-201–T-206) | Multi-tenancy, BYOK + provider router, GitHub connect, VM-grade sandbox isolation, billing/metering, onboarding + abuse controls | done |
| Phase 2.5 (T-207) | Closed beta | ready |
| Phase 3 | Executive layer (CEO/CFO/CPO appraisal agents), public beta | not started |

A number of live-infrastructure gaps are disclosed on purpose (no live OIDC
IdP, GitHub App, Razorpay account, or Anthropic credit in this development
environment) — every one of them is called out explicitly in
[docs/06-tech-stack.md](docs/06-tech-stack.md)'s "Implementation status
notes" and in the relevant `tasks/BACKLOG.md` entry, with the exact test
strategy used to prove the code path anyway (HTTP-boundary fault injection,
respx, real local fixtures). Nothing here is claimed live that isn't.

## Architecture

Five layers, clean contracts, higher layers never bypass lower ones (see
[docs/01-architecture.md](docs/01-architecture.md)):

```
┌─────────────────────────────────────────────────────────┐
│ 1. EXPERIENCE   board UI · ticket detail + live agent   │
│                 transcript · approval gates · dashboards│
├─────────────────────────────────────────────────────────┤
│ 2. ORCHESTRATION  state machine per ticket · routing ·  │
│                 budgets · retries · escalation (CODE)   │
├─────────────────────────────────────────────────────────┤
│ 3. AGENT RUNTIME  role agents (exec/planner/dev/QA),    │
│                 each = prompt + tools + model + evals   │
├─────────────────────────────────────────────────────────┤
│ 4. EXECUTION SANDBOX  org-scoped container per task ·   │
│                 pre-warmed pool · no-co-location         │
│                 scheduler · git worktree · test runners  │
│                 · per-org egress allow-list (T-204)      │
├─────────────────────────────────────────────────────────┤
│ 5. DATA & AUDIT  tickets · event log · cost ledger ·    │
│                 artifacts · traces (append-only)        │
└─────────────────────────────────────────────────────────┘
```

**Two SaaS-readiness rules apply to all code, everywhere, from Phase 2.5 on:**
1. Every domain table carries `org_id`; every repository query is tenant-scoped
   (enforced in CI by `scripts/check_tenant_scope_gate.py`).
2. Every LLM call goes through `packages/llm_router` — never import a provider
   SDK anywhere else. Provider keys are secrets: never in the DB, logs, events,
   traces, or anything visible inside a sandbox.

**Non-negotiable human checkpoints:** go/no-go on every idea, budget approval
before a plan enters the dev queue, escalation after 3 failed QA bounces, and
deploy sign-off — nothing reaches production unreviewed.

## Repo layout

```
apps/
  api/           FastAPI backend (Python 3.12) — tickets, orgs, auth, billing,
                 onboarding/abuse, admin routes. Layered routers/ → services/ →
                 repositories/, Alembic migrations, pytest.
  web/           React 18 + TypeScript + Vite frontend — board, planning
                 review, admin pages, onboarding wizard. Vitest + Playwright.
  orchestrator/  LangGraph state machine driving the per-ticket pipeline
                 (exec panel → planner → dev loop → QA → merge queue), the
                 golden-set eval runner, and end-to-end integration tests.
  sandbox/       Pluggable sandbox runtime (rootless Docker default), egress
                 proxy, host pool scheduler, escape-test suite.
packages/
  schemas/       Shared Pydantic contracts for agent/tool payloads.
  llm_router/    Sole owner of provider SDKs — role+complexity+org routing,
                 fallover/retries across providers.
docs/            Architecture source of truth. Code follows docs, never the
                 reverse — see docs/07-conventions.md for the reading order.
specs/           Feature specs — the "what to build", one file per feature.
tasks/           The board: BACKLOG.md (tasks + states) and CHANGELOG.md.
prompts/         Versioned system prompts for the platform's own runtime
                 agents (planner, dev, QA, exec, review, delivery-manager).
evals/           Golden-set eval harness cases + thresholds (make eval).
scripts/         CI static gates (tenant-scope, llm-router, github-app,
                 razorpay import-boundary checks).
```

## Tech stack

See [docs/06-tech-stack.md](docs/06-tech-stack.md) (locked; changes require a
doc PR + human approval) for the full table and per-row implementation-status
notes. Summary: React 18 + TypeScript + Vite + Tailwind on the frontend;
FastAPI + Pydantic v2 + SQLAlchemy 2/Alembic on Python 3.12 for the API;
LangGraph for orchestration; Postgres 16 + Redis 7 + MinIO (S3-compatible) for
storage; Vault for BYOK provider-key secrets; rootless Docker sandboxes with a
per-org Squid egress allow-list; GitHub App for repo delivery; Razorpay for
billing; OIDC SSO for auth; Anthropic API behind `packages/llm_router`.

## Local setup

### Prerequisites

- Python 3.12
- Node.js 20+
- Docker (for Postgres/Redis/MinIO/Vault via `docker compose`, and for
  sandbox/escape-test suites)
- `gh` CLI, authenticated (dev-agent PR creation, pilot runner)

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd agent-factory
cp .env.example .env
```

`.env.example` documents every variable inline — what it's for, safe local
defaults, and which features are 501/disabled until it's set (OIDC login,
GitHub App, Razorpay, Anthropic). For local dev you can leave most integration
variables blank; `AUTH_DEV_MODE=true` unlocks `POST /auth/dev-login` so you
don't need a real OIDC identity provider to log in. **Never commit `.env`.**

### 2. Start infrastructure

```bash
docker compose up -d postgres redis minio vault
```

This brings up Postgres 16, Redis 7, MinIO (S3-compatible artifact storage),
and Vault in dev mode (in-memory, unsealed, root-token auth — not a
production topology). Add `api web` to run the full stack in containers
instead of locally (`make dev` does exactly this), or keep infra in Docker and
run `api`/`web` locally for faster iteration (below).

### 3. Set up each app

```bash
# API
cd apps/api
python3 -m venv .venv
.venv/bin/pip install -e "../../packages/schemas" -e ".[dev]"
.venv/bin/alembic upgrade head        # or: make migrate
.venv/bin/uvicorn api.main:app --reload --port 8000

# Web (separate shell)
cd apps/web
npm install
npm run dev                            # http://localhost:5173

# Orchestrator (separate shell, for running the agent pipeline / evals)
cd apps/orchestrator
python3 -m venv .venv
.venv/bin/pip install -e "../../packages/schemas" -e "../../packages/llm_router" -e "../../apps/sandbox" -e ".[dev]"
```

Or let the `Makefile` do the venv/npm-install bookkeeping for you — every
`make` target below creates missing venvs and runs `npm install` as needed via
file-timestamp stamps, so you rarely need to do this by hand.

### 4. Common commands

```bash
make dev              # full stack via docker compose
make test              # unit tests (pytest, no Docker) + vitest
make test-integration   # Docker-backed integration suites (Testcontainers)
make check              # lint + typecheck + test + all static gates — the CI gate
make e2e                 # Playwright end-to-end suite (apps/web)
make a11y                 # Lighthouse accessibility audit (needs `npm run dev` running)
make migrate                # apply Alembic migrations
make eval                    # golden-set eval harness — required if prompts/** or LLM routing changed
make escape-test               # sandbox escape probes (host fs, docker socket, cross-org network)
```

`make check` is exactly what CI runs on every PR — lint, typecheck, unit +
integration tests, and four static gates (`llm-router-gate`,
`tenant-scope-gate`, `github-app-gate`, `razorpay-gate`), each enforcing one
of this repo's hard architectural rules by walking the AST, not grepping.

### 5. Log in locally

With `AUTH_DEV_MODE=true`, `POST /auth/dev-login` (used by the web login page
in dev) mints a session for any email without a real OIDC round-trip. The
first login auto-joins a seeded default org as `viewer`; use the in-app
"Get started" wizard to create your own org, accept the ToS, add a BYOK
provider key, and connect a repo.

## The bootstrap trick

This markdown structure is a manual version of the factory itself:
`tasks/BACKLOG.md` is the board, a human is the orchestrator + approval gate,
an AI coding assistant is the dev agent, and the test suite is the QA gate.
We use the process to build the platform that automates the process — see
[CLAUDE.md](CLAUDE.md) for the exact working agreement this repo runs under.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation map

Read in this order (per [docs/07-conventions.md](docs/07-conventions.md)):

1. [docs/00-vision.md](docs/00-vision.md), [docs/01-architecture.md](docs/01-architecture.md)
2. [docs/02-data-model.md](docs/02-data-model.md), [docs/03-state-machine.md](docs/03-state-machine.md)
3. [docs/04-agent-specs.md](docs/04-agent-specs.md), [docs/08-evals.md](docs/08-evals.md)
4. [docs/06-tech-stack.md](docs/06-tech-stack.md) (locked; Phase-2 activation
   triggers listed at the bottom)
5. [docs/05-security.md](docs/05-security.md), [docs/07-conventions.md](docs/07-conventions.md)
6. [docs/09-saas-model.md](docs/09-saas-model.md) — tenancy, BYOK, repo
   delivery, billing, isolation & abuse model
7. The `specs/SPEC-xxx.md` your task references
