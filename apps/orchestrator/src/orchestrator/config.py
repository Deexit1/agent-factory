from dataclasses import dataclass

from schemas import Complexity

from orchestrator.capability_registry import Profile

# docs/06-tech-stack.md: sonnet default, opus for planning/complex, haiku for classification.
# T-105: this is now only the fallback used when no profile was assigned (legacy /
# run_pilot.py callers) — a real dev-agent invocation uses the assigned profile's own
# `model` instead (see model_for below).
_MODEL_BY_COMPLEXITY = {
    Complexity.LOW: "claude-sonnet-5",
    Complexity.MEDIUM: "claude-sonnet-5",
    Complexity.HIGH: "claude-opus-4-8",
}

DEFAULT_TIMEOUT_S = 45 * 60  # SPEC-004: wall-clock timeout, default 45 min


@dataclass(frozen=True)
class DevAgentConfig:
    api_url: str = "http://localhost:8000"
    timeout_s: float = DEFAULT_TIMEOUT_S

    def model_for(self, complexity: Complexity, profile: Profile | None = None) -> str:
        # complexity=high is a safety floor: always escalate to opus regardless of
        # which profile was assigned.
        if complexity is Complexity.HIGH:
            return _MODEL_BY_COMPLEXITY[Complexity.HIGH]
        if profile is not None:
            return profile.model
        return _MODEL_BY_COMPLEXITY[complexity]
