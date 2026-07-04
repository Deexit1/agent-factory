# SPEC-003 — Sandbox Runner

## Goal
Provision an isolated, network-restricted container per task with a git worktree and
scoped credentials; tear down cleanly.

## In scope
- `apps/sandbox`: base image (Python+Node toolchains), provisioning CLI:
  `sandbox up T-123 --repo <url>` / `sandbox down T-123`.
- gVisor runtime, rootless, CPU/RAM/disk limits from config.
- Egress proxy container with allow-list (package registries, git host, Anthropic API);
  all egress logged as `ticket_events` (`kind=tool_call`, `payload.egress=...`).
- Git credential injection: short-lived token, push restricted to `agent/T-123` branch
  (server-side check simulated with a pre-push hook in Phase 1).
- Teardown removes container, worktree, and revokes token.

## Acceptance criteria
1. `sandbox up` yields a container where `curl https://blocked.example.com` fails and
   `pip install requests` succeeds.
2. Push to `main` from inside the sandbox is rejected; push to `agent/T-123` succeeds.
3. Container cannot see host Docker socket or other sandboxes (integration test).
4. `sandbox down` leaves no container, volume, or credential behind.
5. Every egress attempt appears in ticket_events for T-123.
