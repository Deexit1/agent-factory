from schemas import Complexity

from orchestrator.capability_registry import Profile
from orchestrator.config import DevAgentConfig

_FRONTEND_PROFILE = Profile(
    id="dev-frontend",
    model="claude-sonnet-5",
    base_image="agent-factory-sandbox:latest",
    skills=("frontend",),
    max_parallel=2,
)

_DEVOPS_PROFILE = Profile(
    id="dev-devops",
    model="claude-opus-4-8",
    base_image="agent-factory-sandbox:latest",
    skills=("devops",),
    max_parallel=1,
)


def test_model_for_uses_legacy_complexity_map_when_no_profile_given() -> None:
    config = DevAgentConfig()
    assert config.model_for(Complexity.LOW) == "claude-sonnet-5"
    assert config.model_for(Complexity.MEDIUM) == "claude-sonnet-5"
    assert config.model_for(Complexity.HIGH) == "claude-opus-4-8"


def test_model_for_uses_the_profiles_own_model_when_given() -> None:
    config = DevAgentConfig()
    assert config.model_for(Complexity.LOW, _FRONTEND_PROFILE) == "claude-sonnet-5"
    assert config.model_for(Complexity.LOW, _DEVOPS_PROFILE) == "claude-opus-4-8"


def test_model_for_high_complexity_always_escalates_to_opus_regardless_of_profile() -> None:
    config = DevAgentConfig()
    assert config.model_for(Complexity.HIGH, _FRONTEND_PROFILE) == "claude-opus-4-8"
