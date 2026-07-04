# 05 — Security

## Sandbox (per task)
- Rootless Docker + gVisor runtime; no privileged mode; read-only base image;
  tmpfs workspace; CPU/RAM/disk quotas; destroyed at ticket close.
- Base images pre-baked with toolchains (`apps/sandbox/images/`).

## Network
- Default-deny egress. Proxy allow-list only: package registries, git host, Anthropic API.
- Every egress logged with ticket_id. Violation → kill container, ticket → `escalated`.

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
