# 06 — Tech Stack (LOCKED — change requires a doc PR + human approval)

| Concern | Choice |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui, dnd-kit, TanStack Query |
| Backend API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic |
| Live updates | WebSockets fed by Redis pub/sub |
| Auth | OIDC SSO (Authlib); RBAC: admin / approver / viewer |
| Orchestration | LangGraph (Python) + PostgresSaver checkpointing |
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
| Merge safety | GitHub merge queue (or bors-style bot) — required for all `agent/*` PRs |
| LLM routing | `packages/llm_router` (thin custom router, LiteLLM-style): role+complexity+org → provider/model; sole owner of provider SDKs |
| Tenant secrets (BYOK) | Vault KV `tenants/<org>/llm/<provider>`; keys never in DB/logs/traces/sandboxes |
| Repo delivery | GitHub App (contents + PRs on selected repos), per-ticket installation tokens |
| Billing | Stripe (subscriptions + metered usage records) |
| Multi-tenant sandbox | Firecracker/Kata microVMs — REQUIRED at multi-tenant GA (gVisor allowed for single-tenant/dev and closed beta only) |

## Phase-2 activations (pre-approved escalation paths)
- **Runner pool → Kubernetes** (EKS/GKE + autoscaling runners) WHEN sustained parallel
  tickets > 5. Until then: second runner VM.
- **Orchestration → Temporal** WHEN LangGraph checkpoint recovery fails us twice in
  production or ticket volume > 50/day. Not before — migration is expensive.
- **Sandbox → Firecracker/Kata** WHEN agents get access to repos with sensitive data
  classifications. gVisor remains fine for the pilot repos.
