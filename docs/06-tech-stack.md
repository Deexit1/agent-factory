# 06 — Tech Stack (LOCKED — change requires a doc PR + human approval)

| Concern | Choice |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui, dnd-kit, TanStack Query |
| Backend API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic |
| Live updates | WebSockets fed by Redis pub/sub |
| Auth | OIDC SSO (Authlib); RBAC: admin / approver / viewer |
| Orchestration | LangGraph (Python) + PostgresSaver checkpointing (adopted T-103 — single-node StateGraph for the Planner so far; checkpointing lands with the first real multi-step graph, T-104+) |
| LLM | Anthropic API. Routing: sonnet default, opus for planning/complex, haiku for classification & log distillation. Prompt caching on. |
| Dev agents | Claude Code headless (Claude Agent SDK), per-profile base images |
| Database | PostgreSQL 16 (JSONB payloads), Redis 7 |
| Artifacts | S3 / MinIO |
| Sandbox | Rootless Docker + gVisor; egress proxy (Squid); Vault for secrets |
| VCS / CI | GitHub, branch `task/T-xxx`, GitHub Actions with self-hosted runners |
| Tests | pytest, Vitest, Testcontainers, Playwright; smoke suite tagged `@smoke` |
| Static gates | ruff, mypy, eslint, tsc, Semgrep, gitleaks, pip-audit/npm audit |
| Evals | Golden-set harness (`make eval`) — promptfoo-style YAML cases + custom scorer, runs in CI on `prompts/**` or routing diffs |
| Observability | Langfuse (Cloud, Phase-2 pragmatic choice — see T-101 changelog; self-hosting is a separate future migration) for agent traces + cost; OpenTelemetry → Prometheus/Grafana/Loki |
| Merge safety | Home-grown FIFO merge queue (T-107, `apps/orchestrator/src/orchestrator/merge_queue.py`) — real rebase-and-retest + conflict bounce, required for all `agent/*` PRs. Deliberately not GitHub's native merge-queue feature or a bors-style bot (would need GitHub org/repo admin configuration this repo doesn't assume); revisit once that's actually available. |
| LLM routing | `packages/llm_router` (thin custom router, LiteLLM-style): role+complexity+org → provider/model; sole owner of provider SDKs |
| Tenant secrets (BYOK) | Vault KV `tenants/<org>/llm/<provider>`; keys never in DB/logs/traces/sandboxes |
| Repo delivery | GitHub App (contents + PRs on selected repos), per-ticket installation tokens |
| Billing | Stripe (subscriptions + metered usage records) |
| Multi-tenant sandbox | Firecracker/Kata microVMs — REQUIRED at multi-tenant GA (gVisor allowed for single-tenant/dev and closed beta only) |

## Implementation status notes (do not change the locked rows above without a doc PR)
- **LLM routing / Tenant secrets (BYOK) rows — real as of T-202.** `packages/llm_router`
  now takes `(agent_role, complexity, org-fetched credentials)` and does real
  provider fallover/retries across Anthropic + OpenAI. Vault is wired for real in
  local/CI (`docker-compose.yml`'s `vault` service, `hashicorp/vault:1.17`,
  **dev-mode only** — in-memory, root-token auth, no persistence). Real production
  Vault topology (raft storage, auto-unseal, AppRole auth, TLS) is a deploy-time
  concern, not built here — same standing as MinIO standing in for real S3 in this
  same table.
- **Repo delivery row — real as of T-203** for connect/provision/token-mint/webhook-
  disconnect: real RS256 JWT signing + real HTTP calls to `api.github.com`
  (`apps/api/src/api/github_app_client.py`, sole owner of those calls per
  `scripts/check_github_app_gate.py`), a real `repos` registry, per-ticket
  installation-token minting (`GET /tickets/{id}/github-install-token`, ≤1h TTL,
  service-principal-only), and a real native GitHub webhook route
  (`POST /webhooks/github`) that force-blocks in-flight tickets on App uninstall.
  **Not yet real:** no live GitHub App is registered in this environment (creating one
  requires a human with org-owner rights on github.com, a generated private key, and a
  configured webhook URL) and no live customer GitHub org/repo exists — every GitHub
  API interaction is proven via `respx` HTTP-boundary fault injection (T-202's
  `packages/llm_router` precedent) plus a real local bare git repo standing in for
  "the customer repo" in orchestrator integration tests, not a live github.com
  round-trip. GitHub's own server-side branch-protection enforcement is configured and
  verified at connect time but not exercised live. The repo-transfer export mode's
  real permission requirements (whether an App installation token can call
  `POST /repos/{owner}/{repo}/transfer` at all) are built and tested against the
  documented request/response shape but flagged as needing live verification before
  first real use.

## Phase-2 activations (pre-approved escalation paths)
- **Runner pool → Kubernetes** (EKS/GKE + autoscaling runners) WHEN sustained parallel
  tickets > 5. Until then: second runner VM.
- **Orchestration → Temporal** WHEN LangGraph checkpoint recovery fails us twice in
  production or ticket volume > 50/day. Not before — migration is expensive.
- **Sandbox → Firecracker/Kata** WHEN agents get access to repos with sensitive data
  classifications. gVisor remains fine for the pilot repos.
