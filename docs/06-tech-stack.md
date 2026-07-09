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
| Sandbox | Rootless Docker (real, default); egress proxy (Squid) with a per-org allow-list; Vault for secrets; pluggable runtime interface (`apps/sandbox/src/sandbox/runtime.py`) — a Firecracker/Kata `MicroVMRuntime` is built but not live-verified (see below) |
| VCS / CI | GitHub, branch `task/T-xxx`, GitHub Actions with self-hosted runners |
| Tests | pytest, Vitest, Testcontainers, Playwright; smoke suite tagged `@smoke` |
| Static gates | ruff, mypy, eslint, tsc, Semgrep, gitleaks, pip-audit/npm audit |
| Evals | Golden-set harness (`make eval`) — promptfoo-style YAML cases + custom scorer, runs in CI on `prompts/**` or routing diffs |
| Observability | Langfuse (Cloud, Phase-2 pragmatic choice — see T-101 changelog; self-hosting is a separate future migration) for agent traces + cost; OpenTelemetry → Prometheus/Grafana/Loki |
| Merge safety | Home-grown FIFO merge queue (T-107, `apps/orchestrator/src/orchestrator/merge_queue.py`) — real rebase-and-retest + conflict bounce, required for all `agent/*` PRs. Deliberately not GitHub's native merge-queue feature or a bors-style bot (would need GitHub org/repo admin configuration this repo doesn't assume); revisit once that's actually available. |
| LLM routing | `packages/llm_router` (thin custom router, LiteLLM-style): role+complexity+org → provider/model; sole owner of provider SDKs |
| Tenant secrets (BYOK) | Vault KV `tenants/<org>/llm/<provider>`; keys never in DB/logs/traces/sandboxes |
| Repo delivery | GitHub App (contents + PRs on selected repos), per-ticket installation tokens |
| Billing | Razorpay (subscriptions + metered addons) — swapped from Stripe at T-205, human-approved this session; see the implementation-status note below |
| Multi-tenant sandbox | Firecracker/Kata microVMs — REQUIRED at multi-tenant GA (gVisor allowed for single-tenant/dev and closed beta only). As of T-204: real org-aware egress, per-org artifact storage ACLs (MinIO), an in-process scheduler enforcing no cross-org co-location, and a pre-warmed provisioning pool all land on top of the real Docker runtime; the actual Firecracker/Kata hypervisor swap itself is not live-verified in this environment |

## Implementation status notes (do not change the locked rows above without a doc PR)
- **LLM routing / Tenant secrets (BYOK) rows — real as of T-202.** `packages/llm_router`
  now takes `(agent_role, complexity, org-fetched credentials)` and does real
  provider fallover/retries across Anthropic + OpenAI. Vault is wired for real in
  local/CI (`docker-compose.yml`'s `vault` service, `hashicorp/vault:1.17`,
  **dev-mode only** — in-memory, root-token auth, no persistence). Real production
  Vault topology (raft storage, auto-unseal, AppRole auth, TLS) is a deploy-time
  concern, not built here — same standing as MinIO standing in for real S3 in this
  same table.
