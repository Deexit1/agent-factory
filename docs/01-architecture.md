# 01 — Architecture

Five layers with clean contracts. Higher layers never bypass lower ones.

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

## Key design rules
- **Code is law, prompts are suggestions.** Budgets, retry limits, transitions and
  permissions are enforced in layer 2 code — never delegated to agent judgment.
- **Agents request transitions; the orchestrator applies them** after validating against
  the whitelist in `docs/03-state-machine.md`.
- **Append-only event log** (layer 5) records every agent message, tool call, test result
  and token count. It is audit trail, debugger, and future eval dataset.
- **Deterministic QA.** Pass/fail is decided by CI pipelines, not by a model.
- **Agents are pluggable.** Layer 3 wraps external coding agents (Claude Code headless);
  swapping models must never require platform changes.

## Per-ticket workflow (LangGraph graph)
```
exec_panel → human_gate(idea) → planner → human_gate(budget) → assign
  → dev_loop → qa → [pass → done → human_gate(deploy)]
               └── [fail → bounce (max 3) → dev_loop | escalate]
```
