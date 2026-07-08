from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

DEFAULT_ALLOWED_DOMAINS: list[str] = [
    "pypi.org",
    "files.pythonhosted.org",
    "registry.npmjs.org",
    "github.com",
    "codeload.github.com",
    "api.github.com",
    "api.anthropic.com",
]

STATE_DIR = Path.home() / ".agent-factory-sandbox"


@dataclass(frozen=True)
class SandboxLimits:
    cpus: float = 2.0
    memory: str = "2g"
    workspace_size: str = "1g"


@dataclass(frozen=True)
class SandboxConfig:
    image: str = "agent-factory-sandbox:latest"
    proxy_image: str = "ubuntu/squid:latest"
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    allowed_domains: list[str] = field(default_factory=lambda: list(DEFAULT_ALLOWED_DOMAINS))
    api_url: str = "http://localhost:8000"
    # T-204: pluggable execution backend. "docker" is today's real, live-tested
    # mechanism (DockerRuntime); "microvm" selects MicroVMRuntime, built against
    # Firecracker/Kata's real CLI shapes but not live-verified in this environment (no
    # reachable hypervisor) — see runtime.py's module docstring.
    runtime: Literal["docker", "microvm"] = "docker"


def state_dir_for(ticket_id: str) -> Path:
    return STATE_DIR / ticket_id


def org_state_dir_for(org_id: str, ticket_id: str) -> Path:
    """T-204 (SPEC-204 AC5, worktree-storage half): per-org path scoping for the pool/
    orchestrator-wiring path, kept separate from `state_dir_for` (used by `cli.py`'s
    existing single-tenant dogfood flow, which this ticket leaves untouched). This is
    OS-directory-permission-level scoping, not real disk-level encryption (LUKS/
    dm-crypt needs host provisioning outside a rootless container) — a disclosed gap,
    not attempted here.
    """
    return STATE_DIR / "orgs" / org_id / ticket_id
