# Agent Factory — AI Assistant Instructions

You are helping build the **Autonomous Agent Factory**: a Jira-style platform where AI agents
execute tickets end-to-end (plan → build → test → ship) under human supervision.

This file is your permanent context. Read it before every task.

## How we work in this repo (the manual factory)

Until the platform exists, THIS REPO runs the factory process manually:

1. **`tasks/BACKLOG.md`** is the board. Every task has an ID, state, and acceptance criteria.
2. You (the AI assistant) are the **dev agent**. Work only on the task the human points you
   at — never invent scope.
3. A task is **done only when its acceptance criteria pass as automated tests** and
   `make check` is green. Tests are the QA gate; your opinion is not.
4. If tests fail, that is a **bounce**: fix and re-run. After 3 failed attempts, stop and
   escalate to the human with a summary of what you tried.
5. When you finish a task, update its state in `tasks/BACKLOG.md` and append an entry to
   `tasks/CHANGELOG.md` (what changed, files touched, test evidence).

## Reading order for context

1. `docs/00-vision.md` — what we're building and why
2. `docs/01-architecture.md` — the five layers
3. `docs/02-data-model.md` + `docs/03-state-machine.md` — the core domain
4. `docs/06-tech-stack.md` — locked technology choices (do not substitute)
5. `docs/07-conventions.md` — code style, structure, commit format
6. The spec in `specs/` referenced by your current task

## Hard rules

- **Docs are the source of truth; code follows docs.** Never change the state machine,
  data model, or stack without updating the relevant `docs/` file in the same PR and
  flagging it to the human.
- **Never** commit secrets, tokens, or `.env` files. Use `.env.example`.
- Every new endpoint, function, or component ships **with tests in the same commit**.
- Budgets, retries and permissions are enforced **in orchestrator code**, never in prompts.
- Prefer boring technology already listed in `docs/06-tech-stack.md`.
- Small PRs: one task = one branch (`task/T-xxx-slug`) = one PR.

## Commands

```bash
make dev        # run API + frontend locally (docker compose up)
make test       # unit tests (pytest + vitest)
make check      # full QA gate: lint + typecheck + unit + integration
make e2e        # playwright end-to-end suite
make migrate    # apply alembic migrations
```

## Project structure (target)

```
apps/
  api/          # FastAPI backend (Python 3.12)
  web/          # React 18 + TS + Vite frontend
  orchestrator/ # LangGraph workflows (Python)
  sandbox/      # sandbox runner images + provisioning scripts
packages/
  schemas/      # shared Pydantic contracts (TaskSpec, FailureReport, ...)
docs/           # architecture source of truth
specs/          # feature specs (what to build)
tasks/          # backlog, changelog (how work is tracked)
prompts/        # system prompts for the PRODUCT's runtime agents
```

## Definition of done (every task)

- [ ] Each acceptance criterion maps to at least one passing test
- [ ] `make check` green locally
- [ ] Docs updated if behaviour or schema changed
- [ ] `tasks/BACKLOG.md` state updated + `tasks/CHANGELOG.md` entry added
