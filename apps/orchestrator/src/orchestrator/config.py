from dataclasses import dataclass

from schemas import Complexity

# docs/06-tech-stack.md: sonnet default, opus for planning/complex, haiku for classification.
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

    def model_for(self, complexity: Complexity) -> str:
        return _MODEL_BY_COMPLEXITY[complexity]
