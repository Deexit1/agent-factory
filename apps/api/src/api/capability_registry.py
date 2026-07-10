"""Loads capability_registry.yaml (SPEC-103) — read here to enforce per-profile/
per-repo capacity during a `ready -> in_progress` transition. Also read by
apps/orchestrator's own small loader so the Delivery Manager can enumerate eligible
profiles; the two loaders are intentionally not shared code (separate deployables,
same small-duplication precedent as orchestrator/json_utils.py from T-103)."""

from dataclasses import dataclass
from pathlib import Path

import yaml


def _find_repo_root(marker: str = "capability_registry.yaml") -> Path:
    """A fixed `.parents[N]` index breaks the moment this file's depth below the repo
    root differs between environments — which it does here: on the host this file
    lives at `apps/api/src/api/capability_registry.py` (4 parents up to repo root),
    but the Docker image (`apps/api/Dockerfile`) copies `apps/api/src` straight to
    `/app/src`, flattening the `apps/api/` prefix (3 parents up to `/app`, which is
    where the Dockerfile also copies this same marker file). Walking up for the
    marker itself works unmodified in both."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / marker).exists():
            return candidate
    raise FileNotFoundError(f"could not locate repo root (no {marker} found above {__file__})")


_REPO_ROOT = _find_repo_root()
DEFAULT_REGISTRY_PATH = _REPO_ROOT / "capability_registry.yaml"


@dataclass(frozen=True)
class Profile:
    id: str
    model: str
    base_image: str
    skills: tuple[str, ...]
    max_parallel: int


@dataclass(frozen=True)
class CapabilityRegistry:
    repo_concurrency_limit: int
    profiles: dict[str, Profile]


def load_registry(path: Path = DEFAULT_REGISTRY_PATH) -> CapabilityRegistry:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    profiles = {
        profile_id: Profile(
            id=profile_id,
            model=entry["model"],
            base_image=entry["base_image"],
            skills=tuple(entry.get("skills", [])),
            max_parallel=int(entry["max_parallel"]),
        )
        for profile_id, entry in raw["profiles"].items()
    }
    return CapabilityRegistry(
        repo_concurrency_limit=int(raw["repo_concurrency_limit"]), profiles=profiles
    )
