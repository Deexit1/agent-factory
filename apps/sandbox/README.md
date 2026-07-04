# apps/sandbox

Per-task sandbox runner (SPEC-003): an isolated, network-restricted container with a
git checkout scoped to `agent/<ticket_id>`, a default-deny egress proxy, and short-lived
push credentials. See [docs/05-security.md](../../docs/05-security.md) and
[docs/06-tech-stack.md](../../docs/06-tech-stack.md).

```bash
pip install -e ".[dev]"
docker build -t agent-factory-sandbox:latest -f images/Dockerfile images/
docker pull ubuntu/squid:latest

sandbox up T-123 --repo https://github.com/org/repo.git [--base-branch main] [--api-url http://localhost:8000]
sandbox down T-123
```

## What's real here (Phase 1) vs. the target design

- **Container isolation**: real — rootless-style flags, `--read-only` rootfs, tmpfs
  workspace, CPU/RAM limits, no docker socket, one internal docker network per ticket
  (so sandboxes can't see each other). **Not** gVisor (`runsc`) — unavailable on Docker
  Desktop and not preinstalled on GitHub-hosted CI runners. The container runtime is
  swappable; drop in gVisor on a host that has it without changing this code.
- **Egress proxy**: real — a Squid container with a default-deny allow-list
  (`config.DEFAULT_ALLOWED_DOMAINS`), every request logged and forwarded to
  `POST /tickets/{id}/events` (`kind=tool_call`, `payload.egress=...`).
- **Push restriction**: real, but simulated client-side per SPEC-003's own Phase-1 note —
  a pre-push hook in the checkout rejects any ref except `refs/heads/agent/<ticket_id>`.
  A real GitHub branch-protection rule replaces this later.
- **Credential issuing**: `credential_broker.py` is a local stub — it mints/revokes a
  random token with the same issue/revoke shape a real integration would have, but it's
  not Vault and not a real GitHub App token. Swap this module, not its callers, when
  real Vault + GitHub App wiring lands.

## Layout

- `images/Dockerfile` — base sandbox image (Python 3.12 + Node 20)
- `hooks/pre-push` — installed into every checkout; reads `AGENT_FACTORY_TICKET_ID`
- `src/sandbox/` — `cli.py` (up/down), `docker_runtime.py`, `egress_proxy.py`,
  `credential_broker.py`, `worktree.py`, `egress_forwarder.py`, `events_client.py`
- `tests/unit` — pure logic (config, allow-list rendering, credential broker, log parsing)
- `tests/integration` — real Docker; covers all five SPEC-003 acceptance criteria
