# SPEC-204 — Tenant Sandbox Isolation (VM-grade)

## Goal
Upgrade sandbox isolation from gVisor to Firecracker/Kata for multi-tenant operation,
with per-org network and storage separation.

## In scope
- Runner pool executing task sandboxes as microVMs (Kata Containers or Firecracker via
  containerd); pooled pre-warmed VMs to keep boot < 30s.
- Per-org egress policy: base allow-list + org-approved additions (platform-staff
  approval flow); per-org egress logs.
- Storage: per-org encrypted volumes for worktrees/artifacts; no shared scratch.
- Scheduling: no two orgs on the same VM ever; per-org concurrency from SPEC-201 quotas.
- Fallback: single-tenant/dev environments may still run gVisor via config flag.

## Acceptance criteria
1. Escape-test suite (host fs, docker socket, other-VM network probes) passes on the
   microVM runtime.
2. Two orgs' concurrent tasks never co-locate on one VM (scheduler property test, 100
   runs).
3. Org-specific egress addition works only after staff approval and applies only to
   that org.
4. Pre-warmed pool keeps p95 sandbox-ready time < 30s under the load test.
5. Artifacts of org A are unreadable with org B credentials (storage ACL test).
