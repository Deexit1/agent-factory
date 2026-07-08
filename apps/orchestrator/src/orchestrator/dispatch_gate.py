"""T-202 (SPEC-202): shared BYOK dispatch gate. Every LLM-calling agent entry point
(planner/delivery-manager/review/dev) calls this before route()/claude_runner.run() —
never a background pause, a same-request check (AC6's "paused within 60s" is satisfied
by construction: every dispatch re-fetches fresh, so a revoked key or a newly-required
opt-in takes effect on the very next call, not on some polling interval).
"""

from dataclasses import dataclass

from llm_router import ProviderCredential

from orchestrator.api_client import ApiClient


@dataclass(frozen=True)
class DispatchDecision:
    allowed: bool
    credentials: list[ProviderCredential]
    reason: str | None = None


def resolve_dispatch(api: ApiClient, *, org_id: str, agent_role: str) -> DispatchDecision:
    raw_credentials = api.get_runtime_keys(org_id)
    if not raw_credentials:
        return DispatchDecision(
            allowed=False, credentials=[], reason="no active provider key configured for this org"
        )

    primary_provider = raw_credentials[0]["provider"]
    floor = api.get_eval_floor(org_id, agent_role=agent_role, provider=primary_provider)
    if not floor["verified"] and not floor["opted_in"]:
        return DispatchDecision(
            allowed=False,
            credentials=[],
            reason=(
                f"{primary_provider} has no verified eval floor for {agent_role!r} and the "
                "org has not opted into unverified quality"
            ),
        )

    return DispatchDecision(
        allowed=True,
        credentials=[ProviderCredential(**c) for c in raw_credentials],
    )


__all__ = ["DispatchDecision", "resolve_dispatch"]
