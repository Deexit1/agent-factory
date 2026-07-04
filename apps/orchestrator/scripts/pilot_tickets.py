"""T-009 pilot ticket definitions. Not part of the product — a one-off input list for
run_pilot.py. See tasks/CHANGELOG.md's T-009 entry and tasks/PILOT-REPORT.md for results.
"""

from schemas import AcceptanceCriterion, Complexity, TaskSpec

TICKET_BUDGET_USD = 3.0


def _spec(id_: str, title: str, context: str, ac_description: str, verification: str) -> TaskSpec:
    ac = AcceptanceCriterion(id=f"{id_}-AC1", description=ac_description, verification=verification)
    return TaskSpec(
        id=id_,
        title=title,
        context=context,
        acceptance_criteria=[ac],
        complexity=Complexity.LOW,
        budget_usd=TICKET_BUDGET_USD,
    )


# Ordered safest-first (docs, then additive tests, then small real follow-ups).
# `id_` here is a placeholder — the real ticket id comes from POST /tickets; see run_pilot.py.
PILOT_TICKETS: list[TaskSpec] = [
    _spec(
        "PILOT-01",
        "Update apps/web/README.md to reflect what's actually built",
        "apps/web/README.md is still the one-line T-001 scaffolding stub. The frontend now "
        "has a real board (drag-and-drop, ticket drawer, live event feed via WebSocket), "
        "OIDC login (Google + dev-login), a pilot dashboard page, and Vitest/Playwright test "
        "suites. Bring the README up to date with what exists: what's in src/, how to run "
        "dev/test/e2e/a11y, and a link to docs/06-tech-stack.md and docs/07-conventions.md "
        "like the other package READMEs already do (see apps/orchestrator/README.md for the "
        "level of detail expected).",
        "apps/web/README.md documents the board, auth, dashboard, and test commands",
        "manual review of apps/web/README.md",
    ),
    _spec(
        "PILOT-02",
        "Update apps/api/README.md to reflect what's actually built",
        "apps/api/README.md is still the one-line T-001 scaffolding stub. The API now has "
        "routers for tickets, agent-runs, auth (OIDC + dev-login + service token), webhooks "
        "(CI result), dashboard, and websockets, plus Alembic migrations and a real test "
        "suite. Bring the README up to date: what's in src/api/, the auth model (bearer "
        "token, session JWT vs service token), how to run migrations/tests, matching the "
        "detail level of apps/orchestrator/README.md.",
        "apps/api/README.md documents the routers, auth model, migrations, and test commands",
        "manual review of apps/api/README.md",
    ),
    _spec(
        "PILOT-03",
        "Add a unit test for sandbox.events_client.post_event",
        "apps/sandbox/src/sandbox/events_client.py's post_event function (which POSTs "
        "egress-violation events to the ticket API, authenticated via "
        "AGENT_FACTORY_SERVICE_TOKEN) has no direct unit test today — coverage is only 50% "
        "and it's only exercised indirectly through the Docker-heavy integration suite. Add "
        "a unit test in apps/sandbox/tests/unit/ that mocks httpx.post and asserts the "
        "Authorization header and JSON payload are constructed correctly, following the "
        "existing unit test patterns in that directory (e.g. test_credential_broker.py).",
        "a new unit test asserts post_event sends the correct Authorization header and payload",
        "apps/sandbox/tests/unit/test_events_client.py",
    ),
    _spec(
        "PILOT-04",
        "Test the IntegrityError race-recovery path in user_service.get_or_create_user",
        "apps/api/src/api/services/user_service.py's get_or_create_user catches "
        "IntegrityError to recover from a race between two concurrent first-logins for the "
        "same email (see its docstring). This recovery branch (lines ~35-38) is only "
        "exercised indirectly today. Add an integration test in "
        "apps/api/tests/integration/test_user_service.py that actually drives "
        "get_or_create_user through that except-and-refetch path (e.g. by pre-inserting the "
        "row via the repository directly between the function's get_user() check and its "
        "create_user() call is hard to simulate directly — instead, call get_or_create_user "
        "for an email that already exists via repo.create_user, then verify a second call "
        "with a different role_override still returns the first row's role, AND add a "
        "focused test that calls repo.create_user twice for the same email and confirms the "
        "second raises IntegrityError specifically, which is the exception type the service "
        "depends on catching).",
        "a new test exercises get_or_create_user's IntegrityError recovery path directly",
        "apps/api/tests/integration/test_user_service.py",
    ),
    _spec(
        "PILOT-05",
        "Add tests for the untested 404 branches in routers/tickets.py",
        "apps/api/src/api/routers/tickets.py has several TicketNotFound -> 404 branches "
        "(list_ticket_events, approve_ticket, return_to_dev, create_ticket_event) that "
        "aren't all covered by existing tests (coverage report shows lines 78, 104-105, "
        "128-129, 161-162 as missing). Add integration tests in "
        "apps/api/tests/integration/test_tickets_api.py (or a new file) covering each of "
        "these for a ticket id that doesn't exist, asserting 404.",
        "each currently-uncovered 404 branch in routers/tickets.py has a passing test",
        "apps/api/tests/integration/test_tickets_api.py",
    ),
    _spec(
        "PILOT-06",
        "Add tests for the untested 404 branches in routers/agent_runs.py",
        "apps/api/src/api/routers/agent_runs.py has several TicketNotFound -> 404 branches "
        "(list_agent_runs, list_cost_ledger, cost_summary, complete_agent_run) not fully "
        "covered by existing tests (coverage report shows lines 56, 67-68, 77-78, 87-88 as "
        "missing). Add integration tests in apps/api/tests/integration/test_agent_runs_api.py "
        "covering each for a ticket id that doesn't exist, asserting 404.",
        "each currently-uncovered 404 branch in routers/agent_runs.py has a passing test",
        "apps/api/tests/integration/test_agent_runs_api.py",
    ),
    _spec(
        "PILOT-07",
        "Add tests for untested branches in routers/auth.py",
        "apps/api/src/api/routers/auth.py is only 72% covered (lines 29-37, 43-44, 50-58 "
        "missing) — the /auth/login redirect happy path and /auth/callback's "
        "missing-email-claim 401 aren't tested. Add integration tests that: (1) monkeypatch "
        "OIDC_ISSUER_URL/CLIENT_ID/CLIENT_SECRET env vars plus mock "
        "authlib.integrations.starlette_client.OAuth so /auth/login redirects without "
        "hitting a real IdP, and (2) verify /auth/callback returns 401 when the OIDC "
        "provider's token response has no 'email' in userinfo.",
        "routers/auth.py's login-redirect and missing-email-claim branches have passing tests",
        "apps/api/tests/integration/test_auth_api.py",
    ),
    _spec(
        "PILOT-08",
        "Add a test for db/session.py's get_db dependency cleanup",
        "apps/api/src/api/db/session.py's get_db() generator (lines 28-32) always closes "
        "its session in a finally block; this isn't directly unit-tested today (coverage "
        "76%). Add a focused test in apps/api/tests/ that drives the generator directly "
        "(e.g. via next()/close() or a try/finally) and asserts session.close() is called, "
        "using a mock or a real throwaway session.",
        "a new test directly exercises get_db's session cleanup path",
        "apps/api/tests/test_session.py (new)",
    ),
    _spec(
        "PILOT-09",
        "Add a test for the untested line in ws/broadcaster.py",
        "apps/api/src/api/ws/broadcaster.py is 95% covered with one missing line (27). "
        "Read the file, identify what that line does (likely unsubscribe-when-not-present "
        "or similar edge case), and add a unit/integration test in apps/api/tests/ that "
        "exercises it directly.",
        "the previously-uncovered line in broadcaster.py is now covered by a passing test",
        "apps/api/tests/",
    ),
    _spec(
        "PILOT-10",
        "Add a test for the untested line in ticket_repository.py",
        "apps/api/src/api/repositories/ticket_repository.py is 98% covered with one "
        "missing line (80). Read the file, identify what that line does, and add an "
        "integration test in apps/api/tests/integration/test_ticket_repository.py "
        "exercising it directly.",
        "the previously-uncovered line in ticket_repository.py is now covered by a passing test",
        "apps/api/tests/integration/test_ticket_repository.py",
    ),
    _spec(
        "PILOT-11",
        "Add a test for the untested line in webhook_service.py",
        "apps/api/src/api/services/webhook_service.py is 97% covered with one missing "
        "line (69) — the non-auto-escalated branch of the TransitionRefused re-raise in "
        "handle_ci_result. Add an integration test in "
        "apps/api/tests/integration/test_ci_webhook_api.py that drives this specific branch "
        "(a TransitionRefused from request_transition that ISN'T the max-bounces "
        "auto-escalation case) and asserts the exception propagates / the endpoint responds "
        "appropriately.",
        "the previously-uncovered re-raise branch in webhook_service.py is now covered",
        "apps/api/tests/integration/test_ci_webhook_api.py",
    ),
    _spec(
        "PILOT-12",
        "Add a test for the untested branch in schemas/cli.py",
        "packages/schemas/src/schemas/cli.py is 97% covered with one missing line (53). "
        "Read the file to identify what that branch does and add a test in "
        "packages/schemas/tests/test_cli.py exercising it.",
        "the previously-uncovered branch in schemas/cli.py is now covered by a passing test",
        "packages/schemas/tests/test_cli.py",
    ),
    _spec(
        "PILOT-13",
        "Add a unit test for the FailureReport-injection branch in orchestrator's prompt.py",
        "apps/orchestrator/src/orchestrator/agents/prompt.py's build_prompt() has an "
        "80%-covered branch (lines 18-21) for when a FailureReport is passed in (the bounce "
        "case). Add a unit test in apps/orchestrator/tests/ that calls build_prompt with a "
        "real FailureReport and asserts the resulting prompt includes the failure details "
        "(failing tests, expected_vs_actual, attempt number).",
        "a new test asserts build_prompt includes FailureReport details when one is passed",
        "apps/orchestrator/tests/test_prompt.py (new)",
    ),
    _spec(
        "PILOT-14",
        "Add tests for untested lines in orchestrator's git_ops.py",
        "apps/orchestrator/src/orchestrator/git_ops.py is 83% covered (lines 8, 27-28 "
        "missing) — likely the command-failure error path in _run and the diff_against "
        "function, neither directly tested today. Add unit tests in "
        "apps/orchestrator/tests/ using a real throwaway git repo (see the toy_repo fixture "
        "pattern in tests/integration/conftest.py) that exercise diff_against and a failing "
        "git command's RuntimeError.",
        "diff_against and the command-failure path in git_ops.py are covered by passing tests",
        "apps/orchestrator/tests/test_git_ops.py (new)",
    ),
    _spec(
        "PILOT-15",
        "Add tests for the untested timeout/no-changes branches in orchestrator's dev.py",
        "apps/orchestrator/src/orchestrator/agents/dev.py is 90% covered (lines 72-74, "
        "77-78, 114 missing) — likely the wall-clock timeout branch and the 'agent produced "
        "no changes' branch in run_dev_agent. Add integration tests (following the existing "
        "pattern in apps/orchestrator/tests/integration/test_dev_agent.py, which already has "
        "a budget_exceeded test) covering: a FixtureClaudeCodeRunner-driven run that exceeds "
        "config.timeout_s, and one where the fixture makes no file changes.",
        "the timeout and no-changes branches in run_dev_agent are covered by passing tests",
        "apps/orchestrator/tests/integration/test_dev_agent.py",
    ),
    _spec(
        "PILOT-16",
        "Add tests for untested lines in orchestrator's api_client.py",
        "apps/orchestrator/src/orchestrator/api_client.py is 89% covered (lines 29-31, 91 "
        "missing). Read the file to identify what those lines do (likely error-handling in "
        "get_ticket or the close() method) and add unit tests in apps/orchestrator/tests/ "
        "covering them, mocking httpx where needed.",
        "the previously-uncovered lines in api_client.py are now covered by passing tests",
        "apps/orchestrator/tests/test_api_client.py (new)",
    ),
    _spec(
        "PILOT-17",
        "Wire vitest coverage into make coverage-gate for apps/web",
        "T-007's CHANGELOG entry flagged that apps/web has no @vitest/coverage-v8 dependency "
        "or coverage script, so the changed-lines coverage gate (make coverage-gate) only "
        "covers the four Python packages, not the frontend. Add @vitest/coverage-v8 as a "
        "devDependency, add a coverage config to vite.config.ts's test block (provider: "
        "'v8', reporter including 'lcov' for diff-cover), add an npm script (e.g. "
        "'test:coverage': 'vitest run --coverage'), and wire it into the Makefile's "
        "coverage-gate target so diff-cover also checks apps/web's lcov report against the "
        "same 80% threshold.",
        "make coverage-gate includes apps/web's changed-lines coverage alongside the Python "
        "packages",
        "manual run of make coverage-gate (or the equivalent npm/diff-cover commands)",
    ),
    _spec(
        "PILOT-18",
        "Add WebSocket auth via a ?token= query param on /ws/tickets/{id}",
        "T-008's CHANGELOG entry flagged that /ws/tickets/{id} has no authentication — every "
        "other route requires a bearer token, but browsers can't attach custom headers to a "
        "native WebSocket handshake, so this was left as a known gap. Add an optional "
        "`token` query parameter to the websocket route in "
        "apps/api/src/api/routers/ws_tickets.py, verify it the same way "
        "api.auth.get_actor_context does (service token or session JWT), and close the "
        "connection with code 4401 if the token is missing or invalid before accepting the "
        "connection. Update apps/web/src/api/client.ts's ticketEventsWsUrl to include the "
        "current session token as a query param.",
        "connecting to /ws/tickets/{id} without a valid token is rejected with close code 4401",
        "apps/api/tests/integration/test_tickets_ws.py",
    ),
    _spec(
        "PILOT-19",
        "Add an admin-only endpoint to change a user's role",
        "T-008's CHANGELOG entry flagged that there's no way to promote a user past the "
        "ADMIN_EMAILS-seeded bootstrap set except a direct DB update. Add "
        "PATCH /users/{email}/role (admin-only, 403 for non-admin) to a new or existing "
        "router, backed by a small user_service.update_role function, returning the "
        "updated user. Follow the existing router/service/repository layering and auth "
        "dependency patterns used elsewhere in apps/api/src/api/routers/.",
        "an admin can change another user's role via PATCH /users/{email}/role; a non-admin "
        "gets 403",
        "apps/api/tests/integration/ (new or existing test file)",
    ),
    _spec(
        "PILOT-20",
        "Consolidate the duplicated api venv-bootstrap logic",
        "T-004's CHANGELOG entry flagged that apps/api/scripts/e2e-server.sh and "
        ".github/workflows/ci.yml's a11y job both hand-roll the same "
        "'create venv, pip install schemas then api[dev], set auth env vars' logic "
        "independently, and it's easy for one to drift from the other (this already "
        "happened once — see the T-007 'fix (same day)' CHANGELOG entry). Extract the "
        "shared steps into one script (e.g. apps/api/scripts/bootstrap-venv.sh) that both "
        "e2e-server.sh and ci.yml's a11y job call instead of duplicating the pip install "
        "sequence and env var exports.",
        "e2e-server.sh and ci.yml's a11y job both call the same shared bootstrap script",
        "manual review; existing make e2e / a11y jobs still pass",
    ),
    _spec(
        "PILOT-21",
        "Make CORS allowed origins configurable instead of hardcoded localhost",
        "apps/api/src/api/main.py hardcodes allow_origins=['http://localhost:5173'] with a "
        "comment saying 'SPEC-006 will replace this with a proper allow-list once real "
        "deployments/SSO exist' — SPEC-006 (T-008, OIDC auth) is done and never touched "
        "this. Add a CORS_ALLOWED_ORIGINS env var (comma-separated, defaulting to "
        "http://localhost:5173 for local dev) and use it to build the allow_origins list. "
        "Update .env.example and remove the now-stale comment.",
        "CORS allowed origins are read from a CORS_ALLOWED_ORIGINS env var, not hardcoded",
        "apps/api/tests/ (existing tests pass; add one asserting the env var is honored)",
    ),
    _spec(
        "PILOT-22",
        "Add a trace_id correlation id to orchestrator agent runs",
        "apps/orchestrator/src/orchestrator/agents/dev.py calls api.create_agent_run(...) "
        "without ever passing trace_id, even though AgentRun has had that field since T-006 "
        "specifically for correlating with future observability tooling (Langfuse, per "
        "docs/06-tech-stack.md). Generate a uuid4-based trace_id in run_dev_agent and pass "
        "it through to create_agent_run.",
        "run_dev_agent passes a generated trace_id to create_agent_run",
        "apps/orchestrator/tests/integration/test_dev_agent.py",
    ),
]
