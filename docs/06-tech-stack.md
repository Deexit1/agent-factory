# 06 — Tech Stack (LOCKED — change requires a doc PR + human approval)

| Concern | Choice |
|---|---|
| Frontend | React 18 + TypeScript + Vite, Tailwind CSS, shadcn/ui, dnd-kit, TanStack Query |
| Backend API | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 + Alembic |
| Live updates | WebSockets fed by Redis pub/sub |
| Auth | OIDC SSO (Authlib); RBAC: admin / approver / viewer |
| Orchestration | LangGraph (Python) + PostgresSaver checkpointing |
| LLM | Anthropic API. Routing: sonnet default, opus for planning/complex, haiku for classification & log distillation. Prompt caching on. |
| Dev agent | Claude Code headless (Claude Agent SDK) |
| Database | PostgreSQL 16 (JSONB payloads), Redis 7 |
| Artifacts | S3 / MinIO |
| Sandbox | Rootless Docker + gVisor; egress proxy (Squid); Vault for secrets |
| VCS / CI | GitHub, branch `task/T-xxx`, GitHub Actions with self-hosted runners |
| Tests | pytest, Vitest, Testcontainers, Playwright; smoke suite tagged `@smoke` |
| Static gates | ruff, mypy, eslint, tsc, Semgrep, gitleaks, pip-audit/npm audit |
| Observability | Langfuse (self-hosted) for agent traces + cost; OpenTelemetry → Prometheus/Grafana/Loki |
| Pilot infra | 2 VMs, Docker Compose, Caddy TLS, Terraform + Ansible |

Escalation paths (pre-approved, Phase 2+): Temporal for orchestration; Firecracker/Kata
for sandbox; Kubernetes for runner pool.
