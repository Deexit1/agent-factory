# SPEC-104 — Specialised Dev Agent Profiles

## Goal
Replace the single Phase-1 dev agent with frontend / backend / devops profiles:
same runtime, different base images, tool allow-lists, prompts and eval sets.

## In scope
- Profile packaging: `apps/sandbox/images/{frontend,backend,devops}/` with pre-baked
  toolchains; profile manifest (prompt version, model, tools, image tag).
- Prompt variants extending `prompts/dev-agent.md` (shared core + profile appendix);
  test-author behaviour folded into each profile (criteria → tests in the same PR).
- Complexity flag routing: `complexity=high` in TaskSpec → opus-class for that run.
- Per-profile golden sets under `evals/dev/{profile}/` seeded with pilot tickets.
- Backward compatibility: generic profile remains for unclassified tasks.

## Acceptance criteria
1. A CSS/layout fixture task assigned to `frontend` completes with Playwright evidence;
   the same TaskSpec assigned to `devops` is refused by the registry skill match.
2. Profile manifests are the only place image/model/prompt versions are defined
   (grep-gate test: no hardcoded model strings elsewhere).
3. `complexity=high` produces an opus-class agent_run row; default produces sonnet-class.
4. Each profile passes its golden-set floor in `make eval`.
5. Sandbox for each profile boots in < 30s from the pre-baked image (perf test).
