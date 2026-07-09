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

## T-102 · State machine v2 + SaaS groundwork — 2026-07-06
- What changed: Inserted `TicketState.IN_REVIEW` between `in_progress` and `in_qa`
  (`apps/api/src/api/domain/state_machine.py`), making `in_review` bounce/escalate
  through the same shared `ticket.bounce_count` that QA already used — a 4th bounce
  from either gate now auto-escalates, verified by interleaving one review-bounce with
  two QA-bounces. `approved → planning → ready` needed no work: it was already
  whitelisted and guarded since T-003, just unreached because `create_ticket` always
  starts tasks in `ready`. Laid both standing SaaS-readiness foundations from
  `CLAUDE.md`: added an `orgs` table + `org_id` (NOT NULL FK, single `default` org
  backfilled) to all 7 existing domain tables, threaded `org_id` through every
  repository/service/router function (routers read it off a new
  `ActorContext.org_id`, currently always `DEFAULT_ORG_ID` from the new
  `api/tenancy.py` module — real per-request org resolution from auth membership is
  T-201's job, not this ticket's); and built `packages/llm_router`, a new package
  mirroring `packages/schemas`'s layout, whose `route(role, ...)` function is now the
  *only* place in the repo that imports `anthropic` — migrated the two real direct-SDK
  call sites (`orchestrator/evals/judge.py`, `orchestrator/evals/distiller_scorer.py`)
  to call it, and added `scripts/check_llm_router_gate.py` (wired into `make check`) to
  keep it that way.
- Two real bugs found by actually running the suites, not just writing them: (1)
  `apps/orchestrator/src/orchestrator/agents/dev.py`'s `run_dev_agent` transitioned
  straight from `in_progress` to `in_qa` after opening a PR — a real production call
  site the state-machine change would have broken silently (4 orchestrator integration
  tests failed with a live 409 until fixed). Since the Review agent (T-106) doesn't
  exist yet to hold a ticket in `in_review`, the dev agent now transitions through it
  immediately (`in_review` then `in_qa`) — a temporary bridge, not a real review gate;
  revisit when T-106 lands. (2) `apps/web`'s board (`src/board/columns.ts`,
  `src/api/types.ts`) had a fixed state list with no `in_review` column — tickets in
  that state would have silently vanished from the board (T-004 regression); added the
  column and the type-union member, `npm run typecheck` clean.
- Deliberately permissive, not deferred: `in_review`'s two data-dependent guards from
  docs/03-state-machine.md ("diff non-empty" on entry, "review comments recorded" on
  exit) have no real Review agent yet to source that data from, so both transitions are
  currently ungated for any actor — same non-goal precedent as T-101 leaving
  `evals/planner|review` unseeded. They become real guards when T-106 ships.
- Files touched: `apps/api/src/api/db/models.py` (`Org` model, `IN_REVIEW` enum
  member, `org_id` on 7 models), `apps/api/src/api/domain/state_machine.py`,
  `apps/api/src/api/tenancy.py` (new), `apps/api/src/api/auth.py`
  (`ActorContext.org_id`), `apps/api/src/api/repositories/*.py`,
  `apps/api/src/api/services/*.py`, `apps/api/src/api/routers/*.py` (org_id threading),
  `apps/api/migrations/versions/a1b2c3d4e5f6_*.py` (new, `in_review` enum value),
  `apps/api/migrations/versions/b2c3d4e5f6a7_*.py` (new, `orgs` + backfill),
  `apps/api/tests/integration/test_migration_replay.py` (new),
  `apps/api/tests/integration/conftest.py` (seed default org, truncate `orgs`),
  `apps/api/tests/domain/test_state_machine.py`,
  `apps/api/tests/integration/test_tickets_api.py` (+3 new tests),
  `apps/api/tests/integration/{test_dashboard_api,test_ci_webhook_api,
  test_ticket_repository,test_user_service}.py` (updated for `in_review`/`org_id`),
  `packages/llm_router/**` (new package), `apps/orchestrator/src/orchestrator/evals/
  {judge.py,distiller_scorer.py}` (→ `llm_router.route()`),
  `apps/orchestrator/src/orchestrator/agents/dev.py` (in_review bridge transition),
  `apps/orchestrator/pyproject.toml` (dropped direct `anthropic` dep),
  `scripts/check_llm_router_gate.py` (new), `Makefile` (`llm-router-gate` target +
  `LLM_ROUTER_DIR` venv wiring), `apps/web/src/board/columns.ts`,
  `apps/web/src/api/types.ts`, `docs/02-data-model.md` (`orgs` table).
- Test evidence: `apps/api` 70/70 green (unit + integration against a real Postgres 16
  testcontainer, migrations run for real). `test_migration_replay.py` spins up its own
  container, stops at the pre-T-102 revision, inserts a ticket in the exact Phase-1
  shape, upgrades to head, and drives it through the full new lifecycle — proving AC2
  for real, not by assertion. `apps/orchestrator` unit (30) and integration (5) suites
  green after the `dev.py` fix. `scripts/check_llm_router_gate.py` run standalone: 0
  violations. Re-ran the distiller eval set for real against the live Anthropic API
  post-`llm_router`-migration: 86.7/100 (floor 75), consistent with T-101's baseline —
  confirms the refactor didn't change real model behavior. `apps/web`
  `npm run typecheck` clean; `apps/sandbox` unit suite unaffected (12 passed).
- Notes / follow-ups: `docs/02-data-model.md`'s `artifacts` table was already
  documented but never implemented as a model before this ticket — pre-existing drift,
  not introduced here, left alone since T-102's scope is state machine + org_id +
  router only. `RBAC` roles beyond today's `admin|approver|viewer` (docs/09-saas-model.md
  mentions `owner/approver/member/viewer`) are explicitly T-201's job. The `llm_router`
  grep-gate cannot and does not cover `claude_runner.py`'s CLI-subprocess path to the
  `claude` binary — a known, disclosed gap; T-202 (BYOK) will need a different
  mechanism there (e.g. per-org env injection into the subprocess), not a grep gate.

