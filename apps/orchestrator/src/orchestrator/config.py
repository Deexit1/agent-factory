import os
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

# T-109: a scenario-level cap (planner + DM + every dev/review agent run combined),
# distinct from a single ticket's own budget_usd. Fixture-driven scenarios (no real
# LLM calls) cost fractions of a cent, so this default is generous headroom, not a
# tight bound - it exists to catch a scenario that unexpectedly starts spending for
# real, not to tune day-to-day cost.
DEFAULT_SCENARIO_COST_CAP_USD = 1.0


def scenario_cost_cap_usd() -> float:
    raw = os.environ.get("SCENARIO_COST_CAP_USD")
    return float(raw) if raw else DEFAULT_SCENARIO_COST_CAP_USD


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
