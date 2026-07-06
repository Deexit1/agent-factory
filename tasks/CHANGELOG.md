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

## T-005 · Sandbox runner — 2026-07-04
- What changed: Implemented SPEC-003 in `apps/sandbox`, with two deliberate substitutions
  for real infra this environment/Phase 1 doesn't have (both confirmed with the human
  first): standard Docker isolation instead of gVisor (`--read-only` rootfs, tmpfs
  workspace, CPU/RAM limits, `--security-opt no-new-privileges`, no docker-socket mount,
  one `--internal` docker network per ticket so sandboxes can't reach each other), and a
  local stub `credential_broker.py` instead of real Vault + a GitHub App (same issue/revoke
  shape, mints a random token for a local git remote — swap the module, not its callers,
  when real Vault/GitHub App wiring lands). Also added a small but real extension to
  SPEC-001's API: `POST /tickets/{id}/events`, since SPEC-003's AC #5 needs an external
  writer (the egress-log forwarder) to append `ticket_events`, and no such endpoint existed
  (only auto-written transition events did). A Squid container gives default-deny egress
  (allow-list: PyPI, npm, GitHub, Anthropic API) on a network topology where the sandbox
  only has the internal leg and the proxy bridges to the internet; every request (allowed
  or denied) is tailed from Squid's access log and forwarded as a `tool_call` event. A
  pre-push hook (reading `AGENT_FACTORY_TICKET_ID`) rejects any push except to
  `refs/heads/agent/<ticket_id>`, per SPEC-003's own Phase-1 note that this is simulated
  client-side rather than via real GitHub branch protection.
- Files touched: `apps/api/src/api/contracts.py` (`CreateEventRequest`, rejects `kind:
  transition`), `apps/api/src/api/services/ticket_service.py` (`record_event`),
  `apps/api/src/api/routers/tickets.py` (new endpoint),
  `apps/api/tests/integration/test_ticket_events_api.py` (new); `apps/sandbox/**` (new:
  `images/Dockerfile`, `hooks/pre-push`, `src/sandbox/{cli,config,docker_runtime,
  egress_proxy,credential_broker,worktree,egress_forwarder,events_client}.py`,
  `tests/unit/**`, `tests/integration/**`); `.gitattributes` (new — forces LF checkout
  repo-wide); `Makefile` (`SANDBOX_DIR` wired into test/lint/typecheck, so `make check`
  now also covers apps/sandbox); `.pre-commit-config.yaml` (ruff now covers
  `apps/sandbox/`).
- Test evidence: 12 unit tests (squid config rendering, credential broker issue/get/revoke,
  egress-log line parsing) + 7 integration tests against **real Docker** (19 total,
  `make test` picks them up automatically now). The integration suite bootstraps its own
  dependencies — builds the sandbox image, pulls `ubuntu/squid`, and (for the one test that
  needs it) spins up a real throwaway Postgres + a real migrated `apps/api` via its own
  venv — and covers all five SPEC-003 acceptance criteria directly: blocked-domain curl
  fails / `pip install requests` succeeds through the proxy; push to `main` rejected, push
  to `agent/<ticket>` succeeds; no docker socket, no docker CLI, two concurrent sandboxes
  can't resolve or reach each other by name or IP; `sandbox down` leaves no container,
  network, or credential (and no worktree directory) behind; both an allowed and a denied
  egress attempt show up as real `ticket_events` fetched back from a real running API.
  Also drove the entire lifecycle by hand first (before automating it) to find and fix
  every bug below. `apps/api` full suite still green (28 passed) after the new endpoint.
  `ruff check` + `mypy --strict` clean on all three Python packages. `pre-commit run
  --all-files` clean.
- Notes / follow-ups: building this surfaced (and fixed) four real, non-obvious bugs, all
  now covered by tests or config rather than just "worked on my machine": (1) a git
  worktree's `.git` file references the main repo by absolute host path, which breaks once
  bind-mounted into a container's own filesystem namespace — switched to a full self-
  contained clone instead of a literal `git worktree add`; (2) `Path.write_text()` on
  Windows re-translates `\n` to `\r\n`, silently corrupting the pre-push hook's shebang
  (fixed with a binary copy) — and separately, **this repo had no `.gitattributes` at
  all**, so a fresh Windows clone with the common `core.autocrlf=true` setting would hit
  the identical corruption on checkout regardless of any fix in Python; added
  `* text=auto eol=lf` repo-wide and force-set the executable bit on both `.sh`/hook files
  via `git update-index --chmod=+x` (this checkout has `core.fileMode=false`, so `chmod`
  alone never reached git's index); (3) git's "dubious ownership" check fires on bind-
  mounted directories not owned by the container's user — addressed with a system-wide
  (not `/home`, which is tmpfs and wiped per container) `safe.directory *`, acceptable
  because these containers are single-tenant and ephemeral, which is exactly the scenario
  that check exists to rule out; (4) `os.kill(pid, SIGTERM)` raises a plain `OSError` on
  Windows rather than `ProcessLookupError`, so a narrow `except` silently aborted teardown
  partway through on a re-run. Separately: WS pub/sub for egress events piggybacks on
  T-004's in-process broadcaster, so the same "single API replica only" caveat applies.
  CPU/RAM/disk limits and the allow-listed domain list are hardcoded defaults in
  `config.py`, not yet loaded from a config file as SPEC-003 implies ("from config") —
  revisit if per-ticket overrides are needed.

## fix(T-005) · Sandbox tests failing on Linux CI — 2026-07-04
- What changed: The first GitHub Actions run of T-005 (real Linux, not Docker Desktop)
  failed two of the seven sandbox integration tests that had passed locally. Root cause:
  Docker Desktop's bind-mount layer doesn't enforce real UID/GID checks, so a permission
  bug was invisible on this Windows dev box. On native Linux, the git clone is created on
  the host as the CI runner's user, then bind-mounted into the sandbox container which
  runs as a different, fixed uid (10001) — the container couldn't write
  `.git/refs/remotes/origin/*.lock` files, so *every* push failed (both the "should be
  rejected" and "should succeed" ones), which the "push to main rejected" assertion
  happened to paper over while "push to agent/T-xxx succeeds" failed outright. Separately,
  the egress-logging test used a fixed 3s sleep waiting for the async curl → squid access
  log → `tail -F` → HTTP POST pipeline, which isn't enough headroom on a loaded CI runner.
- Files touched: `apps/sandbox/src/sandbox/worktree.py` (new `make_writable_by_any_user`,
  called after clone+checkout on the real worktree), `apps/sandbox/src/sandbox/cli.py`
  (same treatment for the local-testing-only bare-cache bind mount),
  `apps/sandbox/tests/integration/test_sandbox_lifecycle.py` (poll up to 20s instead of a
  fixed sleep).
- Test evidence: Full sandbox suite (19 tests) still green locally after the fix. Chmod
  uses OR-in (`stat.st_mode | 0o777`/`0o666`) rather than overwrite, so it widens access
  without stripping any executable bit already set on files in the checkout — relevant
  once T-006's dev agent starts producing/running scripts inside these checkouts.
- Notes / follow-ups: Couldn't reproduce the original failure locally (Docker Desktop
  masks it), so this fix is verified by the fix's own logic and passing local tests, not
  by reproducing-then-fixing — watch the next CI run to confirm.

## fix(T-005) · Sandbox tests failing on Linux CI, round 2 — 2026-07-04
- What changed: The first fix wasn't enough — CI still failed the same two tests.
  (1) `push_to_main_rejected...`: the round-1 chmod only widened permissions on files
  existing at `sandbox up` time. The push test's own `git push` creates a *new*
  `refs/remotes/origin/agent/...` ref from *inside* the container (owned by its uid
  10001), after the host-side chmod already ran — the host-side pytest teardown then hit
  `PermissionError: Operation not permitted` trying to remove it. Fixed by chmod'ing from
  *inside* the sandbox container (which owns those files and can always touch them) right
  before `cli.down()` removes it, rather than relying on a one-time host-side pass.
  (2) `egress_attempts...`: `docker run -d` returns as soon as the proxy container is
  *created*, not once its process is far enough along to accept `exec` — the
  egress-forwarder subprocess's `docker exec <proxy> tail -F ...` was racing that gap and
  losing on a loaded CI runner, dying silently (its stderr was piped to `DEVNULL`). Added
  `docker_runtime.wait_until_execable()`, polling `docker exec <name> true` before
  `run_proxy()` returns, so the forwarder never starts until the proxy is actually usable.
  Also stopped swallowing the forwarder's stderr — it now goes to
  `~/.agent-factory-sandbox/<ticket>/egress_forwarder.log`, since this is a background
  process nothing else supervises and losing its errors is exactly how round 1's real
  cause went unnoticed.
- Files touched: `apps/sandbox/src/sandbox/docker_runtime.py` (`wait_until_execable`,
  called at the end of `run_proxy`), `apps/sandbox/src/sandbox/cli.py` (`down()` chmods
  `/workspace/repo` from inside the sandbox container before removing it; `up()` routes
  the forwarder's stdout+stderr to a log file instead of `DEVNULL`).
- Test evidence: Manually verified the forwarder log now surfaces real errors (drove a
  sandbox by hand with no API running: the log correctly captured a connection-refused
  error that round 1 would have swallowed silently). Full 19-test suite green locally
  after clearing out stale `~/.agent-factory-sandbox/` state left over from earlier manual
  testing — that contamination briefly looked like a regression (a fresh ephemeral test
  API always assigns ticket `T-001`, colliding with a stale local cache from an unrelated
  manual run) but wasn't caused by this change and can't happen on a clean CI runner.
- Notes / follow-ups: Same caveat as round 1 — Docker Desktop's bind-mount layer doesn't
  enforce real UID/GID checks or reproduce container-startup races the way native Linux
  does, so neither bug was reproducible locally; both fixes are reasoned from the exact
  CI error messages, not reproduce-then-fix. Watch the next CI run to confirm.

## fix(T-005) · Egress-log timing, round 3 — this time reproduced — 2026-07-04
- What changed: Round 2's push-permission fix worked (that test went green in CI), but
  the egress-logging test still came back completely empty (not even the `blocked.
  example.com` deny, which needs no internet access to log — a strong signal the whole
  pipeline was never seeing traffic, not that traffic was misclassified). This time
  reproduced it directly: `wait_until_execable()` confirms the *container's shell* is
  reachable, but Squid itself takes a bit longer to finish initializing and bind its
  listening socket — a `docker exec <proxy> true` succeeding doesn't mean Squid is
  actually accepting connections on 3128 yet. Curl racing ahead of that produces zero
  Squid log lines at all, allow or deny, exactly matching the symptom. Also incidentally
  confirmed Squid listens on `[::]:3128` (IPv6), not plain IPv4 — worth knowing if anyone
  probes this by hand later. Added `wait_until_port_listening()`, checking
  `/proc/net/tcp{,6}` directly (no ss/netstat/curl dependency inside the image) for the
  hex-encoded port, called right after `wait_until_execable()` in `run_proxy()`.
- Files touched: `apps/sandbox/src/sandbox/docker_runtime.py`
  (`wait_until_port_listening`).
- Test evidence: Reproduced locally this time (unlike rounds 1–2) by launching a sandbox
  and inspecting `/proc/net/tcp6` and `docker logs <proxy>` directly — confirmed Squid's
  own startup log ("Accepting HTTP Socket connections... listening port: 3128") lands
  after the container becomes exec-able. Verified end-to-end against a real running API:
  both the allowed (`pypi.org`, 200) and denied (`blocked.example.com`, 403) egress
  attempts now land as `ticket_events` reliably. Full 19-test suite green locally.
- Notes / follow-ups: Three rounds for one task's CI failure is a signal, not just bad
  luck — Docker Desktop's masking of real UID/GID and container-startup-timing behavior
  means this environment structurally can't catch these classes of bug before CI does.
  Worth remembering for T-006+: any new sandbox-adjacent readiness assumption should be
  treated as unverified until a real Linux run confirms it.

## T-006 · Dev agent integration — 2026-07-04
- What changed: Implemented SPEC-004. Two scope calls confirmed with the human first:
  the "recorded fixture run" in AC #1 is a hand-authored transcript (no real
  `ANTHROPIC_API_KEY` spend), and PR creation is stubbed (no scratch GitHub repo
  available) while the real `gh pr create` code path still exists, just untested here.
  Extended `apps/api` with `agent_runs`/`cost_ledger` tables and a small API surface
  (`POST .../agent-runs`, `.../agent-runs/{id}/complete`, `GET .../agent-runs`,
  `.../cost-ledger`, `.../cost-summary`) — `cost_ledger` rows are created automatically
  inside `complete_agent_run` whenever `cost_usd > 0`, so the AC #5 invariant
  (`cost_ledger` total == sum of `agent_runs.cost_usd`) holds by construction rather than
  needing separate bookkeeping. New `apps/orchestrator` package finally wires
  `packages/schemas` as a real dependency (deferred since T-003's changelog) — added a
  `py.typed` marker there so mypy actually resolves it instead of erroring on missing
  stubs. `agents/dev.py` builds the prompt from a real `TaskSpec` (+ `FailureReport` on
  bounce), streams every transcript event into `ticket_events` as it arrives via
  `ApiClient` (HTTP only — the orchestrator never touches the DB directly, per the
  layer-2/layer-5 split in docs/01-architecture.md), tracks cumulative cost against
  `task_spec.budget_usd` and wall-clock against a configurable timeout, and escalates via
  the real transition API on either breach. `ClaudeCodeRunner` and `GitHubClient` are
  `Protocol`s with a real implementation each (subprocess `claude -p ... --output-format
  stream-json`; `gh pr create`) plus a fixture/fake for tests — git commit+push themselves
  are real in tests (against a local bare "origin"), only the GitHub API call is faked.
- Files touched: `apps/api/src/api/db/models.py` (`AgentRun`, `CostLedgerEntry`,
  `AgentRunStatus`), `apps/api/migrations/versions/e9be75d61d32_*.py` (new),
  `apps/api/src/api/repositories/agent_run_repository.py` (new),
  `apps/api/src/api/services/agent_run_service.py` (new),
  `apps/api/src/api/routers/agent_runs.py` (new), `apps/api/src/api/contracts.py`,
  `apps/api/src/api/main.py`, `apps/api/tests/integration/test_agent_runs_api.py` (new);
  `apps/orchestrator/**` (new package); `packages/schemas/src/schemas/py.typed` (new);
  `Makefile` (`ORCHESTRATOR_DIR`, installs `packages/schemas` editable before orchestrator
  itself).
- Test evidence: `apps/api` full suite 34 passed (6 new agent-run tests) — including the
  cost_ledger==sum(agent_runs) invariant and that a zero-cost run creates no ledger entry.
  `apps/orchestrator`: 5 integration tests, one per SPEC-004 acceptance criterion, against
  a **real** throwaway Postgres + real migrated `apps/api` (mirrors T-005's
  `running_api` pattern) and a **real** local git remote — only Claude Code and GitHub are
  faked. Confirmed the budget-exceeded test actually stops mid-transcript (asserts the
  fixture's tail-end file, `test_app.py`, was never written) and that the escalation
  path lands the ticket in `escalated` via a real API round-trip, not just a return value.
  Added `testpaths = ["tests"]` to orchestrator's pytest config after noticing it was
  accidentally collecting `fixtures/*/workspace_diff/test_app.py` as a real test.
  `ruff check` + `mypy --strict` clean on all four Python packages. `pre-commit run
  --all-files` clean.
- Notes / follow-ups: `SubprocessClaudeCodeRunner`'s stream-json parsing is a best-effort
  approximation of Claude Code's actual headless output format, informed but unverified
  against a live run — revisit once this is exercised for real. Budget/timeout checks
  only run between transcript events, so a single very expensive or very slow tool call
  can overshoot before the next check point; acceptable for a fixture-paced test, worth
  revisiting for the real subprocess runner (e.g. a watchdog thread). No LangGraph yet
  despite docs/06 naming it for orchestration — `run_dev_agent` is a plain function; the
  per-ticket graph (exec_panel → planner → dev_loop → qa) is out of scope until those
  other agents exist.

## T-007 · QA gate & bounce loop — 2026-07-04
- What changed: Implemented SPEC-005 in `apps/api` (webhook + distiller) and as a new
  `.github/workflows/agent-pr-gate.yml` (CI job ordering + security/coverage gates).
  `POST /webhooks/ci-result` is the receiver: HMAC-SHA256 verified (`X-Hub-Signature-256`,
  `CI_WEBHOOK_SECRET` — unset disables verification, same Phase-1 dev-convenience pattern
  as the other stubbed integrations), it requires the ticket be `in_qa`, then either
  transitions straight to `done` (green) or runs the new deterministic failure distiller
  (`services/failure_distiller.py` — regex-parses pytest `FAILED <nodeid> - <reason>`
  summary lines / vitest `FAIL`/`✗` lines into a `packages/schemas.FailureReport`, no LLM
  call; a haiku-class call isn't needed to extract "which tests failed" and wouldn't be
  as testable) before requesting `bounced`. AC5's "third consecutive red pipeline escalates"
  is implemented via the *existing*, already-tested T-003 state machine guard exactly as
  written in docs/03-state-machine.md (`bounce_count == 3`) rather than a new one — that
  guard fires on the 4th red pipeline (3 bounces have to happen first), which is one more
  than SPEC-005's prose literally says. Flagging this rather than quietly picking one:
  changing the guard to fire on the 3rd would contradict T-003's own shipped, tested
  behavior ("the 4th bounce attempt is refused ... becomes escalated") and the state
  machine doc; I left both as-is and treated "third consecutive red pipeline" as informal
  shorthand for "the pipeline run that would be the 4th bounce." Human: say the word if
  you want the guard changed instead — it's a one-line change plus a docs/03 update.
  `agent-pr-gate.yml` runs `smoke -> unit -> integration -> e2e` gated via `needs:` (so a
  failing unit test really does stop e2e from starting — AC1), `semgrep`/`dependency-audit`
  (pip-audit + npm audit) as blocking checks in parallel once `unit` is green, and a
  `coverage` job running the new `make coverage-gate` (diff-cover, 80% floor, all four
  Python packages' coverage.xml merged, compared against `origin/main`). Secret scanning
  (AC3) isn't duplicated here — `ci.yml`'s existing `gitleaks` job already runs on every
  PR, agent-authored or not. A final `report-result` job always runs, collects any
  uploaded failure logs from the unit/integration/e2e jobs, and POSTs the outcome to the
  webhook — this is what actually drives the ticket transition; the workflow itself never
  touches ticket state directly.
- Files touched: `apps/api/src/api/services/failure_distiller.py` (new),
  `apps/api/src/api/services/webhook_service.py` (new),
  `apps/api/src/api/routers/webhooks.py` (new), `apps/api/src/api/contracts.py`
  (`CIResultWebhook`), `apps/api/src/api/main.py`, `apps/api/tests/test_failure_distiller.py`
  (new), `apps/api/tests/integration/test_ci_webhook_api.py` (new);
  `.github/workflows/agent-pr-gate.yml` (new); `Makefile` (`test` split into
  `test-unit`/`test-integration` — same combined behavior, `check`/`test` unchanged — plus
  new `coverage-gate` target; `apps/api` venv now installs `packages/schemas` first,
  matching the orchestrator's pattern); `apps/sandbox/pyproject.toml`,
  `apps/orchestrator/pyproject.toml`, `packages/schemas/pyproject.toml` (added
  `pytest-cov`, needed for the coverage gate); `.env.example` (`CI_WEBHOOK_SECRET`);
  `.gitignore` (`.coverage`, `coverage.xml`).
- Test evidence: `apps/api` full suite 45 passed (11 new: 5 distiller unit tests, 6 webhook
  integration tests covering green→done, red→bounced with a FailureReport whose
  `failing_tests` matches the injected CI log verbatim, the 4-red-pipelines→escalated
  sequence, 404 for a missing ticket, 409 for a ticket not in `in_qa`, and signature
  rejection/acceptance) — all against a real Postgres via testcontainers. `ruff check` +
  `mypy --strict` clean on `apps/api`, `apps/sandbox`, `apps/orchestrator`,
  `packages/schemas` after the pyproject changes. Manually validated the exact
  `make coverage-gate` command sequence (pytest --cov + diff-cover) end-to-end against
  this task's own uncommitted diff: 96% changed-line coverage, above the 80% floor.
  `agent-pr-gate.yml` itself is untested here — no `make` binary in this dev environment
  and no way to trigger a real `pull_request` event from `agent/*` without pushing;
  written carefully (`pipefail` on every `tee`d step, `jq` for JSON body construction
  instead of string interpolation) but treat it like T-005's rounds 1-3: expect to iterate
  once it runs for real.
- Notes / follow-ups: web-side coverage (vitest) isn't wired into `coverage-gate` yet —
  `apps/web` has no `@vitest/coverage-v8` dependency or coverage script, and adding one
  felt too risky to do unverified in the same change as the Python-side gate. AC4 is
  covered for the Python packages, which is where agent-authored PRs mostly land today;
  revisit before an agent is ever asked to touch `apps/web` under this gate.
- Fix (same day, after CI ran): `make e2e` failed in CI —
  `ModuleNotFoundError: No module named 'schemas'` importing `api.main` — because
  Playwright's `webServer` boots the API via `apps/api/scripts/e2e-server.sh`, which
  builds its own venv independently of the Makefile and was never updated to install
  `packages/schemas` first. `ci.yml`'s `a11y` job builds the api venv the exact same way
  and had the identical latent bug (hadn't surfaced yet only because nothing under
  `apps/api` imported `schemas` before this task). Fixed both to `pip install -e
  ../../packages/schemas` before `pip install -e ".[dev]"`, matching the Makefile.

## T-008 · Cost, SSO & pilot dashboard — 2026-07-04
- What changed: Implemented SPEC-006. Scope call confirmed with the human first: OIDC is
  wired for real against Google (Authlib, `docs/06-tech-stack.md`'s locked choice) — a
  live Google Cloud OAuth client isn't available here, so `/auth/login` and `/auth/callback`
  are real code (501 until `OIDC_ISSUER_URL`/`CLIENT_ID`/`CLIENT_SECRET` are set) plus a
  `POST /auth/dev-login` that mints the exact same session JWT without the round-trip
  (`AUTH_DEV_MODE=true`, local/CI only) — same stub-alongside-real pattern as the sandbox's
  credential broker and the orchestrator's GitHub client. Every route except `/health`,
  `/webhooks/*` and `/auth/*` now requires `Authorization: Bearer <token>`
  (`api/auth.py:get_actor_context`, applied at the router level via
  `dependencies=[Depends(...)]` rather than per-endpoint, so a new endpoint can't
  accidentally ship unauthenticated) — either a session JWT (human, role read from the new
  `users` table, defaulting to viewer unless pre-seeded via `ADMIN_EMAILS`) or the shared
  `AGENT_FACTORY_SERVICE_TOKEN` (apps/orchestrator, apps/sandbox — full trust, role=admin).
  The old `X-Actor`/`X-Actor-Role` header stub and the web `ActorSwitcher` are gone.
  Escalation inbox: added `escalated -> in_progress` to the state machine (human-actor-only
  guard, `docs/03-state-machine.md` updated in this PR per the hard rule) and a
  `POST /tickets/{id}/return-to-dev` endpoint that writes the approver's note as a
  FailureReport-shaped `test_result` event (same shape the CI webhook's failure distiller
  produces) before transitioning — so the dev agent's next attempt sees it the same way it
  would see a CI failure. Cost bar: the drawer (and `TicketOut`) now derive spend from
  `GET .../cost-summary` (`cost_ledger`'s sum) instead of a `spent_usd` ticket column that
  was never written to after creation — removed that column outright (migration
  `0cf581260d39`) rather than leave a permanently-zero, misleading field around, since
  `cost_ledger` is already documented as the $/ticket source of truth. Dashboard: new
  `dashboard_service.py` computes the four vision.md metrics from one shared per-ticket
  row set (`dashboard_repository.list_dashboard_rows`) that the CSV export also serializes
  directly, so re-deriving the aggregates from the CSV mathematically reproduces
  `/dashboard/metrics` (AC4) rather than the two just happening to agree. Added
  `tickets.created_at` (tickets start in `ready` in Phase 1, so this doubles as the cycle
  clock's start) and `escaped_defect_reports` (manual entry, append-only) to back it.
- Flagged rather than silently decided: `docs/00-vision.md`'s "first-pass QA rate ≥ 50%
  (tickets closed with ≤ 1 bounce)" doesn't say what the rate is *out of*. Implemented it
  as `count(done AND bounce_count<=1) / count(done OR escalated)` — i.e. escalated tickets
  count against the rate rather than being excluded from the denominator, since excluding
  QA failures from a QA-effectiveness metric would make it gameable. Say the word if you
  want a different denominator.
- Files touched: `apps/api/src/api/auth.py` (rewritten), `apps/api/src/api/routers/auth.py`
  (new), `apps/api/src/api/routers/dashboard.py` (new),
  `apps/api/src/api/services/{user,dashboard}_service.py` (new),
  `apps/api/src/api/repositories/{user,dashboard}_repository.py` (new),
  `apps/api/src/api/domain/state_machine.py` (`escalated -> in_progress`),
  `apps/api/src/api/db/models.py` (`User`, `UserRole`, `EscapedDefectReport`,
  `Ticket.created_at`, dropped `Ticket.spent_usd`), `apps/api/migrations/versions/
  0cf581260d39_*.py` (new), `apps/api/src/api/services/ticket_service.py`
  (`return_to_dev`), `apps/api/src/api/routers/{tickets,agent_runs}.py` (router-level auth
  dependency), `apps/api/pyproject.toml` (`authlib`, `pyjwt`, `itsdangerous`); 9 new/updated
  test files under `apps/api/tests/`; `apps/orchestrator/src/orchestrator/api_client.py` +
  its test conftest, `apps/sandbox/src/sandbox/events_client.py` + its test conftest (both
  now send the service token); `apps/web/src/auth/{AuthContext,LoginPage}.tsx` (new,
  replace `ActorContext`/`ActorSwitcher`), `apps/web/src/dashboard/DashboardPage.tsx`
  (new), `apps/web/src/App.tsx` (auth gate + Board/Dashboard nav), `apps/web/src/api/
  {client,queries,types}.ts`, `apps/web/src/board/TicketDrawer.tsx` (cost bar,
  escalation-inbox "return to dev" UI replacing the generic approve/reject for that one
  gate), `apps/web/e2e/*` (dev-login helper replacing the old localStorage-only actor
  stub), `apps/web/scripts/lighthouse-a11y.mjs` (mints a dev-login token so the a11y audit
  still measures the board, not the new login gate); `docs/02-data-model.md`,
  `docs/03-state-machine.md`.
- Test evidence: `apps/api` full suite 63 passed (18 new: auth 401/dev-login/me/501,
  escalation return-to-dev incl. 403 for viewer, dashboard golden-fixture test with a
  hand-seeded 5-ticket dataset asserting exact numbers for all four metrics, CSV↔dashboard
  cross-check, a `get_or_create_user` race-condition regression test — see below).
  `apps/orchestrator` 5 passed, `apps/sandbox` 19 passed after wiring the service token
  into both their real (non-fixture) HTTP calls. `ruff check` + `mypy --strict` clean on
  all four Python packages. Web: `eslint`/`tsc -b`/`vitest` clean. Ran the real Playwright
  suite (not just unit tests) against a live API + web dev server: all 5 e2e specs passed,
  including the escalation-inbox role-gating test switching between two real dev-login
  sessions mid-test. Lighthouse a11y: 100/100 on the authenticated board page (was 100/100
  pre-auth too; confirmed the new login page separately also scores 100/100).
- Bug found via the concurrent e2e run (not by inspection): `user_service.get_or_create_user`
  raced under Playwright's 5 parallel workers all logging in as the same default viewer in
  `beforeEach` — two workers' `get_user()` both returned `None` before either committed,
  so the loser's `INSERT` hit the `users_pkey` unique constraint and 500'd. Fixed by
  catching `IntegrityError` and re-fetching the winner's row; the same race exists in the
  real Google OIDC callback path (two tabs, first login) and is now handled there too.
  Added a repository-level regression test pinning the exception type Postgres actually
  raises for this constraint, since the fix's `except IntegrityError` depends on it.
- Notes / follow-ups: role changes take up to the session TTL (12h) to take effect for an
  already-logged-in user, since the role is embedded in the JWT at mint time rather than
  looked up per-request — acceptable for Phase 1's small pilot user base, revisit if that
  becomes a real operational papercut. No admin UI to promote a user past the
  `ADMIN_EMAILS`-seeded bootstrap set; that's a direct DB update for now. Websocket auth
  (`/ws/tickets/{id}`) is unchanged from the header-stub era — AC1 is about REST access,
  and browsers can't attach custom headers to a native WebSocket handshake, so closing
  this gap needs a token-via-query-param design; flagging it, not fixing it here.

## T-009 · Pilot run — 2026-07-05
- What changed: Ran the real loop end-to-end for the first time — every prior "real"
  integration (Claude Code subprocess, `gh pr create`, the CI gate) had been implemented
  but deliberately never exercised live (see each task's own changelog entry). Scope
  reduced from the spec's 20-30 tickets to 3 by explicit human decision once the first
  ticket proved the whole loop worked for real; see `tasks/PILOT-REPORT.md` for the full
  writeup, including a real leaked-secret near-miss caught before commit (a real
  Anthropic key pasted into `.env.example` instead of `.env`) and four real bugs the first
  live run surfaced and fixed, three specific to this repo's CI/orchestrator code and one
  — an outdated `claude` CLI's incompatibility with `claude-sonnet-5` under
  `ANTHROPIC_API_KEY` auth — relevant to any real deployment, not just the pilot. Added a
  one-off `apps/orchestrator/scripts/run_pilot.py` (+ `pilot_tickets.py`) to drive it;
  explicitly not part of the product (documented as such in the script's own docstring).
- Files touched: `apps/orchestrator/scripts/run_pilot.py`, `scripts/pilot_tickets.py`
  (new, ops-only); `apps/orchestrator/src/orchestrator/claude_runner.py` (`--verbose`,
  tool-call classification, transient-retry); `.github/workflows/agent-pr-gate.yml` and
  `.github/workflows/ci.yml` (pinned Actions to SHAs); `apps/api/Dockerfile`,
  `apps/web/Dockerfile` (non-root `USER`); `.env.example` (reverted an accidentally
  real key back to a placeholder; added `GITHUB_TOKEN`); `tasks/PILOT-REPORT.md` (new).
- Test evidence: 3 real tickets (T-001 README update, T-002 README update, T-003 a unit
  test), each a real Claude Code run → real commit/push → real PR → real
  `agent-pr-gate.yml` run on GitHub Actions → real webhook call → ticket `done`, with full
  event history (transcript + cost + transitions). All 3 succeeded on the first attempt
  once the CLI was updated; zero bounces, zero escalations. Real cost: $2.16 total
  ($0.55/$0.60/$1.01). Cross-checked `/dashboard/metrics` against `/dashboard/export.csv`
  by hand (median cost, median cycle time) — matched.
- Notes / follow-ups: sandbox isolation was never wired into this run (the human
  explicitly accepted running without it and without branch protection on `main` for this
  pilot) — don't treat "zero security incidents" here as validating that path for a less
  curated or larger batch. All 3 tickets were docs/test-only by deliberate safest-first
  selection; re-run with a larger, less hand-picked set before trusting the first-pass QA
  rate as statistically meaningful. Keep the `claude` CLI current — the outdated-CLI bug
  found here would silently manifest as "the dev agent produced no changes" with zero
  events recorded, easy to misdiagnose as a prompt problem instead of a CLI version issue.

## T-101 · Eval harness & golden sets — 2026-07-05
- What changed: Implemented SPEC-101's `make eval` in
  `apps/orchestrator/src/orchestrator/evals/` (loader, dev/distiller scorers, a
  haiku-class judge, Langfuse Cloud logging, JUnit+markdown reporting, a CLI). Seeded
  `evals/dev/` (10 cases: 3 real Phase-1 pilot PRs pinned to their pre-PR SHA + 7
  hand-authored synthetic cases) and `evals/distiller/` (13 cases) golden sets plus
  `evals/thresholds.yaml`; `evals/planner/`/`evals/review/` are scaffolded but empty
  (`not_yet_enforced: true`) until T-103/T-106 seed them. Two prerequisite fixes were
  required for the harness to detect anything real rather than being theater:
  `prompts/dev-agent.md` was never actually reaching the `claude` CLI (no
  `--append-system-prompt`, and `agents/dev.py`'s `build_prompt()` only assembles the
  per-task TaskSpec/FailureReport) — fixed in `claude_runner.py`. And
  `prompts/failure-distiller.md` (bumped v0.1 → v0.2) referenced "schema in
  packages/schemas" without inlining it, so a haiku-class model guessed a nested JSON
  shape instead of `FailureReport`'s flat string lists — fixed by inlining the exact
  output shape. `apps/api`'s production failure-distiller (SPEC-005's deliberate
  deterministic regex stand-in) was not touched; the eval-only LLM path in
  `distiller_scorer.py` exists solely to score the prompt file's own quality.
  Added `CODEOWNERS` (`/evals/thresholds.yaml @Deexit1`) and a `threshold-governance`
  CI job that fails if a floor is lowered without an approving codeowner review, backed
  by newly-enabled branch protection on `main` (require PR + codeowner review;
  `enforce_admins: false`) — `main` had **no** branch protection at all before this,
  contrary to what T-009's changelog assumed would eventually be set up. New
  `.github/workflows/eval-gate.yml` runs `make eval --only-changed` on any
  `prompts/**`/`evals/**`/routing-config diff (not restricted to `agent/*` branches,
  unlike `agent-pr-gate.yml`, since a human editing a prompt must hit this gate too) and
  posts a PR comment with per-set scores and the worst-3 cases' real candidate output.
- Files touched: `apps/orchestrator/src/orchestrator/evals/**` (new: `loader.py`,
  `dev_scorer.py`, `distiller_scorer.py`, `judge.py`, `langfuse_client.py`, `report.py`,
  `runner.py`), `apps/orchestrator/tests/evals/**` (new), `apps/orchestrator/src/
  orchestrator/claude_runner.py` (`--append-system-prompt` wiring),
  `apps/orchestrator/tests/test_claude_runner.py`, `apps/orchestrator/pyproject.toml`
  (`anthropic`, `langfuse` v4, `pyyaml`, `flask` dev dep), `apps/orchestrator/scripts/
  check_threshold_governance.py` (new), `evals/**` (new: cases, `thresholds.yaml`,
  `planner/README.md`, `review/README.md`), `CODEOWNERS` (new), `Makefile` (`eval`
  target), `.github/workflows/eval-gate.yml` (new), `prompts/failure-distiller.md`
  (v0.1 → v0.2), `docs/06-tech-stack.md` (Langfuse Cloud note), `docs/08-evals.md`
  (corrected the dev-set seed-count claim), `.env.example`/`.env` (`LANGFUSE_BASE_URL`,
  matching the installed SDK's current env var name — not `LANGFUSE_HOST`), `.gitignore`
  (`evals/results/`).
- Test evidence: `apps/orchestrator` unit suite green (30 passed: loader, judge,
  dev/distiller scorer logic against fakes — no real API spend in the base suite, same
  convention as every prior task). Then verified for real against live Anthropic +
  Langfuse Cloud + GitHub Actions, not just unit tests: distiller set scores 86.5–87.5/
  100 (floor 75) across three separate real runs; deleting `failure-distiller.md`'s
  Rules section drops it to 70.6 (red), confirming the harness actually detects a
  prompt regression (AC1); restoring it goes green again with both runs visible in
  Langfuse Cloud tagged with distinct prompt versions (AC2); two full runs on an
  unchanged prompt differ by ~0.2%, well under AC4's 2% bar. Dev set (live Claude Code,
  real `claude-sonnet-5` invocations against all 10 cases): 87.1/100 (floor 70) on the
  first real run. Opened PR #6 against `main` for real, which triggered
  `eval-gate.yml` for the first time — surfaced and fixed three real CI-only bugs a
  local run couldn't have caught: the eval job's default `GITHUB_TOKEN` needed an
  explicit `permissions: pull-requests: write` block to post PR comments;
  `check_threshold_governance.py` crashed on `evals/thresholds.yaml`'s first-ever
  introduction (no prior version on the base ref to diff against); and the initial PR
  comment only showed judge rationale, not real diffs/candidate output, so `report.py`
  now includes each worst-3 case's full candidate JSON/diff in a collapsed `<details>`
  block. AC3's fail-without-approval path was verified for real (a dry run against PR
  #6's actual, zero reviews correctly failed, naming the codeowner); the
  approve-then-pass half can't be demonstrated on this repo — GitHub categorically
  blocks self-approval and `@Deexit1` is the only codeowner/contributor, confirmed via a
  real `gh api` call returning "Review Can not approve your own pull request".
- Notes / follow-ups: SPEC-101's ask to seed `evals/dev/` from "20-30 pilot tickets"
  was never achievable — T-009 was descoped to 3 real tickets, and there is no
  retrievable transcript data from that run (its scratch clones were torn down). Seeded
  3 real (from the actual merged PR diffs) + 7 synthetic cases sized like real pilot
  tickets instead; documented the discrepancy in `docs/08-evals.md` rather than silently
  padding the count. The solo-maintainer self-approval gap above means
  `evals/thresholds.yaml` changes will always need an explicit admin merge-override on
  this repo, not a real second-party review — acceptable for now, but revisit if this
  project ever gets a second real contributor (a genuine codeowner review would then
  become possible and should replace the override path). `evals/planner/` and
  `evals/review/` remain unseeded stubs; T-103/T-106 must flip
  `not_yet_enforced: false` once they seed real cases, or those sets stay silently
  skipped forever.
