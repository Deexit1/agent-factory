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