- **Onboarding-gate enforcement (post-T-206, `apps/web/src/App.tsx`) blocks board
  access until an org has accepted the ToS, added a BYOK key, and connected a repo —
  and the last two of those need live vendor infrastructure this environment doesn't
  have.** `PROVIDER_KEY_VALIDATION_SKIP` (`provider_key_service.validate_key`) and
  `FIXTURE_REPO_PROVISIONING` (`github_repo_service.provision_repo`) are two new,
  narrowly-scoped dev/CI-only bypass flags — same precedent as `AUTH_DEV_MODE`
  (explicit, default-off, `.env.example`-documented, and each additionally requires
  `AUTH_DEV_MODE=true` to take effect as defense-in-depth). The fixture-repo path
  creates a `Repo` row with a clearly-marked `github_full_name` (`fixture/<name>`) and
  never calls `github_app_client`. Neither flag weakens anything for a real deployment;
  both are off unless explicitly and deliberately turned on alongside dev mode.
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
- **Sandbox isolation row — real as of T-204** for: a pluggable `SandboxRuntime`
  interface (`apps/sandbox/src/sandbox/runtime.py`) with `DockerRuntime` (today's real,
  fully-tested mechanism, unchanged behavior) as the live default; org-aware egress
  (`org_egress_rules` table, staff-approval-gated additions on top of the base
  allow-list, `apps/api/src/api/routers/egress.py`); a real, concurrency-tested
  `HostPool` scheduler (`apps/sandbox/src/sandbox/scheduler.py`) that gates every real
  sandbox provisioning through a fixed pool of logical slots so two different orgs can
  never hold the same slot at once; a pre-warmed `SandboxPool`
  (`apps/sandbox/src/sandbox/pool.py`) that keeps idle network+proxy pairs ready and
  live-reconfigures Squid's allow-list per org at hand-out time; per-org MinIO artifact
  storage ACLs proven against MinIO's own STS/policy engine
  (`apps/api/src/api/artifact_storage.py`); a formal escape-test suite (host fs,
  docker-socket, cross-org network — `apps/sandbox/tests/integration/
  test_escape_probes.py`, `make escape-test`); and — closing the gap disclosed since
  T-105/106/107 — `apps/orchestrator`'s dev-agent run now actually executes inside this
  isolated, org-scoped sandbox (`orchestrator/sandbox_runner.py`'s
  `SandboxClaudeCodeRunner`) when opted into (`scripts/run_pilot.py --sandbox`); the
  bare-host-subprocess path (`SubprocessClaudeCodeRunner`) remains the default,
  unaffected. **Not yet real:** any actual Firecracker/Kata microVM boot
  (`MicroVMRuntime` is built against the real CLI shapes and subprocess-fault-injection
  tested only — no hypervisor is reachable in this environment, same disclosed category
  as T-202/T-203's live-infra gaps); true multi-host/multi-process scheduler
  coordination (`HostPool` enforces its guarantee correctly but only within one
  process/host — today's actual single-runner-VM deployment shape, see the Phase-2
  activation note below); real disk-level encryption for worktree storage (per-org path
  scoping + OS permissions only, not LUKS/dm-crypt).
- **Billing row — real as of T-205, vendor swapped from Stripe to Razorpay** (human
  decision this session; no live account existed for either, so this was a build-time,
  not migration-time, choice). Real: a hand-rolled `httpx` REST client
  (`apps/api/src/api/razorpay_client.py`, sole owner of `api.razorpay.com` per
  `scripts/check_razorpay_gate.py`, same discipline as `github_app_client.py`) covering
  customer/subscription/addon creation and HMAC webhook-signature verification; three
  placeholder tiers (`free`/`starter`/`team`, `apps/api/src/api/billing_plans.py`) with
  a pure `compute_invoice` function; an idempotent nightly metering job
  (`apps/api/scripts/run_billing_metering.py`, `make billing-meter`) that records real
  usage from `agent_runs`/`usage_events`/`ticket_events` into a `billing_usage_reports`
  ledger and bills overage as real Razorpay addons once a billing period elapses;
  deferred-to-period-end plan downgrades mapping straight onto `orgs.max_parallel_
  tickets` (T-201's one enforced quota); a real dunning path (`POST /webhooks/razorpay`)
  reusing T-203's `disconnect_repo` force-block precedent verbatim (`system:billing` is
  the second disclosed exception in `state_machine.py`'s `_SYSTEM_BLOCK_ACTORS`); and a
  free-tier hard-usage-cap guard extending T-201's `org_at_quota` pattern. **Not yet
  real:** no live Razorpay account reachable in this environment — every call is
  respx-tested at the HTTP boundary only, same standing as T-202/T-203/T-204's
  equivalent live-infra gaps; the three tiers' ₹ figures are explicit placeholders
  pending a real pricing decision; no new `apps/web` UI (matches T-201–204's own
  precedent — AC5's dashboard/Razorpay reconciliation is proven at the API layer); seats
  are stored but not enforced; no real cron/scheduler daemon runs the metering job
  (external trigger only, matching `provider_health_service.py`'s own disclosed
  standing).

## Phase-2 activations (pre-approved escalation paths)
- **Runner pool → Kubernetes** (EKS/GKE + autoscaling runners) WHEN sustained parallel
  tickets > 5. Until then: second runner VM. `HostPool`'s scheduler (T-204) is scoped to
  exactly this shape — one process, one host — and its cross-host coordination gap is
  deferred to whenever this activation fires, not built preemptively.
- **Orchestration → Temporal** WHEN LangGraph checkpoint recovery fails us twice in
  production or ticket volume > 50/day. Not before — migration is expensive.
- **Sandbox → Firecracker/Kata** WHEN agents get access to repos with sensitive data
  classifications (same trigger condition the locked table's "Multi-tenant sandbox" row
  states as "at multi-tenant GA" — both describe the same event). gVisor remains fine
  for the pilot repos. T-204 built the pluggable runtime interface and every
  org-isolation mechanism around it ahead of this activation firing, so the swap itself
  (once a real hypervisor is available) is a `SandboxConfig.runtime` flag flip, not a
  from-scratch build.
