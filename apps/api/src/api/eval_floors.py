"""T-202 (SPEC-202 AC5): reads evals/thresholds.yaml directly — a plain static-file
read, not DB access, so it doesn't go through routers/->services/->repositories/'s
DB-layering convention. apps/api reads the file itself rather than importing
orchestrator.evals.loader: apps/api and apps/orchestrator are separate deployables
(docs/01-architecture.md), and that loader pulls in packages/schemas' TaskSpec/
case-loading machinery apps/api has no use for — the wrong dependency direction for a
small YAML read.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


def _find_repo_root(marker: str = "capability_registry.yaml") -> Path:
    """Same rationale as capability_registry.py's identical helper: a fixed
    `.parents[N]` index breaks once this file's depth below the repo root differs
    between the host checkout and the Docker image (which flattens the `apps/api/`
    prefix). Walking up for a marker file present at the repo root in both
    environments works unmodified in both."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / marker).exists():
            return candidate
    raise FileNotFoundError(f"could not locate repo root (no {marker} found above {__file__})")


_REPO_ROOT = _find_repo_root()
_THRESHOLDS_FILE = _REPO_ROOT / "evals" / "thresholds.yaml"


@dataclass(frozen=True)
class ProviderFloor:
    verified: bool
    floor: float | None


def load_provider_floor(agent_role: str, provider: str) -> ProviderFloor:
    """Roles with NO eval-floor concept at all (e.g. "delivery-manager" — no golden
    set exists for it, see evals/thresholds.yaml) have nothing to be "unverified"
    against, so they're never gated: verified=True, floor=None. That's distinct from
    a role that DOES have an eval floor but this specific provider isn't verified for
    it (e.g. dev+openai) — only the latter requires an org's explicit opt-in."""
    if not _THRESHOLDS_FILE.exists():
        return ProviderFloor(verified=True, floor=None)
    raw = yaml.safe_load(_THRESHOLDS_FILE.read_text(encoding="utf-8"))
    role_entry = raw.get(agent_role)
    if role_entry is None:
        return ProviderFloor(verified=True, floor=None)
    provider_entry = role_entry.get("providers", {}).get(provider)
    if provider_entry is None:
        return ProviderFloor(verified=False, floor=None)
    return ProviderFloor(
        verified=not provider_entry.get("not_yet_enforced", True),
        floor=provider_entry.get("floor"),
    )
