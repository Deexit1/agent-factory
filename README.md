# Autonomous Agent Factory

A Jira-style delivery platform where AI agents run the pipeline — from appraising an idea's
business case to shipping tested code — under human supervision at hard checkpoints.

## How this repo is organised

| Folder | Purpose |
|---|---|
| `docs/` | Architecture source of truth. Code follows docs, never the reverse. |
| `specs/` | Feature specs — the "what to build", one file per feature. |
| `tasks/` | The manual board: `BACKLOG.md` (tasks + states) and `CHANGELOG.md`. |
| `prompts/` | System prompts for the product's runtime agents (planner, dev, QA, exec). |
| `CLAUDE.md` | Working instructions for Claude Code (mirrored to `.github/copilot-instructions.md` for Copilot). |

## The bootstrap trick

This markdown structure IS a manual version of the factory we're building:
`BACKLOG.md` is the board, the human is the orchestrator + approval gate,
Claude Code / Copilot is the dev agent, and the test suite is the QA gate.
We use the process to build the platform that automates the process.

## Getting started (with Claude Code or Copilot)

1. Open the repo in your assistant (Claude Code: `claude` in repo root; Copilot picks up
   `.github/copilot-instructions.md` automatically).
2. Say: *"Read CLAUDE.md and docs/, then pick up task T-001 from tasks/BACKLOG.md."*
3. Review the PR. Merge when `make check` is green and criteria are met.
4. Repeat, in backlog order. Phase-1 scope lives in `specs/SPEC-001` … `SPEC-006`.