## T-103 · Planner agent + planning review UI — 2026-07-06
- What changed: First real LangGraph adoption in the repo (`docs/06-tech-stack.md`) —
  `apps/orchestrator/src/orchestrator/agents/planner.py` is a single-node `StateGraph`
  (no `PostgresSaver` checkpointing yet; nothing to resume across with one node,
  revisit when T-104+ chains multiple agents into a real multi-step graph). Built the
  actual idea/epic/task workflow the state machine only had enum placeholders for:
  idea tickets now enter directly at `approved` (contracts.py requires `budget_usd` >
  0 for `IDEA` tickets); `approved -> planning` guard reuses the existing
  budget-positive check; `planning -> escalated` and `escalated -> planning` are new
  whitelist entries for the Planner's questions[] round trip
  (`ticket_service.answer_planning_questions`); `planning -> ready`'s guard now checks
  a real DAG-cycle test (DFS with a recursion stack over the TaskSpec-id space each
  task's `spec` JSONB carries — deliberately not the real Ticket.id space, since the
  Planner assigns its own scratch ids before any Ticket row exists), a task-budget-sum
  check, and a recorded `Approval(gate=BUDGET, decision=APPROVED)` — resolving two
  different "budget" concepts in SPEC-102 by re-reading docs/00-vision.md's two human
  checkpoints (idea go/budget at creation vs. plan-budget approval before the dev
  queue). Epics/tasks are stored as real child `Ticket` rows (`parent_id` chaining
  idea -> epic -> task), not a JSON blob, reusing every existing piece of ticket
  infrastructure (events, org_id scoping, dashboard, board) for free; on
  `planning -> ready`, descendant epic/task tickets cascade from `planning` to `ready`
  in the same transaction. Extended `packages/schemas.TaskSpec` with `depends_on`/
  `estimate_days`/`epic_id`, and added `Epic`/`PlannerPlan`/`PlannerQuestions`.
  Extended `packages/llm_router.route()` to return a `RouteResult` (text + model +
  tokens + cost) instead of a bare string — needed to record real `agent_runs`/
  `cost_ledger` rows for the planner, which (unlike the dev agent's CLI-transcript-cost
  events) has no other way to learn its own token usage — and added a `"planner"` role
  routed to an opus-class model. Added `EventKind.EDIT` + `PATCH /tickets/{id}`
  (approver/admin-gated) so human inline-edits to a Planner-produced TaskSpec are
  versioned as before/after events (AC6). Added a new third web view ("Planning") in
  the existing `useState<View>` switch (no router in this app) with a review screen:
  idea list -> descendant epic/task tree -> inline task edit -> "Approve & start".
  Seeded `evals/planner/` with 15 synthetic idea fixtures (no real ideas exist to seed
  from, same honesty precedent as T-101's dev set) and a real scorer
  (`planner_scorer.py`, 60/40 deterministic/judge blend matching the dev set).
- Real bug found via a real API call, not a unit test: `claude-opus-4-8` rejects the
  `temperature` parameter outright ("`temperature` is deprecated for this model") —
  `llm_router.route()` now omits it for opus-class models while still sending it for
  haiku (needed for AC4-style reproducibility on the judge). Would have silently
  broken every real planner call had it shipped unnoticed.
- Files touched: `packages/schemas/src/schemas/models.py` (+tests),
  `packages/llm_router/src/llm_router/__init__.py` (`RouteResult`, `planner` role,
  temperature fix, +tests), `apps/orchestrator/src/orchestrator/evals/{judge.py,
  distiller_scorer.py}` (updated for `RouteResult`), `apps/orchestrator/src/
  orchestrator/json_utils.py` (new, shared JSON-fence extraction, judge.py re-exports
  it), `apps/orchestrator/src/orchestrator/agents/planner.py` (new),
  `apps/orchestrator/src/orchestrator/api_client.py` (`create_ticket`, `descendants`),
  `apps/orchestrator/src/orchestrator/evals/{loader.py,planner_scorer.py,runner.py}`
  (planner set wiring), `apps/orchestrator/pyproject.toml` (`langgraph` dep),
  `apps/orchestrator/tests/integration/test_planner_agent.py` (new),
  `apps/api/src/api/domain/state_machine.py`, `apps/api/src/api/services/
  ticket_service.py` (initial-state logic, plan sanity gates, cascade, edit
  versioning, `answer_planning_questions`), `apps/api/src/api/repositories/
  ticket_repository.py` (`get_descendants`, `has_approval`, `update_ticket_fields`),
  `apps/api/src/api/routers/tickets.py` (`descendants`, `answer-planning-questions`,
  `PATCH`), `apps/api/src/api/contracts.py`, `apps/api/src/api/db/models.py`
  (`EventKind.EDIT`), `apps/api/migrations/versions/c3d4e5f6a7b8_*.py` (new,
  `EventKind.EDIT` value, chained after T-102's `b2c3d4e5f6a7`), `apps/api/tests/integration/
  test_idea_planning_workflow.py` (new), `apps/web/src/planning/
  PlanningReviewPage.tsx` (new), `apps/web/src/App.tsx`, `apps/web/src/board/
  columns.ts`, `apps/web/src/api/{types.ts,client.ts,queries.ts}`,
  `evals/planner/**` (new cases + README), `evals/thresholds.yaml`.
- Test evidence: `packages/schemas` 18/18, `packages/llm_router` 4/4 (incl. the
  temperature-omission regression test), `apps/api` 84/84 (unit + integration against
  a real Postgres 16 testcontainer — includes the full idea -> planning -> epics/
  tasks -> ready flow, the DAG-cycle rejection, the budget-sum rejection, the
  questions -> escalated -> planning round trip, and the edit-event versioning),
  `apps/orchestrator` 37 unit + 7 integration (including the new planner-agent tests,
  against a real Postgres + API with a mocked LLM response for cost control). `apps/web`
  `npm run typecheck`/`lint` clean. All of the above: zero real API spend. Separately,
  ran the real Planner against live opus for 2 of the 15 `evals/planner/` cases (not
  the full set, and not through `make eval` — a targeted ad-hoc check to bound API
  spend under a mid-session credit constraint): both real calls returned
  `questions[]` instead of a plan, and `planner_scorer.invoke_planner` doesn't handle
  that response shape — it raises instead of scoring gracefully.
- **Follow-up (same day): AC5 fixed and `evals/planner` enforced for real.** Two real
  bugs, both fixed: (1) `planner_scorer.invoke_planner`/`score_case` now branches on
  `PlannerQuestions` vs `PlannerPlan` instead of assuming a plan — a `questions[]`
  response is scored (deterministic=0, judge-rated) instead of raising;
  `judge.py`'s `"planner"` rubric prompt gained explicit guidance to score a
  needlessly-conservative `questions[]` response low, since every reference in this
  set is a full plan (the idea was demonstrably plannable). (2) `prompts/planner.md`
  (v0.1 → v0.2) never specified the exact output JSON shape — the live model
  responded with rich `{id, topic, question}` objects instead of `PlannerQuestions`'
  flat `list[str]`, and asked unnecessary clarifying questions on well-specified
  ideas; v0.2 adds an explicit "Output shape" section for both the plan and
  questions responses, plus "prefer a reasonable default over a question" guidance.
  Re-ran all 15 cases for real after both fixes: 15/15 valid plans, zero errors,
  zero questions, `deterministic_score` 100 on every case (schema/DAG/budget/
  verification all pass), combined score avg 88.6 (min 76.8, max 96.8). Set
  `evals/thresholds.yaml`'s `planner.floor: 70` (same reasoning as the dev set's
  initial floor — a buffer below the observed minimum) and flipped
  `not_yet_enforced` to `false`. AC5 is now genuinely satisfied, not just built.
- Notes / follow-ups: `run_planner_agent` has no auto-dispatch trigger (invoked by
  tests/an ops script only) — matches `run_dev_agent`'s own precedent; real dispatch
  is T-104 (Delivery Manager)'s job. Not building T-104's capability registry or
  Delivery Manager here — this ticket stops at `planning -> ready`. Planner-set
  run-to-run reproducibility (AC4-style, <2% drift) has not been separately measured
  — only one real pass over the 15 cases was run, to bound API spend.

## T-104 · Capability registry + Delivery Manager — 2026-07-06
- What changed: New `capability_registry.yaml` at repo root (profile → model/
  base_image/skills/max_parallel, plus a `repo_concurrency_limit`), read by a small,
  intentionally duplicated loader in each of `apps/api` and `apps/orchestrator`
  (`capability_registry.py`, same small-duplication precedent as T-103's
  `orchestrator/json_utils.py` — separate deployables, not worth cross-importing).
  Seeded with one `dev-generalist` profile pointing at today's existing hardcoded
  model/image; real multi-profile skill-matching is T-105's job. All hard gates live
  in `apps/api`'s `state_machine.py`/`ticket_service.py` (code, not the prompt),
  mirroring every other gate T-102/T-103 already established as computed
  `TransitionRequest` fields: `deps_done` (walks `ticket.spec["depends_on"]` in the
  TaskSpec-id space, resolved to sibling tickets via the shared ancestor idea's
  descendant tree — a *separate* id-space from real `Ticket.id`s), `spent_usd`
  (reuses the existing `cost_ledger` sum query), and `profile_at_capacity`/
  `repo_at_capacity` (new `ticket_repository` count helpers compared against the
  registry). New whitelist transition `escalated -> ready` (human-only guard,
  mirroring the existing `escalated -> in_progress`/`escalated -> planning` guards)
  — "requeue for reassignment," distinct from `bounced -> in_progress`'s "restart
  with the same agent immediately." New `EventKind.ASSIGNMENT` + migration. Added
  `TaskSpec.repo` (defaulted, so no existing construction site breaks) to
  `packages/schemas`. Fixed a pre-existing `llm_router` gap: no `claude-sonnet-5`
  pricing entry existed (only haiku/opus were priced) — added it plus a new
  `"delivery-manager"` role, since the Delivery Manager is the first caller that
  needs sonnet pricing. New `apps/orchestrator/src/orchestrator/agents/
  delivery_manager.py`: single-node LangGraph (mirrors `agents/planner.py`'s exact
  shape, no `PostgresSaver` checkpointing yet — still nothing to resume across with
  one node) that makes ONE sonnet call per invocation for the WHOLE `ready` queue at
  once, matching the pre-existing `prompts/delivery-manager.md` (v0.1, discovered
  already drafted, not written by this task) batch input/output contract — not one
  call per task, since the prompt itself asks for cross-task prioritisation.
  Eligible profiles (registry membership + not-at-capacity) are computed in Python
  *before* the LLM call, so the model can never even see an ineligible option; a
  task with zero eligible profiles skips the LLM call entirely and is recorded
  `human_only`. Every decision (`assigned`/`refused`/`deferred`/`human_only`) is
  recorded as a `kind=assignment` event with the model's reason and the profiles
  considered. New web view ("Assignments") listing `ready` tasks plus a live
  per-profile utilisation table, backed by a new `GET /capability-registry/
  utilisation` endpoint.
- Design decisions worth flagging: "sandbox available" is treated as identical to
  "profile at `max_parallel` capacity" — the architecture doesn't document a
  separately-sized shared sandbox pool distinct from per-profile concurrency, so a
  second parallel capacity subsystem wasn't invented for a distinction the docs
  don't actually draw. The batch LLM call's entire cost is attributed to the first
  considered ready task's `agent_run` (not proportionally split across every
  considered task) — `agent_runs` has no "not tied to one ticket" concept; a real
  limitation to revisit if a batch/session concept is ever added, not a real
  multi-ticket cost model. The DM's own capacity snapshot (fetched once per
  invocation, before any of its own transitions land) can go stale mid-batch; the
  API's live, real-time capacity check is what actually catches a same-batch race
  (proven by `apps/orchestrator/tests/integration/test_delivery_manager_agent.py`'s
  capacity test, which the DM handles as an ordinary refused-not-crashed outcome).
- Files touched: `capability_registry.yaml` (new),
  `apps/api/src/api/capability_registry.py` (new),
  `apps/orchestrator/src/orchestrator/capability_registry.py` (new),
  `apps/api/pyproject.toml` (+pyyaml), `packages/schemas/src/schemas/models.py`
  (`TaskSpec.repo`, +tests), `apps/api/src/api/domain/state_machine.py` (new
  `TransitionRequest` fields, `escalated -> ready`, extended `ready -> in_progress`
  guard, +tests), `apps/api/src/api/db/models.py` (`EventKind.ASSIGNMENT`) +
  migration, `apps/api/src/api/repositories/ticket_repository.py` (new count/
  ancestor helpers), `apps/api/src/api/services/ticket_service.py` (`_deps_done`,
  `_spent_usd`, `_capacity_fields`), `apps/api/src/api/contracts.py`
  (`assignee_agent`, `ProfileUtilisationOut`/`UtilisationOut`),
  `apps/api/src/api/routers/{tickets.py,capability_registry.py}` (new router),
  `apps/api/src/api/main.py`, `apps/api/tests/integration/
  test_delivery_manager_gates.py` (new, 5 tests),
  `packages/llm_router/src/llm_router/__init__.py` (`delivery-manager` role, sonnet
  pricing, +test), `apps/orchestrator/src/orchestrator/api_client.py`
  (`list_tickets`, `utilisation`, `transition(assignee_agent=...)`),
  `apps/orchestrator/src/orchestrator/agents/delivery_manager.py` (new),
  `apps/orchestrator/tests/integration/test_delivery_manager_agent.py` (new, 4
  tests against a real Postgres + API), `apps/orchestrator/tests/integration/
  conftest.py` (+`AUTH_DEV_MODE`/`SESSION_JWT_SECRET` env, needed for dev-login in
  these new tests), `apps/web/src/{App.tsx, assignments/AssignmentQueuePage.tsx,
  api/{client.ts,queries.ts,types.ts}}`, `docs/03-state-machine.md`.
- Test evidence: `apps/api` full suite green (93/93) including 5 new gate/
  integration tests and 4 new `state_machine.py` unit tests, against a real
  Postgres testcontainer; ruff/mypy clean. `apps/orchestrator` full suite green
  (49/49) including 4 new `test_delivery_manager_agent.py` tests run for real
  against a live Postgres + uvicorn `apps/api` instance (not mocked, only the LLM
  call is faked) — covers the dependency gate, the capacity pre-filter (asserts the
  LLM is never even called when no profile is eligible), the over-budget
  reassignment refusal, and the assignment-event audit trail; ruff/mypy clean.
  `packages/schemas` and `packages/llm_router` suites green. `apps/web`:
  `npm run typecheck`, `npm run lint`, and the existing Vitest suite all clean.
- Notes / follow-ups: The web Assignments view was verified via typecheck/lint/unit
  tests, not a live browser session (no dedicated component/e2e test was added,
  matching T-103's `PlanningReviewPage` precedent — this repo has no e2e coverage
  for planning/assignment views yet, only `board`/`smoke`). T-105 (specialised
  dev-agent profiles) is now unblocked and is where real skill-matching across
  multiple profiles starts to matter — today's single seeded profile makes the DM's
  model choice trivial by construction.

## T-105 · Specialised dev-agent profiles — 2026-07-06
- What changed: `capability_registry.yaml` grows from T-104's single seeded
  `dev-generalist` to four real profiles — `dev-frontend`/`dev-backend`
  (`claude-sonnet-5`, skills `[frontend]`/`[backend]`) and `dev-devops`
  (`claude-opus-4-8`, skills `[devops]`, on the theory that infra/CI reasoning
  benefits from the stronger model). Added `TaskSpec.required_skills: list[str] =
  []` (`packages/schemas`, additive/default-safe) and bumped `prompts/planner.md`
  v0.2 → v0.3 to have the Planner tag each task's domain
  (`frontend`/`backend`/`devops`/`general`). Split
  `apps/orchestrator/agents/delivery_manager.py`'s single-stage
  `_eligible_profile_ids` into two stages: `_skill_matching_profile_ids` (a task's
  `required_skills` intersected against each profile's `skills`; empty matches any
  profile, so today's untagged tasks keep working) runs *before* the existing
  capacity filter and before the LLM ever sees the task — a skill-mismatched task
  now gets its own `human_only` reason ("no profile has the required skills"),
  distinct from the pre-existing capacity-exhaustion reason ("no eligible profile
  has free capacity"), and never reaches the batch prompt at all. `DevAgentConfig.
  model_for(complexity, profile=None)` now prefers the assigned profile's own
  `model` field over the legacy complexity-only `_MODEL_BY_COMPLEXITY` map — except
  `complexity=high`, which always escalates to opus regardless of profile (an
  unconditional safety floor, not something a profile can downgrade).
  `run_dev_agent(..., profile=None)` threads it through; `profile=None` (every
  existing caller, including `run_pilot.py`) preserves the exact legacy behavior.
  `FixtureClaudeCodeRunner` (test-only) gained `last_model` alongside its existing
  `last_prompt`, so tests can assert which model actually reached the runner.
- Real gap found and closed while implementing this, not merely inherited: nothing
  in `run_delivery_manager_agent` validated that the LLM's proposed profile was
  actually in the eligible set it computed before calling `api.transition(...)`.
  For pure capacity-based eligibility (T-104) this was harmless — `apps/api`'s own
  capacity gate is a real hard backstop that would catch ANY over-capacity
  proposal regardless of profile. But skill-match has no such `apps/api` gate (see
  disclosed non-goal below), so a profile with free capacity but the wrong skills
  — e.g. the LLM hallucinating `dev-backend` for a frontend-tagged task — would
  have sailed straight through unchecked. Fixed by rejecting (as an ordinary
  "refused" outcome, not a crash) any proposed profile not in that task's own
  computed eligible set, before ever calling `transition()` — proven by
  `test_frontend_tagged_task_is_never_proposed_to_a_non_matching_profile`, where
  the fake LLM deliberately proposes the wrong profile and the ticket stays
  `ready`, never actually assigned to it.
- Files touched: `capability_registry.yaml` (+3 profiles),
  `packages/schemas/src/schemas/models.py` (`TaskSpec.required_skills`, +tests),
  `prompts/planner.md` (v0.2 → v0.3), `apps/orchestrator/src/orchestrator/
  agents/delivery_manager.py` (skill-match stage + eligible-set validation before
  `transition()`), `apps/orchestrator/src/orchestrator/config.py`
  (`DevAgentConfig.model_for` profile branch), `apps/orchestrator/src/orchestrator/
  agents/dev.py` (`run_dev_agent(profile=...)`), `apps/orchestrator/src/
  orchestrator/fixture_runner.py` (`last_model`), `apps/orchestrator/tests/
  test_config.py` (new), `apps/orchestrator/tests/integration/
  test_dev_agent.py` (+1 test), `apps/orchestrator/tests/integration/
  test_delivery_manager_agent.py` (+3 tests, 1 redesigned, "considered"
  assertions updated for the 4-profile registry), `docs/04-agent-specs.md`,
  `docs/02-data-model.md` (drive-by fix: T-104's `assignment` event kind was
  never added to this doc's enum list).
- Test evidence: `packages/schemas` 20/20. `apps/orchestrator` full suite green
  (55/55, up from 49 — 3 new integration tests, 1 redesigned, 3 new unit tests)
  against a real Postgres + live `apps/api`, LLM mocked; ruff/mypy clean.
  `apps/api` 93/93 unchanged (no source changes there; confirmed no regression
  from the richer registry — its own gate tests POST `assignee_agent=
  "dev-generalist"` directly and never depend on how many other profiles exist).
  Full real re-run of the 15-case planner golden set after the v0.3 prompt bump:
  15/15 valid plans, zero errors, avg score 89.6 against `floor: 70` — consistent
  with T-103's original 88.6–89.2 baseline, no regression from adding
  `required_skills` to the output shape.
- Notes / follow-ups: All four profiles still point at the one existing sandbox
  image — real per-profile base images (new Dockerfiles, CI build steps) is
  orthogonal infra work, deliberately deferred until a profile genuinely needs
  different tooling, not spec'd speculatively here. Skill-match stays a
  Delivery-Manager-side routing filter, not a hard `apps/api` gate like budget/
  deps/capacity — a deliberate scope boundary (disclosed, not silently assumed),
  with the DM's own eligible-set validation (above) as its real backstop. No
  auto-dispatch loop exists connecting a DM assignment to a real `run_dev_agent`
  invocation; `run_pilot.py` is unchanged and still the only real (non-test)
  caller of `run_dev_agent`, calling it with `profile=None` — an already-disclosed
  gap from earlier tasks that this one doesn't attempt to close.

## T-106 · Review agent + in_review gate — 2026-07-06
- What changed: `in_review` was a true no-op before this task —
  `apps/orchestrator/agents/dev.py` transitioned straight through it to `in_qa`
  with zero enforcement, and `state_machine.py` had no guard at all for
  `IN_REVIEW → IN_QA` (any actor could request it). New
  `apps/orchestrator/src/orchestrator/agents/review.py`: single-node LangGraph
  (mirrors `planner.py`/`delivery_manager.py`'s exact shape, no
  `PostgresSaver` checkpointing yet) that fetches a PR diff
  (`GitHubClient.get_pr_diff`, new method) and calls `llm_router.route(role=
  "review", ...)` against the pre-existing, unedited `prompts/review-agent.md`
  (v0.1), parsing a new `ReviewResult` (`verdict: approve|block`,
  `comments: ReviewComment[]`, `scope_violations: list[str]`). On approve:
  posts a PR comment (`GitHubClient.post_comment`, new method), transitions
  the ticket to `in_qa`. On block: posts the comments, transitions to
  `bounced` (bounce_count shared with QA failures — same counter, same
  `MAX_BOUNCES=3` escalation). `agents/dev.py`'s job now genuinely ends at
  opening the PR — the automatic `to_state="in_qa"` line right after
  `to_state="in_review"` is gone. `apps/api`'s `state_machine.py` gained two
  real guards: `IN_REVIEW → IN_QA` now requires a review-agent or human actor
  (closing the exact gap above), and a new `BOUNCED → IN_QA` human-only edge —
  the override path for a review-block a human disagrees with (records an
  `Approval(gate=review)` row via the existing `/tickets/{id}/approve`
  endpoint, reusing the same two-call pattern T-103 established for budget
  approval; no new router/service code needed). New `EventKind.REVIEW` +
  `ApprovalGate.REVIEW` + one migration adding both enum values.
- Eval seeding (SPEC-105 AC5): 8 real cases under `evals/review/cases/` (4
  clean: health endpoint, widget CRUD, bugfix, refactor; 4 planted-defect:
  out-of-scope file edit, missing test for an AC, hardcoded API key, a
  swallowed-exception correctness smell) + new `review_scorer.py` (invokes
  the Review agent directly via `llm_router`, like `planner_scorer.py` does —
  no repo cloning needed since review judges a *given* diff, not one it
  produces) + `runner.py` wiring (`_SCORABLE_SETS`, `run_review_set`,
  `--only-changed` map). **Left genuinely unverified, disclosed not hidden**:
  every attempt to actually run the set against live Anthropic in this
  environment returned 400 "credit balance is too low" (same billing
  exhaustion that hit T-105's CI eval-gate run). The scorer's wiring is
  confirmed correct — it runs, parses, and blends deterministic+judge scores
  properly, and fails gracefully (score 0, no crash) on the API error, same
  as every other scorer's error-handling convention — but no real passing
  run exists behind `evals/thresholds.yaml`'s `review.floor: 70`. Presented
  the user a choice (wait for credits / leave `not_yet_enforced: true` /
  enable anyway with an unverified floor); the user explicitly chose to
  enable enforcement anyway. `evals/thresholds.yaml`'s `review` rationale
  spells this out in full and flags it as a required follow-up for whoever
  next touches `prompts/review-agent.md`.
- Files touched: `packages/schemas/src/schemas/models.py`
  (`ReviewComment`/`ReviewResult`, +tests), `packages/llm_router/src/
  llm_router/__init__.py` (`"review"` role, +test),
  `apps/api/src/api/db/models.py` (`EventKind.REVIEW`,
  `ApprovalGate.REVIEW`) + migration,
  `apps/api/src/api/domain/state_machine.py` (two new guards, +2 unit
  tests), `apps/api/tests/integration/test_review_gate.py` (new, 3 tests),
  `apps/orchestrator/src/orchestrator/github_client.py`
  (`get_pr_diff`/`post_comment`), `apps/orchestrator/src/orchestrator/
  agents/review.py` (new), `apps/orchestrator/src/orchestrator/agents/
  dev.py` (stops at `in_review`), `apps/orchestrator/tests/integration/
  test_dev_agent.py` (updated final-state assertion + 1 new test from
  T-105, untouched here), `apps/orchestrator/tests/integration/
  test_review_agent.py` (new, 4 tests), `apps/orchestrator/tests/
  integration/test_delivery_manager_agent.py` (`_finish_task` helper
  fixed — its `in_review → in_qa` step needed an explicit review/human
  actor once the new guard landed), `apps/orchestrator/src/orchestrator/
  evals/{loader.py, review_scorer.py, runner.py, judge.py}`,
  `evals/review/cases/*.yaml` (new, 8 cases), `evals/thresholds.yaml`,
  `docs/{02-data-model.md, 03-state-machine.md, 04-agent-specs.md}`.
- Test evidence: `packages/schemas` 22/22. `packages/llm_router` 6/6.
  `apps/api` 98/98 (5 new: 2 state-machine unit tests + 3 review-gate
  integration tests) against a real Postgres testcontainer; ruff/mypy
  clean. `apps/orchestrator` 60/60 (4 new integration tests in
  `test_review_agent.py`, 1 updated assertion, 1 loader test updated + 1
  new) against a real Postgres + live `apps/api`, LLM mocked; ruff/mypy
  clean. `apps/web`: no code changes; `npm run typecheck`/`lint` not
  re-verified this task since nothing on the wire format changed (Review
  agent has no web surface yet — no board button for the override, per
  the plan's non-goals).
- Notes / follow-ups: **AC5's floor is unverified — re-run the real eval once
  API credits are available** (see thresholds.yaml). No real Semgrep
  integration — `semgrep_findings` is an injectable string parameter;
  CI already runs Semgrep (`agent-pr-gate.yml`) but nothing parses its
  output back into the agent yet. No auto-dispatch connects a ticket's
  arrival at `in_review` to an automatic `run_review_agent` invocation,
  matching the same disclosed gap as every other agent in this repo. No
  board UI for the human-override button — exercised via the existing
  `/tickets/{id}/approve` + `/tickets/{id}/transition` endpoints only, same
  as every gate before a board button existed for it.

## T-107 · Merge queue + parallelism — 2026-07-06
- What changed: `in_qa -> done` was a bare state flip before this task —
  `webhook_service.handle_ci_result`'s success path transitioned straight to
  `done` with zero git operation; `docs/03-state-machine.md`'s own
  "merge-queue slot acquired" guard text had no code behind it. New
  `merge_queue_entries` table (`queued`/`merged`/`conflict`,
  `MergeQueueStatus`) — CI-green now only creates a `queued` row
  (`ticket_service.enqueue_for_merge`); the ticket stays `in_qa`. New
  `apps/orchestrator/src/orchestrator/merge_queue.py`: a callable entry point
  (`run_merge_queue`, no auto-dispatch — matches Planner/Delivery
  Manager/dev agent/Review agent's own precedent) that processes one repo's
  queued entries strictly in FIFO order — the ordering itself is the
  serialization, no locking primitive needed since the orchestrator drives
  entries one at a time. Per entry: fresh clone of `agent/{ticket_id}`
  (matching `agents/dev.py`'s own branch-naming convention), a REAL
  `git_ops.rebase_onto()` (new — the one `git_ops` function that deliberately
  does NOT raise on a non-zero git exit, since a conflict is an expected
  outcome, not a bug) onto the target branch. Success: force-push + a new
  `GitHubClient.merge_pr()` (new method, alongside `get_pr_for_branch`),
  `apps/api`'s `IN_QA -> DONE` guard now genuinely requires a `has_merged_
  queue_entry` (a new service-computed `TransitionRequest` field, same
  pattern as every other gate since T-102). Conflict: aborts the rebase,
  reports the real conflicting paths (`git diff --name-only
  --diff-filter=U`), records a `FailureReport(failing_suite="conflict",
  suspect_files=<conflicting paths>)` and bounces — bounce_count shared with
  QA failures, reusing `FailureReport`'s generic fields exactly like T-106's
  `failing_suite="review"` precedent (no schema change needed). AC2's audit
  query (`ticket_repository.tickets_done_without_merge_queue_entry`) proves
  the invariant holds by joining `tickets(state=done)` against
  `merge_queue_entries(status=merged)`.
- Two real, pre-existing bugs found and fixed while building the tests that
  actually exercise these mechanisms for the first time (both are latent gaps
  from earlier tasks, not introduced here):
  1. `ticket_repository.count_in_progress_by_repo` (T-104) matched
     `Ticket.spec["repo"]` literally — a ticket with no `spec` at all (the
     common case; most tickets in this repo's own test suite) was invisible
     to the query, since Postgres JSONB path access on a NULL column returns
     NULL, not a match, silently undercounting to zero. This meant the
     `repo_concurrency_limit` gate (AC3, `capability_registry.yaml`) never
     actually fired for any ticket without an explicit `spec.repo` — writing
     the first real "5 ready tickets, exactly 3 succeed" integration test
     (rather than a unit test with a mocked bool) is what surfaced it. Fixed
     with `COALESCE(Ticket.spec["repo"].astext, DEFAULT_REPO)`, matching
     `ticket_service._capacity_fields`'s own existing fallback logic exactly.
  2. `shutil.rmtree(scratch, ignore_errors=True)` silently left git's
     read-only object files behind on Windows instead of actually removing
     them or raising — the "zero orphaned scratch directories" load-test
     assertion caught this immediately. Fixed with an `onexc` callback
     (`os.chmod(path, stat.S_IWRITE)` then retry), a well-known Windows
     git-cleanup workaround.
- Files touched: `apps/api/src/api/db/models.py` (`MergeQueueStatus`,
  `MergeQueueEntry`) + migration, `apps/api/src/api/repositories/
  ticket_repository.py` (merge-queue CRUD + the audit query + the
  `count_in_progress_by_repo` COALESCE fix), `apps/api/src/api/services/
  {ticket_service.py, webhook_service.py}`, `apps/api/src/api/domain/
  state_machine.py` (+2 unit tests), `apps/api/src/api/{contracts.py,
  routers/merge_queue.py, main.py}` (new router), `apps/api/tests/
  integration/{test_merge_queue_api.py (new, 4 tests), test_tickets_api.py
  (`_complete_via_merge_queue` helper), test_ci_webhook_api.py,
  test_dashboard_api.py, test_delivery_manager_gates.py,
  test_migration_replay.py}` (all updated to route through the real
  merge-queue endpoints instead of a direct `done` transition),
  `apps/orchestrator/src/orchestrator/{git_ops.py (`rebase_onto`,
  `force_push`, `clone_branch`), github_client.py (`merge_pr`,
  `get_pr_for_branch`, + `FakeGitHubClient`'s real-git-push simulation),
  api_client.py, merge_queue.py (new)}`, `apps/orchestrator/tests/
  integration/{test_merge_queue.py (new, 2 tests), test_delivery_manager_
  agent.py (`_finish_task` now drives the real CI-webhook + merge-queue
  path)}`, `docs/{02-data-model.md, 03-state-machine.md,
  06-tech-stack.md}`.
- Test evidence: `apps/api` 103/103, up from 98 (5 new: 1 state-machine unit
  test + 4 in the new `test_merge_queue_api.py`; several existing tests in
  `test_ci_webhook_api.py`/`test_dashboard_api.py`/
  `test_delivery_manager_gates.py`/`test_migration_replay.py`/
  `test_tickets_api.py` updated to route through the real merge-queue
  endpoints instead of a direct `done` transition) against a real Postgres
  testcontainer; ruff/mypy clean. `apps/orchestrator` 62/62 (2 new
  `test_merge_queue.py` tests using REAL local git fixture repos — no
  mocked git, no real GitHub) against a real Postgres + live `apps/api`;
  ruff/mypy clean. `packages/schemas`, `packages/llm_router` unaffected
  (22/22, 6/6). `apps/web`: no code changes; not re-verified this task (no
  wire-format change).
- Notes / follow-ups: **Part B (real infra) deliberately not attempted** —
  Terraform/Ansible for a second self-hosted GitHub Actions runner VM, and a
  real Grafana queue-wait-time dashboard, both require real cloud
  credentials and a real Grafana instance this dev environment doesn't
  have. The user was shown this split explicitly before implementation
  began (software mechanism vs. infra deliverables) and chose to scope this
  PR to the mechanism only — the infra half is logged as a future follow-up,
  not silently dropped, matching how T-105 deferred real sandbox images and
  T-106 deferred real Semgrep integration. Not using GitHub's native
  merge-queue feature or a bors-style bot (needs GitHub org/repo admin
  configuration this session has no reason to assume exists) — the
  orchestrator's own FIFO processor is the disclosed substitute. AC3's
  "sandboxes" is interpreted as "concurrently in_progress tickets on one
  repo" (the existing T-104 mechanism), not literal Docker containers —
  `apps/sandbox` still isn't wired into the dev-agent path at all (T-105's
  own disclosed gap), closing that is separate work. No auto-dispatch loop
  invokes `run_merge_queue` on a timer/webhook, matching every other agent
  in this repo.

## T-108 · Cost ledger v2 — 2026-07-08
- What changed: the core cost plumbing (`agent_runs`, `cost_ledger`,
  per-ticket cost summary, drawer budget bar, org-wide dashboard metrics) was
  already real from T-001/T-008/T-102-104 — this task closed the three gaps
  actually asked for. **AC1 (idea rollup):** new
  `GET /tickets/{id}/cost-rollup` sums `cost_ledger` over a ticket and every
  descendant, reusing `ticket_repository.get_descendants` (BFS over
  `parent_id`, already used by budget/capacity checks) — the drawer's budget
  bar only ever showed a single ticket's spend before this. **AC2
  (spend-by-profile / spend-by-prompt-version):** this was actually promised
  in SPEC-006 ("org-level spend by model & agent role") but never built.
  Closed via two real gaps: `agents/dev.py`'s `run_dev_agent` hardcoded
  `agent_role="dev"` even when a `Profile` was passed in (dev-frontend/
  backend/devops/generalist from T-105) — it now uses `profile.id`, so
  `agent_runs.agent_role` doubles as the "profile" dimension; and a new
  `agent_runs.prompt_version` column (nullable, new migration) is now
  populated by every orchestrator agent (dev/planner/review/delivery-manager)
  parsing its own prompt file's `# ... · vX.Y` header via a `parse_prompt_
  version` helper extracted out of `evals/langfuse_client.py` into a neutral
  `orchestrator/prompt_version.py` (agents importing from `evals/` would have
  been backwards layering). New `GET /dashboard/spend-by-profile` and
  `GET /dashboard/spend-by-prompt-version` group `cost_ledger` by
  `agent_runs.agent_role`/`prompt_version` via a join; `DashboardPage.tsx`
  renders both as simple horizontal bar-list charts, matching the existing
  budget-bar visual style (no new charting dependency). **AC3 (eval
  exclusion):** confirmed already true by construction — the eval harness
  (`apps/orchestrator/.../evals/`) calls `llm_router.route()` directly with
  no `ticket_id` and never imports the ticket API client or agent-run
  repository, so there's no code path for an eval run to write cost. Added a
  structural regression test (AST-parses every `evals/*.py` file's imports)
  instead of an integration test that would actually invoke a real LLM
  call — this environment has repeatedly hit Anthropic API credit exhaustion
  on real eval runs (T-105/T-106), so a DB-round-trip test here would be
  flaky for reasons unrelated to the invariant being proven.
- Files touched: `apps/api/src/api/db/models.py` (`AgentRun.prompt_version`)
  + migration, `apps/api/src/api/repositories/{agent_run_repository.py
  (`sum_cost_ledger_for_tickets`), dashboard_repository.py
  (`sum_cost_ledger_by_agent_role`, `sum_cost_ledger_by_prompt_version`)}`,
  `apps/api/src/api/services/{agent_run_service.py (`cost_rollup`),
  dashboard_service.py (`spend_by_profile`, `spend_by_prompt_version`)}`,
  `apps/api/src/api/{contracts.py (`CostRollupOut`, `SpendBreakdownOut`),
  routers/{agent_runs.py, dashboard.py}}`, `apps/api/tests/integration/
  {test_cost_rollup_api.py (new, 4 tests), test_dashboard_api.py (+1 golden
  test)}`, `apps/orchestrator/src/orchestrator/{prompt_version.py (new),
  evals/langfuse_client.py (re-exports from the new module),
  agents/{dev.py, planner.py, review.py, delivery_manager.py}, api_client.py}`,
  `apps/orchestrator/tests/{integration/test_dev_agent.py (+1 test),
  evals/test_cost_isolation.py (new)}`, `apps/web/src/{api/{client.ts,
  queries.ts, types.ts}, board/TicketDrawer.tsx, dashboard/DashboardPage.tsx}`,
  `docs/02-data-model.md`.
- Test evidence: `apps/api` 108/108, up from 103 (4 new in
  `test_cost_rollup_api.py`, 1 new golden fixture test in
  `test_dashboard_api.py`) against a real Postgres testcontainer; ruff/mypy
  clean. `apps/orchestrator` 64/64, up from 62 (1 new `test_dev_agent.py`
  case proving `agent_role`/`prompt_version` land on the real row, 1 new
  structural `test_cost_isolation.py`) against a real Postgres + live
  `apps/api`; ruff/mypy clean. `apps/web`: `tsc -b --noEmit` clean, `eslint`
  clean (1 pre-existing unrelated warning in `AuthContext.tsx`), `vitest run`
  1/1 (no dedicated component tests existed for `TicketDrawer`/
  `DashboardPage` before this task, so none were extended — only the existing
  smoke test re-verified).
- Notes / follow-ups: none — no SPEC-107/108 file exists for this task
  (BACKLOG points at docs/02-data-model.md directly); doc updates landed in
  this PR per CLAUDE.md's "schema changes need a doc update in the same PR"
  rule rather than a separate spec.

## T-109 · End-to-end management flow test — 2026-07-08
- What changed: every agent (planner, DM, dev, review, merge-queue) already
  had its own real integration test against a live `apps/api`, but nothing
  chained more than one together — `test_delivery_manager_agent.py`'s own
  `_finish_task` helper explicitly faked the rest of the pipeline via direct
  API transitions instead of calling `run_review_agent`/`run_merge_queue`.
  New `apps/orchestrator/tests/integration/test_e2e_management_flow.py`
  drives the real chain once: creates an idea, transitions it to `planning`,
  runs the real `run_planner_agent` (mocked `route()`, same pattern as
  `test_planner_agent.py`) against a canned two-task plan (one
  `required_skills=["frontend"]`, one `["backend"]`); approves the idea's
  budget for real (`POST /tickets/{id}/approve` gate=budget) and transitions
  it to `ready`, cascading the epic/tasks; runs the real
  `run_delivery_manager_agent` (mocked `route()`) which assigns each task to
  its one skill-eligible profile; then runs **two real `run_dev_agent` calls
  genuinely concurrently** via `ThreadPoolExecutor` (new test infra — every
  existing test called agents strictly sequentially) against two clones of
  one shared bare-origin fixture repo seeded with two files
  (`frontend.py`/`backend.py`, so the branches never conflict), each dev
  agent replaying its own canned `FixtureClaudeCodeRunner` transcript (new
  fixtures: `apps/orchestrator/fixtures/e2e_{frontend,backend}_task/`); runs
  two real `run_review_agent` calls (mocked `route()`, approve verdict,
  per-task diff swapped onto one shared `FakeGitHubClient`); reports CI
  success for both (enqueuing both for merge); then one real
  `run_merge_queue` call (unmodified, no LLM involved) merges both — disjoint
  files, no conflict — to `done`. New `orchestrator.config.
  scenario_cost_cap_usd()` (env-overridable `SCENARIO_COST_CAP_USD`, default
  $1.00) plus a new `ApiClient.cost_rollup()` wrapper (mirrors the existing
  `cost_summary` method) checks the whole idea tree's real summed cost via
  T-108's `GET /tickets/{id}/cost-rollup` stays under the cap. Every LLM call
  in the whole scenario is mocked or fixture-replayed — real Anthropic spend
  is $0 — so a nightly run can never fail on provider billing exhaustion
  instead of a real regression, a real recurring problem on this project's
  eval runs (T-105/T-106). New `.github/workflows/nightly-e2e.yml`
  (`schedule: cron "0 3 * * *"` + `workflow_dispatch` for on-demand
  verification) runs just this one test file — no nightly/cron trigger
  existed anywhere in the repo before this.
- Files touched: `apps/orchestrator/src/orchestrator/{config.py
  (`scenario_cost_cap_usd`), api_client.py (`cost_rollup`)}`,
  `apps/orchestrator/fixtures/e2e_{frontend,backend}_task/{transcript.jsonl,
  workspace_diff/}` (new), `apps/orchestrator/tests/integration/
  test_e2e_management_flow.py` (new), `.github/workflows/nightly-e2e.yml`
  (new), `docs/04-agent-specs.md` (pointer note, no schema change).
- Test evidence: `apps/orchestrator` 65/65, up from 64 (1 new scenario test,
  full suite re-run to confirm no ordering/residue interference with the
  existing DM/merge-queue tests that share one session-wide Postgres)
  against a real Postgres + live `apps/api` + real local git; ruff/mypy
  clean. The new nightly workflow itself is `workflow_dispatch`-triggerable
  for on-demand verification in CI, since a live 03:00 UTC cron firing can't
  be observed from this dev session. `apps/api`: unaffected by this task
  (no api-side code changes beyond what T-108 already shipped and merged);
  not re-verified here.
- Notes / follow-ups: `scripts/run_pilot.py` (T-009, real-cost, real-GitHub,
  single-agent) was deliberately left alone — this scenario needed the
  opposite properties (cheap, deterministic, fully-chained) and reuses none
  of its machinery beyond the general "drive a ticket through the API"
  pattern every other agent test already follows.

## T-201 · Multi-tenancy core — 2026-07-08
- What changed: T-102 added `org_id` to every table and threaded it through
  every query via a single hardcoded `DEFAULT_ORG_ID` — real, but not
  multi-tenant. This task built the real thing: `org_members` (a user's role
  is per-org now, not global — replaces `users.role`/`users.org_id`),
  `org_invites` (owner-issued, token returned directly in the response since
  no email-sending exists in this system yet), `orgs.max_parallel_tickets`
  (the one quota that's actually enforceable — reuses
  `ticket_service._capacity_fields`'s exact existing pattern, a new
  `org_at_quota` field alongside `profile_at_capacity`/`repo_at_capacity`
  gating the same `ready -> in_progress` transition), and `staff_audit_log`
  (one row per impersonation start + one per page view while impersonating).
  `UserRole` was renamed `admin/approver/viewer` -> `owner/approver/member/
  viewer` — a real breaking change, not a parallel role system alongside the
  old one; every real call site fixed in this PR (~15 sites, grepped:
  `apps/api` src+tests, `apps/web`). The session JWT now carries a real
  `org_id` claim (`mint_session_token` gained an `org_id` param); a new
  `POST /auth/switch-org` re-authenticates an already-proven identity scoped
  to a different org they belong to (the org switcher). `/auth/callback`
  picks a login's org via the user's first membership (auto-joining the
  default org if they have none), not a full interactive "choose an org"
  flow — a real, disclosed scope trim (the org switcher covers switching
  *after* landing; only the very-first-OIDC-login-with-2+-orgs edge case is
  simplified). AC2's static gate
  (`scripts/check_tenant_scope_gate.py`) is a REAL AST walk — `ast.parse` +
  `ast.walk` over every top-level repository function, flagging any that
  call `session.execute/get/query` without ever referencing `org_id` — not a
  regex line-scan like `check_llm_router_gate.py` turned out to actually be
  on closer inspection (its own docs call it "AST-based"; it's `re.match`
  over `git ls-files`). Verified for real: found one genuine, correct
  allowlist candidate (`user_repository.get_user` — `users` is a global
  identity table now, not org-scoped) and, separately, confirmed it fails on
  a deliberately-broken repository function before being fixed. AC5's
  impersonation always mints `actor=f"staff:{email}"` (never `human:`), so
  `state_machine.is_human_actor()` correctly excludes impersonation sessions
  from every human-only gate (approve/reject etc.) by construction — "view
  as org" is read-mostly visibility, not a way to act as an org's owner.
- Two migrations, not one (a real, documented exception to "one migration
  per PR max" in docs/07-conventions.md): Postgres won't let a transaction
  USE an enum value it just `ADD VALUE`d, and each migration file is its own
  transaction — `b8c9d0e1f2a3` adds `owner`/`member` to the `user_role`
  enum; `c9d0e1f2a3b4` does everything else, including the backfill
  (`admin -> owner`, `approver`/`viewer` unchanged) that needs those new
  values to already be committed. Both round-trip tested for real against a
  throwaway Postgres container: fresh `upgrade head`, `downgrade -1`, then
  re-`upgrade head` with real pre-existing `admin`/`viewer` users inserted
  first — confirmed the backfill lands exactly right (`alice: admin ->
  owner`, `bob: viewer -> viewer`).
- Files touched: `apps/api/migrations/versions/{b8c9d0e1f2a3,
  c9d0e1f2a3b4}_*.py` (new), `apps/api/src/api/db/models.py` (`UserRole`
  rename, `Org.max_parallel_tickets`, `User` drops role/org_id gains
  `is_platform_staff`, new `OrgMember`/`OrgInvite`/`StaffAuditLog`),
  `apps/api/src/api/repositories/{user_repository.py (rewritten),
  org_repository.py (new), ticket_repository.py
  (count_in_progress_by_org)}`, `apps/api/src/api/services/{user_service.py
  (rewritten), org_service.py (new), ticket_service.py (_org_at_quota)}`,
  `apps/api/src/api/{auth.py (org_id/is_platform_staff/impersonating on
  ActorContext + mint_session_token), contracts.py (Org*/Invite* contracts,
  SessionOut gains org_id/is_platform_staff/impersonating), domain/
  state_machine.py (org_at_quota guard), routers/{auth.py (switch-org),
  tickets.py (admin->owner rename), orgs.py (new), admin.py (new)}, main.py
  (router registration)}`, `apps/api/tests/integration/
  {test_tenant_isolation.py, test_org_quota.py, test_staff_impersonation.py}
  (new, 7 tests total), test_user_service.py (rewritten), test_auth_api.py
  (admin->owner)`, `scripts/check_tenant_scope_gate.py` (new), `Makefile`
  (new `tenant-scope-gate` target, wired into `check`),
  `apps/web/src/{api/{client.ts, queries.ts}, auth/{AuthContext.tsx,
  LoginPage.tsx}, admin/ImpersonatePage.tsx (new), App.tsx (watermark + org
  switcher + staff entry point), board/TicketDrawer.tsx,
  planning/PlanningReviewPage.tsx}` (admin->owner renames + new org/
  impersonation UI), `apps/web/e2e/api.ts`, `docs/{02-data-model.md,
  07-conventions.md, 09-saas-model.md}`.
- Test evidence: `apps/api` 116/116, up from 109 (7 new: 3
  `test_tenant_isolation.py` covering AC1+AC4, 2 `test_org_quota.py`
  covering AC3, 2 `test_staff_impersonation.py` covering AC5; every
  existing test using the string `"admin"` for a role updated to `"owner"`)
  against a real Postgres testcontainer; ruff/mypy clean.
  `scripts/check_tenant_scope_gate.py` verified for real (found a genuine
  allowlist case, caught a deliberately-broken function, passes clean on
  the real repo) and wired into `make check`. `apps/orchestrator` 65/65,
  fully unaffected (no code changes there — it stays single-org, disclosed
  above). `apps/web`: `tsc -b --noEmit` clean, `eslint` clean (1
  pre-existing unrelated warning), `vitest run` 1/1.
- Notes / follow-ups: sandbox-minutes/day and storage quotas from SPEC-201's
  wording are NOT implemented — `apps/sandbox` has no real usage metering to
  enforce against (T-105's own disclosed gap); adding config fields for an
  unenforceable quota would be dead config, not real work. The orchestrator/
  service-token path stays on `DEFAULT_ORG_ID` — real per-org agent dispatch
  is separate, larger work (arguably T-202/BYOK's territory, since keys are
  per-org). The Phase-2.5 "starts after T-110 go" gate was deliberately
  overridden by explicit human decision (T-110 is blocked on Anthropic
  credit, not completed) — noted in `tasks/BACKLOG.md`'s Phase-2.5 header,
  not silently skipped.
## T-110 · Phase-2 pilot & report — blocked, 2026-07-08
- What happened: before spending any real budget on 3-5 real ideas, ran a
  direct smoke-test call through `llm_router.route()` with the repo's
  configured `ANTHROPIC_API_KEY` — it returned
  `anthropic.BadRequestError: ... credit balance is too low to access the
  Anthropic API`, confirming the account has zero balance right now, not a
  transient failure. This is the same recurring billing-exhaustion issue
  that hit T-105/T-106's eval-gate CI runs, but here it blocks the task
  itself rather than a CI check, since T-110 requires real planner/dev/
  review LLM calls across 3-5 real ideas to produce a genuine go/no-go
  report — there was no funded fallback key and no prior real run to point
  to as evidence, so a fabricated report was never an option.
- Decision: presented the blocker plus three options (top up credits and
  retry; defer and move to other work; use a different funded key). Human
  chose to defer T-110 and move on to Phase-2.5 (T-201+) engineering work
  that doesn't need real LLM spend.
- Files touched: `tasks/BACKLOG.md` (T-110 marked `ready (blocked: no
  Anthropic credit)` with the full blocker + unblock instructions inline).
- Notes / follow-ups: T-110 stays open, unblock by topping up the Anthropic
  account (or supplying a funded key) and re-running the pilot for real —
  no code changes needed to start it once credit exists.
## T-202 · BYOK keys & provider router v1 — 2026-07-08
- What changed: `packages/llm_router` was a 105-line skeleton — a role→model
  map, one hard-coded Anthropic client using the ambient `ANTHROPIC_API_KEY`,
  no `org_id`, no fallback, no retries (its own docstring said so). This task
  built the real thing: `route(role, *, credentials, complexity, ...)` takes
  an ordered `list[ProviderCredential]` (the org's fallback order, already
  fetched by the caller — matches docs/09-saas-model.md's "fetched at run
  start, held in memory in the runner, passed to the router" line verbatim,
  a design already approved before this task), tries each in order with
  per-provider retries on transient failures, and returns a `RouteResult`
  carrying the real `provider` + a full `attempts` trail. A real second
  provider (OpenAI) was genuinely wired in, not simulated — `_call_anthropic`/
  `_call_openai` adapters, `_PROVIDER_ROLE_MODELS`/`_PRICING_PER_MILLION_
  TOKENS` both keyed by `(provider, model)` now. Real HashiCorp Vault
  (dev-mode) was added to `docker-compose.yml` — not a stub like T-105/106/
  107's infra deferrals, since Vault dev-mode is free/local/zero-billing-risk
  and `docs/06-tech-stack.md` already locked Vault in by name for this exact
  row. `apps/api/src/api/vault_client.py` wraps `hvac`'s KV v2 API at
  `tenants/<org_id>/llm/<provider>`. New `provider_keys` (audit-only
  metadata — last4/status/timestamps, NEVER the secret) and
  `provider_eval_opt_ins` tables; `orgs.llm_fallback_order` (a JSON column,
  not a new ordering table — same judgment as `max_parallel_tickets`);
  `agent_runs.provider`/`cost_ledger.provider` are dynamic now instead of
  `agent_run_repository.complete_agent_run`'s old hard-coded `"anthropic"`
  literal. New `apps/api/src/api/routers/provider_keys.py` (owner-gated CRUD
  + fallback-order + health-check, plus a service-principal-only
  `GET /orgs/{id}/llm/runtime-keys` returning real key material — the one
  route deliberately excluded from any future request/response logging) and
  `routers/eval_floors.py` (AC5's badge + opt-in). `evals/thresholds.yaml`
  gained a `providers:` sub-map per role — anthropic mirrors the existing
  floor, openai ships `floor: null, not_yet_enforced: true` with an honest
  rationale (no OpenAI credits in this environment, same disclosed pattern
  as the `review` set's own precedent). `apps/api/src/api/eval_floors.py`
  reads that YAML directly (not via `orchestrator.evals.loader` — wrong
  dependency direction between two separate deployables) and treats a role
  with NO eval-floor entry at all (e.g. `delivery-manager`, which has no
  golden set) as never-gated, distinct from a role that has a floor but this
  provider isn't verified for it — a real bug caught by the orchestrator
  integration suite (the DM's dispatch gate was refusing every batch call
  until this distinction was added). New `orchestrator/dispatch_gate.py` is
  the shared "fetch credentials, check the eval floor, refuse if neither
  verified nor opted-in" gate every LLM-calling agent entry point
  (planner/delivery-manager/review/dev) now calls before `route()`/
  `claude_runner.run()` — never a background pause, a same-request check, so
  AC6's "paused within 60s" is satisfied by construction (every dispatch
  re-fetches fresh; there's no cache to go stale). `claude_runner.py`'s
  `SubprocessClaudeCodeRunner.run()` gained `anthropic_api_key: str | None`,
  building `env={**os.environ, "ANTHROPIC_API_KEY": key}` for the CLI
  subprocess when set — the key never reaches argv or a `TranscriptEvent`
  payload, only `Popen`'s `env=`; `None` preserves the exact pre-BYOK
  ambient-inheritance behavior for every existing test/pilot-script caller.
  An org with zero configured `ProviderKey` rows at all falls back to the
  platform's own `ANTHROPIC_API_KEY` (`provider_key_service.
  resolve_runtime_credentials`) — the pre-BYOK behavior, unchanged, so every
  existing test/pilot script needed zero BYOK setup; this fallback stops the
  instant an org configures its own key (`ACTIVE` or `REVOKED` both count),
  so AC6's "delete pauses, it doesn't silently fall back" still holds once
  BYOK is actually in use. Key hygiene: `packages/schemas/redaction.py`'s
  `scrub`/`scrub_payload` (regex-based, Anthropic/OpenAI key shapes) is
  applied once at `ticket_repository.append_event` — the single choke point
  every one of the 7 service-layer event-write call sites already funnels
  through — plus a belt-and-suspenders scrub at `orchestrator.api_client.
  append_event` before an event body ever leaves that process. The
  validate-on-save ping (`provider_key_service.validate_key`, a cheap
  `models.list()`-shaped call, never a completion call) is a disclosed,
  narrow, allowlisted exception to "provider SDKs live only in
  `packages/llm_router`" — `scripts/check_llm_router_gate.py` gained a small
  `_ALLOWLISTED_FILES` set for exactly this one file, with the reasoning
  inline in both files' docstrings; verified for real (allowlist emptied ->
  the gate correctly flags both `import anthropic`/`import openai` lines;
  restored -> passes clean).
- Files touched: `docker-compose.yml`/`.env.example` (vault service + env
  vars), `apps/api/migrations/versions/d1e2f3a4b5c6_*.py` (new, one
  migration — `provider_keys`, `provider_eval_opt_ins`,
  `orgs.llm_fallback_order`, `agent_runs.provider`), `apps/api/src/api/
  {db/models.py (ProviderKey/ProviderKeyStatus/ProviderEvalOptIn), vault_
  client.py (new), eval_floors.py (new), repositories/{provider_key_
  repository.py, provider_eval_opt_in_repository.py} (new), agent_run_
  repository.py (dynamic provider param), ticket_repository.py (scrub at
  append_event), services/{provider_key_service.py, provider_health_
  service.py, eval_floors_service.py} (new), agent_run_service.py (provider
  param), routers/{provider_keys.py, eval_floors.py} (new), agent_runs.py
  (provider param), contracts.py (new Provider*/EvalFloor* contracts,
  TicketOut.org_id, AgentRunOut.provider), main.py (router registration)}`,
  `packages/llm_router/src/llm_router/__init__.py` (full redesign) +
  `pyproject.toml` (+openai, +respx dev), `packages/schemas/src/schemas/
  redaction.py` (new), `apps/orchestrator/src/orchestrator/{api_client.py
  (runtime-keys/eval-floor methods, provider param, scrub on append_event),
  dispatch_gate.py (new), claude_runner.py (anthropic_api_key param),
  fixture_runner.py (matching param), agents/{planner.py, review.py,
  delivery_manager.py, dev.py} (dispatch-gate wiring, credentials threaded
  into route()), evals/{judge.py (platform_credentials), distiller_scorer.py,
  planner_scorer.py, review_scorer.py (credentials param), loader.py
  (ProviderThreshold/providers field)}`, `scripts/check_llm_router_gate.py`
  (allowlist), `evals/thresholds.yaml` (providers: sub-maps),
  `apps/web/src/{api/{client.ts, queries.ts}, admin/ProviderKeysPage.tsx
  (new), App.tsx (Keys nav entry)}`, `docs/{02-data-model.md,
  06-tech-stack.md, 09-saas-model.md}`, test files listed below.
- Test evidence: `apps/api` 128/128 (up from 116 — 12 new: 5
  `test_provider_key_router.py`, 4 `test_eval_floors_router.py`, 2
  `test_byok_attribution.py`, 1 `test_redaction.py`, all against real
  Postgres + a real ephemeral Vault container), ruff/mypy clean; both static
  gates pass for real (llm-router-gate's allowlist exception verified to be
  load-bearing, not decorative — see above). `packages/llm_router` 12/12 (3
  new: real HTTP-boundary fault-injected fallover/all-fail/transient-retry
  tests via `respx`, zero live provider spend), ruff/mypy clean.
  `packages/schemas` 26/26 (4 new pure-function redaction tests), ruff/mypy
  clean. `apps/orchestrator` 43 unit + 22 integration, all green after
  updating every existing fake-`route()` test double across
  `test_planner_agent.py`/`test_review_agent.py`/
  `test_delivery_manager_agent.py`/`test_e2e_management_flow.py` to accept
  the new `credentials` kwarg and carry a `.provider` attribute — a real,
  necessary fallout fix, not papered over; ruff/mypy clean. `apps/web`:
  `tsc -b --noEmit` clean, `eslint` clean (1 pre-existing unrelated
  warning), `vitest run` 1/1, `vite build` succeeds.
- Notes / follow-ups: `make eval` was **not run for real** — the local
  `ANTHROPIC_API_KEY` in this environment was smoke-tested directly and
  confirmed still at zero credit balance (same recurring blocker as
  T-105/106/110; see memory `feedback_eval_gate_ci_billing.md`). CI's
  `eval-gate.yml` job uses its own repo-secret key and may have real credit
  — its actual result must be checked before merge, not assumed green from
  this disclosure. A third provider (Gemini), a live OpenAI eval run,
  `complexity`-based model subdivision within a role, a dedicated per-agent
  provider/model picker UI (vs. the opt-in surfacing on the provider-keys
  page instead), real cron for health-checks (vs. the real, callable,
  testable function that exists), and real production Vault topology (raft
  storage, auto-unseal, AppRole auth, TLS — dev-mode only here, same
  standing as MinIO for S3) are all explicitly out of scope, not silent
  gaps — see `tasks/BACKLOG.md`'s T-202 entry for the full list.

## T-203 · GitHub connect & provisioned repos — 2026-07-08
- What changed: the whole system had exactly one repo target before this
  task — this platform monorepo itself, reached via an ambient
  `GITHUB_TOKEN` PAT and `gh` CLI auto-auth (the "single-app assumption"
  SPEC-203 names). No GitHub App, installation-token, repo-registry, or
  GitHub-native-webhook concept existed anywhere (confirmed by grep, not
  assumed). This task makes the platform able to deliver code to a
  CUSTOMER's own repo (App install) or a repo it provisions and later hands
  over, while leaving the dogfood path untouched as a fallback. New
  `apps/api/src/api/github_app_client.py` is the sole owner of
  `api.github.com` calls (enforced by a new `scripts/check_github_app_gate.py`,
  mirroring `check_llm_router_gate.py`'s discipline): real RS256 JWT signing
  (`mint_app_jwt`), real installation-token minting
  (`mint_installation_token`, asserting the ≤1h TTL ceiling before ever
  returning a token — AC2's "introspection test" IS this assertion), real
  branch-protection checks, repo-from-template creation, ownership transfer,
  and archive-URL resolution, plus HMAC webhook-signature verification. New
  `repos` table (org_id, mode connected|provisioned, github_installation_id,
  github_repo_id, clone_url, default_branch, ci_mode,
  protected_branch_rules_verified, status active|disconnected|exported) and
  a nullable `tickets.repo_id` FK — null means the pre-T-203 dogfood path,
  never backfilled, mirroring `agent_runs.provider`'s T-202 precedent.
  `apps/api/src/api/services/github_repo_service.py` orchestrates
  connect/provision/export/disconnect/token-mint; `build_connect_url` signs
  a short-lived `state` token (itsdangerous) that doubles as CSRF protection
  for the GitHub App's browser-redirect callback. Two-tier App permissions:
  customer-connect installations request `contents:write`+
  `pull_requests:write` only (SPEC-203's "selected repos only" verbatim);
  the platform's own installation (provisioned repos only, never a
  customer's) additionally requests `administration:write` for
  repo-transfer export — a disclosed, not-live-verified assumption about
  whether an installation token can call that endpoint at all. New
  `github_webhook_service.py` handles GitHub's native `installation`/
  `check_run` webhooks (`POST /webhooks/github`, deliberately separate from
  the pre-existing custom `/webhooks/ci-result` route, which stays
  untouched) — `installation.deleted` force-disconnects the affected
  `repos` rows and force-transitions every in-flight ticket to `blocked`,
  synchronously, in the same request (AC4's "within 60s" by construction,
  not polling); `check_run.completed` resolves the ticket via a new
  `schemas.branches.ticket_id_from_branch` helper and delegates to a
  `webhook_service.apply_ci_result` helper extracted from the existing
  `handle_ci_result` (same code path for both entry points now, one less
  place to drift; `handle_ci_result`'s own public signature/behavior is
  unchanged, its existing tests are the regression proof). The one
  disclosed state-machine rule change this task makes:
  `domain/state_machine.py`'s `blocked` target now also accepts the exact
  actor `system:github` (not any `system:*` actor — a narrow allowlist), so
  the webhook handler can force-block without becoming human-only-exempt in
  general; `ticket_service.request_transition` gained an optional `reason`
  kwarg so "events explaining why" (AC4) is a real queryable field, not
  free text jammed into `actor`. AC1's "push to their default branch is
  impossible" is proven at two independent, honestly-separated layers: (a)
  our own code — `git_ops.py` gained `BranchNotAllowed`/
  `_assert_agent_branch`, called at the top of `push`/`force_push` before
  any subprocess or network call, real and live-testable today, plus every
  git-touching function gained an `auth_header` kwarg
  (`git -c http.extraheader=...`, built by the new `build_auth_header`,
  never written to `.git/config`, never argv-visible, never logged — chosen
  over URL-embedding the token specifically to avoid persisting it to
  on-disk git config for the workspace's lifetime); (b) GitHub's own
  branch-protection, configured/verified at connect time but disclosed as
  unexercised live (no customer org exists here). `github_client.py`'s
  `GhCliGitHubClient` became a dataclass with a `token` field and a new
  `with_token`/`_env()` pair that scopes every `gh` subprocess call via a
  `GITHUB_TOKEN` env override — the exact `Popen(env=...)` pattern
  `claude_runner.py` already established for BYOK keys (T-202); `dev.py`
  and `merge_queue.py` both call the new
  `api.get_github_install_token(ticket_id)` (404 → `None` → today's
  ambient-credential behavior, unchanged) and thread the minted token
  through — `merge_queue.py` mints its OWN fresh token at merge time rather
  than reusing the dev agent's PR-creation-time one, since tokens expire
  ≤1h and the queue may run well after that (AC2's "minted per ticket", not
  "per ticket's whole lifecycle"). New `packages/schemas/src/schemas/
  branches.py` (`agent_branch_name`/`ticket_id_from_branch`) replaces the
  ad hoc `f"agent/{ticket_id}"` string duplicated in `dev.py`/
  `merge_queue.py`, since the webhook handler now needs the inverse too.
  `vault_client.py` gained `put_platform_secret`/`get_platform_secret` for
  platform-level (non-tenant) singletons at `platform/<name>`, distinct
  from BYOK's per-org `tenants/<org_id>/...` paths — used once, for the
  App's own private key. New `apps/web/src/admin/RepoConnectPage.tsx`
  mirrors `ProviderKeysPage.tsx`'s shape (list/connect/provision/export/
  disconnect, owner-gated forms, a persistent warning banner for an
  unprotected default branch).
- Files touched: `.env.example`/`Makefile` (GitHub App env vars;
  `github-app-gate` wired into `make check`; `apps/orchestrator` added to
  `make test-unit` — a pre-existing gap this fixes, its own root-level unit
  tests were never wired into any Makefile target before), `apps/api/
  migrations/versions/e6f7a8b9c0d1_*.py` (new — `repos` table,
  `tickets.repo_id`), `apps/api/src/api/{db/models.py (Repo/RepoMode/
  RepoCIMode/RepoStatus, Ticket.repo_id), github_app_client.py (new),
  vault_client.py (platform secrets), repositories/{repo_repository.py
  (new), ticket_repository.py (list_in_flight_by_repo)}, services/
  {github_repo_service.py (new), github_webhook_service.py (new),
  webhook_service.py (apply_ci_result extraction), ticket_service.py
  (reason kwarg, repo_id validation on create_ticket)}, domain/
  state_machine.py (system:github blocked exception), routers/{repos.py
  (new), webhooks.py (POST /webhooks/github), tickets.py (repo_id
  passthrough)}, contracts.py (Repo*/ConnectUrlOut/Export*/
  GitHubInstallTokenOut, CreateTicketRequest.repo_id, TicketOut.repo_id),
  main.py (router registration), pyproject.toml (pyjwt[crypto], +respx
  dev)}`, `packages/schemas/src/schemas/{branches.py (new), __init__.py}`,
  `apps/orchestrator/src/orchestrator/{git_ops.py (branch guard,
  auth_header threading), github_client.py (token field, with_token/_env),
  api_client.py (get_github_install_token), agents/dev.py (token wiring),
  merge_queue.py (per-merge token mint)}`, `scripts/{check_github_app_gate.py
  (new), check_tenant_scope_gate.py (list_by_installation allowlist)}`,
  `apps/web/src/{api/{client.ts, queries.ts}, admin/RepoConnectPage.tsx
  (new), App.tsx (Repos nav entry)}`, `docs/{02-data-model.md,
  03-state-machine.md, 06-tech-stack.md, 09-saas-model.md}`, test files
  listed below.
- Test evidence: `apps/api` 158/158 (up from 128 — 30 new: 5 pure JWT/HMAC
  unit (`test_github_app_client.py`), 9 respx HTTP-boundary unit
  (`test_github_app_client_http.py`), 10 `test_repo_router.py` (real
  ephemeral Vault + Postgres + a locally generated throwaway RSA keypair),
  5 `test_github_webhook_router.py`, plus 1 new `test_state_machine.py`
  case), ruff/mypy clean; all three static gates pass for real, each
  verified to fail on a deliberately planted violation and pass once
  reverted (llm-router-gate and tenant-scope-gate unchanged behaviorally;
  the new github-app-gate caught its own docstring's prose on first run,
  fixed by allowlisting itself alongside the pre-existing sandbox
  egress-domain list false-positive). `apps/orchestrator` 46/46 (22 unit +
  24 integration; 9 new this ticket — 6 `test_git_ops.py` + 3
  `test_github_client.py` unit tests, plus 2 new
  `test_github_app_connected_repo_flow.py` integration tests, the AC1 proof
  against a real local bare git repo standing in for "the customer repo" —
  all 35 pre-existing tests re-passed unmodified, including `make
  test-unit` now actually running orchestrator's own root-level suite for
  the first time, a pre-existing gap this ticket also fixed), ruff/mypy
  clean; the entire pre-existing integration suite (dev agent, merge
  queue, e2e management flow) re-passed unmodified, confirming the
  dogfood fallback path is genuinely byte-for-byte unchanged. `packages/
  schemas` 30/30 (4 new `branches.py` tests). `apps/web`: `tsc -b --noEmit`
  clean, `eslint` clean (1 pre-existing unrelated warning), `vitest run`
  1/1, `vite build` succeeds; additionally smoke-tested against the real
  running stack (real Postgres, real dev-mode Vault, real `apps/api`/
  `apps/web` dev servers, migrations applied clean end-to-end) via a real
  headless-Chromium Playwright session — screenshots confirmed the Repos
  page's empty state, nav wiring, and a real 503 ("GitHub App not
  configured") surfacing as a proper user-facing error banner rather than
  a silent failure.
- Notes / follow-ups: no live GitHub App is registered in this environment
  (requires a human with org-owner rights on github.com, a generated
  private key, and a configured webhook URL) and no live customer repo
  exists — every GitHub API interaction is respx-fault-injection-tested at
  the HTTP boundary, not a live github.com round-trip; this is disclosed,
  not silently assumed to work. GitHub's own server-side branch-protection
  enforcement is configured/verified but not exercised live.
  Repo-transfer's real permission requirements (can an App installation
  token call it at all) are not live-verified — flagged in code/docs for
  verification before first real use; the archive export mode has no such
  gap and is the recommended default in the UI. No new artifact/S3 storage
  was built — archive export returns GitHub's own tarball URL; MinIO is
  declared in `docker-compose.yml`/`.env.example` but nothing in this
  codebase touches it yet, unchanged by this task. A third provider
  (Gemini), incremental "repos added/removed from an existing installation"
  without a full uninstall, and real production Vault topology are all
  explicitly out of scope, not silent gaps — see `tasks/BACKLOG.md`'s
  T-203 entry for the full list.

## T-204 · VM-grade tenant isolation — 2026-07-09
- What changed: `apps/sandbox` was real (Docker network-per-ticket,
  read-only rootfs, Squid egress proxy) but had zero org-awareness and zero
  placement/pooling code, and — more importantly — `apps/orchestrator`'s
  real dev-agent run never invoked it at all: `SubprocessClaudeCodeRunner`
  spawned `claude` as a bare host subprocess against a plain git worktree,
  a gap already disclosed three times (T-105/106/107 notes). Resolved via
  two AskUserQuestion decisions: (1) this task closes that orchestrator-
  wiring gap too, not just apps/sandbox's own isolation mechanism, so the
  new guarantees actually protect real ticket runs; (2) since no
  Firecracker/Kata hypervisor is reachable in this environment (Windows dev
  host), the microVM runtime is a pluggable interface with a disclosed,
  subprocess-fault-injection-tested-only mock, not an attempted real boot —
  same disclosed category as T-202's "no OpenAI credits" / T-203's "no live
  GitHub App". New `apps/sandbox/src/sandbox/runtime.py`: a `SandboxRuntime`
  Protocol with `DockerRuntime` (thin wrapper over the pre-existing,
  behavior-unchanged `docker_runtime.py`) as the real default and
  `MicroVMRuntime` (Firecracker/Kata `ctr` CLI shapes) as the disclosed
  mock. New `scheduler.py`'s `HostPool`: real `threading.Lock`-guarded
  mutual exclusion over N logical slots, proving two different orgs never
  hold the same slot concurrently (100-round concurrent-threads property
  test) — deliberately scoped to one process/host, matching
  `docs/06-tech-stack.md`'s own "second runner VM until sustained parallel
  tickets > 5" Phase-2 activation note; true multi-host coordination is
  deferred to whenever that fires. New `pool.py`'s `SandboxPool`:
  pre-warms network+proxy pairs (the genuinely slow parts to provision —
  image pull, `wait_until_execable`/`wait_until_port_listening` polling),
  attaches a fresh ticket-bound sandbox container to an already-warm pair
  on request, and live-reconfigures the reused proxy's Squid allow-list to
  the requesting org's actual merged list via `squid -k reconfigure` (no
  container restart) — proven with a real 10-concurrent-request load test
  against real Docker, p95 comfortably under the 30s budget. New
  `org_egress_rules` table (apps/api) + `POST/DELETE /orgs/{id}/
  egress-rules`, staff-gated via the exact `ActorContext.is_platform_staff`
  check T-201 impersonation already established — no new auth concept; the
  orchestrator fetches the merged base+org list via a new service-token-
  only `GET /orgs/{id}/egress-rules/effective`. New
  `apps/api/src/api/artifact_storage.py`: real per-org MinIO storage ACLs
  via MinIO's own STS `AssumeRole` with an inline session policy scoped to
  `orgs/<org_id>/*` — closes a repo-wide disclosed gap for real (MinIO has
  sat declared-but-unused in `docker-compose.yml` since before T-203). New
  `apps/sandbox/tests/integration/test_escape_probes.py` formalizes a named
  escape-test suite (`make escape-test`): host-fs write rejected outside
  declared mounts, docker socket invisible, org A's sandbox cannot reach
  org B's — real, against `DockerRuntime`; the same probes against
  `MicroVMRuntime` are honestly `skipif`'d, not faked green. Orchestrator
  wiring: `ClaudeCodeRunner.run()` gained two **optional** kwargs,
  `org_id`/`ticket_id` (default `None`, every existing caller/
  implementation unaffected); new `orchestrator/sandbox_runner.py`'s
  `SandboxClaudeCodeRunner` implements the same Protocol, acquires a
  `HostPool` lease before ever provisioning a container (this is what makes
  AC2 real for actual dispatch, not just apps/sandbox's own isolated
  tests), execs `claude` inside the container via a new streaming
  `docker_runtime.exec_stream`, and reuses `claude_runner.py`'s private
  NDJSON-parsing helpers verbatim so its retry-on-transient-API-error
  behavior matches `SubprocessClaudeCodeRunner`'s exactly.
  `apps/orchestrator` gained `apps/sandbox` as a real editable dependency
  (same Makefile pattern as `packages/schemas`/`llm_router`); `apps/sandbox`
  gained a `py.typed` marker so the cross-package import type-checks under
  strict mypy. `scripts/run_pilot.py` (already disclosed as "NOT part of
  the product") gained a `--sandbox` opt-in flag; default stays the
  bare-host path. A real bug was caught and fixed mid-task: `HostPool` was
  built and tested in isolation first, then discovered to be completely
  unwired from `SandboxClaudeCodeRunner`'s real `run()` path until a new
  concurrency test (`test_host_pool_serializes_two_orgs_when_only_one_
  slot_exists`) forced the integration — the scheduler would otherwise have
  been decorative, not protective. A second real bug was caught the same
  way, after opening the PR: repeated local Docker runs left `sandbox-
  pool-*` proxy/network containers running indefinitely — `SandboxPool`
  tore down leased slots on `release()` but had no way to tear down IDLE
  ones (`warm()`'s initial fill, or a background `_replenish_async()`
  landing after the last request), so every unleased slot was silently
  abandoned as a real, running container pair. Fixed with a new
  `SandboxPool.shutdown()` (joins in-flight replenishment threads first,
  so a replenishment landing mid-shutdown can't create yet another orphan)
  and `SandboxClaudeCodeRunner.close()`, wired into `run_pilot.py`'s
  `finally` block. Also discovered and fixed along the way:
  `SandboxPool`'s teardown had been bypassing the injected `runtime`
  entirely and hardcoding real `docker_runtime` module calls — new
  `remove_container_named`/`remove_network_named` methods on the
  `SandboxRuntime` Protocol make teardown properly pluggable, and newly
  testable with a fake runtime. Verified with a real Docker run: zero
  leaked containers/networks after the full suite, down from dozens
  accumulated across the session before this fix.
- Verification: `apps/sandbox` 41 tests (38 passed, 3 `skipif`'d for the
  disclosed microVM gap) — up from 19 pre-existing, all re-passed
  unmodified; ruff/mypy clean. `apps/api` 165/165 green (up from 158 — 7
  new: 5 egress-router + 2 real-MinIO artifact-storage integration tests),
  ruff/mypy clean, all three static gates pass unchanged
  (`llm-router-gate`, `tenant-scope-gate`, `github-app-gate`).
  `apps/orchestrator` 50/50 green (up from 46 — 4 new
  `test_sandbox_runner.py` tests), ruff/mypy clean. Docker Desktop was not
  running at the start of this session (a Windows dev host) — it was
  started and every Docker-dependent test in this task (pool load test,
  escape probes, real `docker_runtime.exec_stream` multi-line streaming,
  MinIO cross-org ACL denial) ran for real against it locally in this same
  session, not merely asserted to pass in CI: genuine p95 < 30s measured,
  genuine cross-org MinIO policy denial observed via a real
  `botocore.exceptions.ClientError`, genuine multi-line stdout streamed
  from a real running container. A pre-existing, unrelated test-hygiene
  issue was hit and worked around (not fixed, out of this task's scope):
  `apps/sandbox`'s own `test_egress_attempts_are_logged_as_ticket_events`
  reuses a real, sequentially-incrementing ticket id
  (`~/.agent-factory-sandbox/T-001/...`) as a host cache-directory key, so
  stale state from an earlier session/run collides with a fresh `tmp_path`
  — cleaning `~/.agent-factory-sandbox` before each full run resolved it.
  Not re-verified against a clean `main` checkout, but the caching logic
  it's hitting (`cli.py`/`worktree.py`'s bare-clone cache) was untouched by
  this task and the stale directories themselves predate this session
  (timestamped days before T-204 started), so this reads as pre-existing,
  not a regression introduced here.
- Notes / follow-ups: no real Firecracker/Kata hypervisor boot anywhere —
  `MicroVMRuntime` is built and subprocess-fault-injection tested only,
  never live-verified; its escape-tests skip with an explicit reason.
  `HostPool` enforces mutual exclusion per-process/per-host only; true
  multi-host distributed coordination (Postgres advisory locks / Redis) is
  deferred to the "Runner pool → Kubernetes" Phase-2 activation, not built
  preemptively. Worktree storage gets per-org path scoping
  (`sandbox.config.org_state_dir_for`) + OS permissions only, not real
  disk-level encryption (LUKS/dm-crypt needs host provisioning beyond a
  rootless container) — a disclosed gap. Production MinIO/Vault topology
  stays dev-mode only, same standing as every other MinIO/Vault note in
  these docs. See `tasks/BACKLOG.md`'s T-204 entry for the full
  per-AC evidence and architecture-decision list.

## T-205 · Billing & metering — 2026-07-09
- What changed: Implemented SPEC-205 — subscription tiers, an idempotent
  nightly usage-metering job, deferred-downgrade plan enforcement mapped
  onto T-201's `max_parallel_tickets`, a Razorpay-webhook-driven dunning
  path reusing T-203's `disconnect_repo` force-block precedent verbatim,
  and a reconciled usage dashboard endpoint. Vendor swapped from the
  locked table's `Stripe` to Razorpay (human decision this session, no
  live account for either — resolved via AskUserQuestion) and pricing
  tiers are explicit placeholders (also resolved via AskUserQuestion, no
  real figures exist anywhere in this repo's docs). New
  `apps/api/src/api/razorpay_client.py`: a hand-rolled `httpx` REST
  wrapper (this repo's T-202/T-203 convention, not the vendor SDK), sole
  owner of `api.razorpay.com` per new `scripts/check_razorpay_gate.py`
  (`make razorpay-gate`, added to `check`) — real HMAC-SHA256 webhook
  signature verification, respx-tested at the HTTP boundary only (no live
  Razorpay account reachable here). New `apps/api/src/api/
  billing_plans.py`: `free`/`starter`/`team` tier definitions + a pure
  `compute_invoice` function (base fee + max(0, used-included)*rate per
  metered item) — the exact function the golden-total test asserts
  against. New tables `usage_events` (a sibling to `cost_ledger`, not an
  overload of `ticket_events`'s Postgres-enum `kind` column — only
  `sandbox_minutes` is written here, posted by `apps/orchestrator`'s
  `SandboxClaudeCodeRunner` after each real sandbox lease via a new
  `POST /tickets/{id}/usage-events` route) and `billing_usage_reports`
  (unique on `(org_id, report_date, kind)` — this constraint IS the
  idempotency mechanism the nightly job relies on). `orgs` gained 8 plain
  string/timestamp columns (`plan`, `pending_plan`,
  `pending_plan_effective_at`, `current_period_end`, `billing_status`,
  `dunning_grace_until`, `razorpay_customer_id`,
  `razorpay_subscription_id`) — no new Postgres enum, avoiding the
  documented two-migration ADD-VALUE-then-USE split. New
  `apps/api/src/api/services/billing_service.py`: `set_plan` (upgrade
  immediate, downgrade deferred to `current_period_end`),
  `apply_pending_plan_sweep` (applies deferred downgrades + bills the
  elapsed period's overage as real Razorpay addons + rolls the period
  forward — all three only once per elapsed period, not prorated daily, so
  they agree exactly with `compute_invoice_for_period`'s math),
  `run_metering_for_day` (idempotent raw-usage recording),
  `pause_org_for_nonpayment`/`handle_payment_failed`/
  `handle_payment_succeeded`/`expire_grace_periods` (the dunning path),
  `compute_invoice_for_period` (ledger-based, from `billing_usage_reports`)
  and `compute_live_invoice_for_period` (computed directly from
  `usage_events`/`agent_runs`/`ticket_events`, independent of the ledger —
  what the dashboard endpoint shows, so AC5's reconciliation test compares
  two genuinely independent code paths, not the same number twice). New
  `apps/api/scripts/run_billing_metering.py` (`make billing-meter
  DATE=...`) — a standalone, externally-triggered script, not a daemon; no
  scheduler infra exists anywhere in this repo
  (`provider_health_service.py`'s own disclosed standing). New
  `apps/api/src/api/routers/billing.py` (`GET/POST .../billing`,
  `.../billing/plan`, `.../billing/subscribe`, `.../billing/usage`,
  `.../billing/portal-link`) and a new `POST /webhooks/razorpay` route in
  `routers/webhooks.py`. `state_machine.py`'s `_SYSTEM_BLOCK_ACTORS` gained
  one new exact-string entry, `"system:billing"`, next to T-203's
  `"system:github"`; a new `org_over_usage_cap` guard
  (`state_machine.py`/`ticket_service.py`) extends T-201's exact
  `org_at_quota` pattern for free-tier orgs over their included
  agent-run-minutes/sandbox-minutes, hard-capping instead of billing
  overage (only paid tiers bill overage).
- Files touched: `apps/api/src/api/billing_plans.py` (new),
  `razorpay_client.py` (new), `repositories/billing_repository.py` (new),
  `services/billing_service.py` (new), `routers/billing.py` (new),
  `routers/webhooks.py`, `routers/tickets.py`, `db/models.py`,
  `contracts.py`, `main.py`, `domain/state_machine.py`,
  `services/ticket_service.py`, `repositories/ticket_repository.py`,
  `repositories/org_repository.py`,
  `migrations/versions/a2b3c4d5e6f7_billing_metering.py` (new),
  `apps/api/scripts/run_billing_metering.py` (new),
  `apps/orchestrator/src/orchestrator/api_client.py`,
  `sandbox_runner.py`, `tests/test_sandbox_runner.py`,
  `scripts/check_razorpay_gate.py` (new),
  `scripts/check_tenant_scope_gate.py` (2 new allowlist entries),
  `Makefile`, `.env.example`, `docs/06-tech-stack.md`,
  `docs/09-saas-model.md`, `docs/02-data-model.md`,
  `docs/03-state-machine.md`, `docs/05-security.md`, plus 8 new test files
  under `apps/api/tests/`.
- Test evidence: `apps/api` 199/199 green (up from 165 — 34 new: 3 pure
  `compute_invoice` unit tests, 9 real `razorpay_client.py` respx tests, 2
  metering-job (AC1/AC2), 3 plan-change (AC3), 5 dunning (AC4), 1
  reconciliation (AC5), 9 billing-router, 2 free-tier-usage-cap), ruff/
  mypy clean, all four static gates pass (`llm-router-gate`,
  `tenant-scope-gate`, `github-app-gate`, new `razorpay-gate`).
  `apps/orchestrator` 50/50 green (count unchanged — the 4 pre-existing
  `test_sandbox_runner.py` tests gained new `record_sandbox_usage_minutes`
  assertions rather than new test functions), ruff/mypy clean. Migration
  verified reversible for real against a throwaway Postgres container
  (`upgrade head` → `downgrade -1` → `upgrade head`, not just inferred
  from the file's `downgrade()` body). The nightly metering script itself
  was smoke-tested against a freshly migrated database, not just its
  underlying service functions: a first run reports usage for the seeded
  "default" org, an immediate second run for the same date is a real
  no-op. Two real bugs were caught by my own first test runs and fixed
  before proceeding, not just by design review: (1) a test wrongly
  assumed a freshly created org's `max_parallel_tickets` would reflect its
  `plan="free"` default — it doesn't, by design (T-201's own
  `test_org_with_no_quota_configured_is_unaffected` already established
  that new orgs are unlimited until a plan is actually applied via
  `set_plan`; auto-applying it at creation time would have silently
  broken that pre-existing, still-passing T-201 test), so the test's
  expectation was corrected, not the production code; (2) an early
  `apply_pending_plan_sweep` test simulated "period end" by directly
  mutating `orgs.current_period_end` in the test, which desynced it from
  `pending_plan_effective_at` (a snapshot taken at downgrade-request time)
  in a way that could never happen in real operation — fixed by passing
  an explicit future `now` to the sweep function instead, which exercises
  the real trigger condition correctly.
- Notes / follow-ups: no live Razorpay account reachable in this
  environment — `razorpay_client.py` is real and respx-tested at the HTTP
  boundary only, same standing as T-202/T-203/T-204's equivalent
  live-infra gaps. Pricing figures in `billing_plans.py` are explicit
  placeholders pending a real business decision. No new `apps/web` UI —
  matches T-201–204's own precedent exactly (none of those tickets touched
  `apps/web` either); AC5's reconciliation is proven at the API layer.
  Seats (`PlanDefinition.seats_included`) are stored but not enforced — no
  AC requires seat-capacity enforcement. No real cron/scheduler daemon
  runs the metering job — external trigger only. Already-`BLOCKED`
  tickets have no unblock path (billing- or otherwise) — a pre-existing
  gap since T-203, not created or closed here. See `tasks/BACKLOG.md`'s
  T-205 entry for the full per-AC evidence and architecture-decision list.

## T-206 · Onboarding & abuse controls — 2026-07-09
- What changed: Implemented SPEC-206 — a self-serve org-creation wizard
  chained after OIDC/dev-login (`apps/web/src/onboarding/
  OnboardingWizard.tsx`: ToS accept → `POST /orgs` → mandatory
  `POST /auth/switch-org` → the *existing* `ProviderKeysPage`/
  `RepoConnectPage` reused inside wizard chrome → a new
  `CreateFirstIdeaStep`, the first real ticket-creation UI surface in
  this app); a real, deterministic (zero-LLM) intake-screening rules
  engine (`api/services/intake_screening_service.py`) gating
  `POST /tickets` for idea/task submissions, with a staff-only review
  queue (`intake_reviews` table, `POST /admin/intake-reviews/{id}/
  approve|reject`) for borderline matches and an immediate 422 for
  hard-rejects; real ToS acceptance recorded transactionally with org
  creation (`tos_acceptances` table) and re-prompted (ticket creation
  403s) once `api.tos.CURRENT_TOS_VERSION` moves past an org's latest
  acceptance — orgs with no acceptance record at all (every pre-T-206
  org) are grandfathered, not retroactively broken; platform-staff org
  strikes (`org_strikes` table, `POST /admin/orgs/{id}/strikes`) that
  force-block every in-flight ticket via the exact loop
  `billing_service.pause_org_for_nonpayment` (T-205) already
  established, plus the first-ever whitelisted exit from `BLOCKED`
  (`BLOCKED → READY`, human-only) so a staff-approved appeal
  (`POST /orgs/{id}/strikes/{id}/appeal` self-service request,
  `POST /admin/strikes/{id}/resolve-appeal` staff-only decision) can
  actually reactivate them — closing a gap disclosed since T-203; and a
  derived (not event-sourced) cross-org funnel dashboard
  (`onboarding_service.compute_funnel_cohort`, `GET /dashboard/funnel`,
  staff-only) computing each stage's org count live from existing
  timestamped rows. New `GET /tos` endpoint so neither the wizard UI nor
  any test ever hardcodes a ToS version. Resolved via AskUserQuestion:
  "self-serve signup (email + OAuth)" is satisfied by OIDC alone (real
  IdPs authenticate via email identity) — no new password-based auth
  mechanism, zero change to the locked `docs/06-tech-stack.md` Auth row;
  the actually-missing piece was the org-creation wizard itself.
- Files touched: `apps/api/src/api/db/models.py` (3 new models:
  `TosAcceptance`, `IntakeReview`, `OrgStrike`), new migration
  `b3c4d5e6f7a8_onboarding_abuse.py`, new `api/tos.py`, new
  `api/routers/tos.py`, `api/routers/intake_reviews.py` (new),
  `api/routers/abuse.py` (new), `api/routers/orgs.py` (tos_version on
  create, `POST /orgs/{id}/tos/accept`, `GET /orgs/{id}/
  onboarding-status`), `api/routers/tickets.py` (screening + ToS gate
  wired into `create_ticket`), `api/routers/dashboard.py` (`GET
  /dashboard/funnel`), `api/services/intake_screening_service.py` (new,
  pure), `api/services/intake_service.py` (new), `api/services/
  abuse_service.py` (new), `api/services/onboarding_service.py` (new),
  `api/services/org_service.py`, `api/services/ticket_service.py`,
  `api/domain/state_machine.py` (new `BLOCKED → READY` edge),
  `api/repositories/{intake,abuse,funnel,tos}_repository.py` (all new),
  `api/repositories/ticket_repository.py` (`list_blocked_by_org`),
  `api/contracts.py`, `api/main.py`,
  `scripts/check_tenant_scope_gate.py` (6 new allowlist entries),
  `.env.example`; `apps/web/src/onboarding/*` (new: `OnboardingWizard`,
  `TosAcceptanceStep`, `CreateOrgStep`, `CreateFirstIdeaStep`),
  `apps/web/src/admin/{IntakeReviewPage,OrgStrikesPage,
  FunnelDashboardPage}.tsx` (all new), `apps/web/src/docs/*` (new:
  `ByokSetupGuide`, `CheckpointExplainerPage`), `apps/web/src/api/
  {client,queries,types}.ts`, `apps/web/src/App.tsx`; new
  `apps/orchestrator/tests/integration/test_e2e_onboarding_flow.py`,
  `apps/orchestrator/tests/integration/conftest.py` (new `STAFF_EMAIL`
  constant + `PLATFORM_STAFF_EMAILS` in the `running_api` env),
  `.github/workflows/nightly-e2e.yml`; plus 6 new test files under
  `apps/api/tests/`; docs: `docs/02-data-model.md`,
  `docs/03-state-machine.md`, `docs/04-agent-specs.md`,
  `docs/09-saas-model.md`.
- Test evidence: `apps/api` 233/233 green (up from 199 — 34 new: 9 pure
  `intake_screening_service` unit tests, 6 intake-review-flow, 6
  ToS-acceptance incl. `GET /tos`, 8 org-strikes, 2 funnel-dashboard, 2
  onboarding-status, 1 membership-race regression), ruff/mypy clean, all four static gates pass
  (`llm-router-gate`, `tenant-scope-gate`, `github-app-gate`,
  `razorpay-gate` — no new gate needed, T-206 added no new external
  vendor client). Migration verified reversible for real (`alembic
  upgrade head` → `downgrade -1` → `upgrade head` against a throwaway
  Postgres database, not just inferred). `apps/orchestrator` 83/83 green
  (up from 80 — 3 new `test_e2e_onboarding_flow.py` tests), ruff/mypy
  clean. `apps/web` `tsc -b`/`eslint`/`vitest run`/`vite build` all
  clean; every new page was smoke-tested for real against a real running
  stack (real Postgres + real dev-mode Vault + real `apps/api`/
  `apps/web` dev servers) via real headless-Chromium (Playwright) — a
  fresh dev-login viewer reaching the wizard, accepting ToS, creating an
  org, and reaching a correctly-rendered BYOK key step (real Vault write
  path); a platform-staff session seeing all four new nav buttons and
  every new admin page rendering with zero console errors; the funnel
  endpoint verified against real seeded data via a direct request. Two
  real bugs caught and fixed along the way, not just by design review:
  (1) `OnboardingWizard`'s initial-step logic used `orgId` truthiness to
  decide whether to skip ToS+org-creation — since every authenticated
  session always has an `orgId` (even the auto-joined default org), this
  always jumped straight to the key step; fixed to key off
  `onboardingStatus.tos_accepted` instead, which is genuinely false for
  the ungraduated default org. (2) The staff-facing `OrgStrikesPage` UI
  called `GET /orgs/{id}/strikes`, but that route's original
  `_require_member` gate 404'd for platform staff viewing a non-member
  org — added `_require_member_or_staff` (staff already sees everything
  about any org via impersonation, T-201) and a dedicated regression
  test proving staff can list a non-member org's strikes for real.
  (3) PR #21's own real CI `e2e` job (Playwright, `e2e/board.spec.ts`)
  failed with a 500 from `POST /auth/dev-login` —
  `psycopg.errors.UniqueViolation` on `uq_org_members_org_user`.
  `org_service.get_or_create_dev_membership`/`ensure_default_org_membership`
  had the exact same check-then-insert TOCTOU race
  `user_service.get_or_create_user` was already fixed for; Playwright's
  parallel workers all log in as the same fixed email in a
  `beforeEach`, so two workers' dev-logins can race past the
  "no existing membership" check before either commits. Pre-existing,
  not introduced by this ticket's own new code, but directly triggered
  by it. Fixed with the same `except IntegrityError: rollback();
  re-fetch` recovery `get_or_create_user` already uses, plus a
  regression test proving the repository layer raises the specific
  exception type the recovery depends on.
- Notes / follow-ups: no haiku-class LLM intake-screening layer was
  built at all (scoped but zero prompt/schema/router scaffolding exists
  — a disclosed gap, not a partial feature, see `docs/04-agent-specs.md`
  for why the deterministic rules engine is what AC2 is actually
  verified against in an environment with zero live Anthropic credit).
  The orchestrator's dev-agent pipeline (planner → Delivery Manager →
  dev → review → merge queue) cannot run against a freshly created,
  non-default org today — `dispatch_gate.resolve_dispatch`'s
  service-principal-only `runtime-keys` check and `ticket_service`'s
  actor-derived `org_id` scoping can't both be satisfied by one
  `ApiClient` instance, confirmed by reading `dispatch_gate.py`/
  `provider_keys.py` directly. This is the same "orchestrator isn't
  multi-org-aware" gap T-202/T-205 already disclosed, not created or
  closed here — `test_e2e_onboarding_flow.py`'s own docstring has the
  full explanation, and `test_e2e_management_flow.py` (T-109) remains
  the independent, nightly proof that the full idea→done pipeline
  mechanics work for real. Strike reinstatement is org-wide, not
  per-strike-cause (no `blocked_reason` column). No real legal ToS/AUP
  text, no real product-analytics vendor, no live OIDC IdP in this
  environment (unchanged since T-008/T-201). See `tasks/BACKLOG.md`'s
  T-206 entry for the full per-AC evidence and architecture-decision list.
