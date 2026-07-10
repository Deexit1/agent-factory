"""T-211: dispatch_gate.resolve_dispatch had zero dedicated tests before this — every
prior agent integration test only ever exercised the seeded default org via the
platform-fallback key (no BYOK configured), so the "no active provider key" and
"unverified eval floor, not opted in" refusal branches were never actually asserted
anywhere. A fake ApiClient double stands in for the real HTTP round-trip — resolve_dispatch
only ever calls get_runtime_keys/get_eval_floor, both plain org-parametric methods.
"""

from typing import Any

from llm_router import ProviderCredential

from orchestrator.dispatch_gate import resolve_dispatch


class _FakeApiClient:
    def __init__(
        self,
        *,
        runtime_keys: dict[str, list[dict[str, str]]],
        eval_floors: dict[tuple[str, str, str], dict[str, Any]],
    ) -> None:
        self._runtime_keys = runtime_keys
        self._eval_floors = eval_floors
        self.runtime_keys_calls: list[str] = []
        self.eval_floor_calls: list[tuple[str, str, str]] = []

    def get_runtime_keys(self, org_id: str) -> list[dict[str, str]]:
        self.runtime_keys_calls.append(org_id)
        return self._runtime_keys.get(org_id, [])

    def get_eval_floor(self, org_id: str, *, agent_role: str, provider: str) -> dict[str, Any]:
        key = (org_id, agent_role, provider)
        self.eval_floor_calls.append(key)
        return self._eval_floors[key]


def test_allowed_when_a_key_exists_and_the_floor_is_verified() -> None:
    api = _FakeApiClient(
        runtime_keys={"org-a": [{"provider": "anthropic", "api_key": "sk-ant-fake"}]},
        eval_floors={("org-a", "dev", "anthropic"): {"verified": True, "opted_in": False}},
    )

    decision = resolve_dispatch(api, org_id="org-a", agent_role="dev")  # type: ignore[arg-type]

    assert decision.allowed is True
    assert decision.credentials == [ProviderCredential(provider="anthropic", api_key="sk-ant-fake")]
    assert decision.reason is None


def test_allowed_when_the_floor_is_unverified_but_the_org_opted_in() -> None:
    api = _FakeApiClient(
        runtime_keys={"org-a": [{"provider": "openai", "api_key": "sk-fake"}]},
        eval_floors={("org-a", "dev", "openai"): {"verified": False, "opted_in": True}},
    )

    decision = resolve_dispatch(api, org_id="org-a", agent_role="dev")  # type: ignore[arg-type]

    assert decision.allowed is True


def test_refused_when_no_active_provider_key_configured() -> None:
    api = _FakeApiClient(runtime_keys={}, eval_floors={})

    decision = resolve_dispatch(api, org_id="org-with-no-key", agent_role="dev")  # type: ignore[arg-type]

    assert decision.allowed is False
    assert decision.credentials == []
    assert decision.reason == "no active provider key configured for this org"
    # No key at all means the eval-floor check never fires — nothing to check a floor for.
    assert api.eval_floor_calls == []


def test_refused_when_floor_unverified_and_not_opted_in() -> None:
    api = _FakeApiClient(
        runtime_keys={"org-a": [{"provider": "anthropic", "api_key": "sk-ant-fake"}]},
        eval_floors={("org-a", "planner", "anthropic"): {"verified": False, "opted_in": False}},
    )

    decision = resolve_dispatch(api, org_id="org-a", agent_role="planner")  # type: ignore[arg-type]

    assert decision.allowed is False
    assert decision.credentials == []
    assert "anthropic" in (decision.reason or "")
    assert "planner" in (decision.reason or "")


def test_only_the_primary_providers_floor_is_checked() -> None:
    """resolve_dispatch checks the FIRST credential's provider only — a documented,
    existing simplification (not something this test set changes), pinned here so a
    future refactor can't silently start checking every fallback provider's floor
    without a deliberate decision."""
    api = _FakeApiClient(
        runtime_keys={
            "org-a": [
                {"provider": "anthropic", "api_key": "sk-ant-fake"},
                {"provider": "openai", "api_key": "sk-fake"},
            ]
        },
        eval_floors={("org-a", "dev", "anthropic"): {"verified": True, "opted_in": False}},
    )

    decision = resolve_dispatch(api, org_id="org-a", agent_role="dev")  # type: ignore[arg-type]

    assert decision.allowed is True
    assert api.eval_floor_calls == [("org-a", "dev", "anthropic")]


def test_different_orgs_are_independent() -> None:
    """The whole point of T-211: two orgs' dispatch decisions never leak into each
    other, whether that's via a shared default org_id or otherwise."""
    api = _FakeApiClient(
        runtime_keys={"org-a": [{"provider": "anthropic", "api_key": "sk-ant-a"}]},
        eval_floors={("org-a", "dev", "anthropic"): {"verified": True, "opted_in": False}},
    )

    allowed = resolve_dispatch(api, org_id="org-a", agent_role="dev")  # type: ignore[arg-type]
    refused = resolve_dispatch(api, org_id="org-b", agent_role="dev")  # type: ignore[arg-type]

    assert allowed.allowed is True
    assert refused.allowed is False
    assert api.runtime_keys_calls == ["org-a", "org-b"]
