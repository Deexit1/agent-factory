# apps/orchestrator

Dev agent integration (SPEC-004): builds an agent's context from a `TaskSpec` (+
`FailureReport` on bounce), runs Claude Code headless, streams the transcript into
`ticket_events`, meters budget/cost, and on completion opens a PR and transitions the
ticket. See [docs/01-architecture.md](../../docs/01-architecture.md) (layer 2:
orchestration) and [docs/04-agent-specs.md](../../docs/04-agent-specs.md).

```bash
pip install -e ../../packages/schemas
pip install -e ".[dev]"
pytest
```

## What's real here (Phase 1) vs. the target design

- **Orchestration logic** (`agents/dev.py`): real — builds the prompt from a
  `packages/schemas.TaskSpec`, streams every transcript event into `ticket_events` as it
  arrives (not just at the end), tracks cumulative cost against `task_spec.budget_usd` and
  wall-clock against a configurable timeout, and escalates the ticket via the real API on
  either breach. Talks to `apps/api` over HTTP only (`api_client.py`) — never touches the
  database directly, per the layer-2/layer-5 split in `docs/01-architecture.md`.
- **Claude Code invocation** (`claude_runner.py`): `SubprocessClaudeCodeRunner` is a real
  implementation (spawns `claude -p ... --output-format stream-json`), but it is **not**
  exercised by the test suite — no `ANTHROPIC_API_KEY` is spent here. Tests run against
  `FixtureClaudeCodeRunner`, which replays a hand-authored transcript
  (`fixtures/add_health_endpoint/transcript.jsonl`) and applies a matching
  `workspace_diff/` to the working tree, so the rest of the pipeline (event streaming,
  budget checks, git commit/push, PR body) is exercised for real.
- **PR creation** (`github_client.py`): `GhCliGitHubClient` is a real implementation
  (shells out to `gh pr create`), but tests use `FakeGitHubClient`, which records calls
  instead of hitting the GitHub API — no scratch repo is available here. Git commit/push
  themselves *are* real in tests, against a local bare "origin".
- **Credential scoping**: relies on the sandbox's pre-push hook (T-005) to restrict pushes
  to `agent/<ticket_id>` — this package doesn't re-implement that check.

## Layout

- `src/orchestrator/agents/dev.py` — orchestration entry point, `run_dev_agent(...)`
- `src/orchestrator/agents/prompt.py` — builds the prompt from `TaskSpec`/`FailureReport`
- `src/orchestrator/claude_runner.py` — `ClaudeCodeRunner` protocol + real subprocess impl
- `src/orchestrator/fixture_runner.py` — fixture-replaying test double
- `src/orchestrator/github_client.py` — `GitHubClient` protocol, real (`gh` CLI) + fake
- `src/orchestrator/git_ops.py` — commit/push/diff helpers
- `src/orchestrator/api_client.py` — HTTP client for `apps/api`
- `fixtures/add_health_endpoint/` — the recorded (hand-authored) transcript + diff
- `tests/integration/` — real Postgres + real `apps/api`, real git, fake Claude + GitHub;
  covers all five SPEC-004 acceptance criteria
