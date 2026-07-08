# 05 — Security

## Sandbox (per task)
- Real, rootless Docker isolation (T-005): no privileged mode, no docker-socket access,
  read-only base image, tmpfs workspace, CPU/RAM/disk quotas, one internal network per
  ticket, destroyed at ticket close. **Not gVisor** — unavailable on Docker Desktop and
  GitHub-hosted CI runners (disclosed since T-005); a pluggable `SandboxRuntime`
  interface (T-204, `apps/sandbox/src/sandbox/runtime.py`) makes the runtime swappable —
  `DockerRuntime` is the real, live-tested default, a Firecracker/Kata `MicroVMRuntime`
  is built but not live-verified (no reachable hypervisor in this environment).
- Base images pre-baked with toolchains (`apps/sandbox/images/`).
- T-204: a real `HostPool` scheduler admits every sandbox provisioning through a fixed
  pool of logical slots, guaranteeing two different orgs never hold the same slot at
  once (concurrency-tested, 100 rounds) — scoped honestly to one process/host, matching
  today's actual single-runner-VM deployment; a formal escape-test suite (host fs,
  docker socket, cross-org network probes) runs against the real runtime
  (`make escape-test`).

## Network
- Default-deny egress. Proxy allow-list only: package registries, git host, Anthropic
  API, plus (T-204) per-org staff-approved additions layered on top of that base list
  (`org_egress_rules`, `apps/api/src/api/routers/egress.py`) — an org's own additions
  never leak into another org's allow-list.
- Every egress logged with ticket_id. Violation → kill container, ticket → `escalated`.

## Storage
- T-204: per-org artifact storage ACLs via MinIO's own STS `AssumeRole` + policy engine
  (`apps/api/src/api/artifact_storage.py`) — a short-lived credential scoped to
  `orgs/<org_id>/*` is denied by MinIO itself when used against another org's prefix,
  not by a hand-rolled check. Worktree storage gets per-org path scoping + OS
  permissions only, not real disk-level encryption (LUKS/dm-crypt needs host
  provisioning beyond a rootless container) — a disclosed gap, not attempted.

## Credentials
- Per-ticket GitHub App tokens scoped to push `agent/*` branches only.
- Issued and revoked by Vault (or cloud secret manager). Nothing long-lived in containers.
- Agents NEVER receive production credentials. Deploys run from a separate,
  human-approved pipeline (protected environments).

## Code gates on every agent PR (blocking)
- Semgrep (SAST) · gitleaks (secret scan) · pip-audit / npm audit (dependencies)

## Prompt-injection stance
Repo content, tickets and web results are DATA, not instructions. Tool allow-lists per
role + egress proxy bound the blast radius if an agent is manipulated.
