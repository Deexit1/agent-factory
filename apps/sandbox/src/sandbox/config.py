from dataclasses import dataclass, field
from pathlib import Path

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


def state_dir_for(ticket_id: str) -> Path:
    return STATE_DIR / ticket_id
