"""Sole owner of provider SDKs (docs/00-vision.md SaaS-readiness rule 2): every LLM
call in the repo goes through `route()` — nothing outside this package imports
`anthropic`/`openai` directly (enforced by scripts/check_llm_router_gate.py, with one
narrow disclosed exception for a key-validation ping — see that script's docstring).

T-102 scope was a skeleton: a role -> model map and one Anthropic call site, using the
process-wide ANTHROPIC_API_KEY. T-103/T-104/T-106 added roles and usage/cost reporting.

T-202 (SPEC-202): real BYOK. `route()` no longer touches the ambient environment at
all — the caller (an orchestrator agent function) fetches an org's key material from
apps/api at run start and passes an ordered `credentials` list in; this package stays
dependency-light and DB/Vault-unaware (docs/09-saas-model.md's "fetched at run start,
held in memory in the runner, passed to the router"). `route()` iterates `credentials`
in order, retrying transient failures per-provider before falling over to the next
credential — the real (agent_role, complexity, org) -> (provider, model, key) routing
SPEC-202 asks for, minus one disclosed skeleton-first trim: `complexity` is accepted
but doesn't yet subdivide model choice within a role (same incrementalism this module
has followed at every prior step).
"""

from dataclasses import dataclass, field

import anthropic
import openai

# provider -> role -> model, per docs/06-tech-stack.md's routing table ("sonnet
# default, opus for planning/complex, haiku for classification & log distillation").
_PROVIDER_ROLE_MODELS: dict[str, dict[str, str]] = {
    "anthropic": {
        "eval-judge": "claude-haiku-4-5-20251001",
        "eval-distiller": "claude-haiku-4-5-20251001",
        "planner": "claude-opus-4-8",
        "delivery-manager": "claude-sonnet-5",
        "review": "claude-sonnet-5",
    },
    "openai": {
        "eval-judge": "gpt-4.1-mini",
        "eval-distiller": "gpt-4.1-mini",
        "planner": "gpt-4.1",
        "delivery-manager": "gpt-4.1",
        "review": "gpt-4.1",
    },
}

# Approximate $/million tokens (input, output). Good enough for cost_ledger's
# unit-economics tracking; not a substitute for reconciling against real provider
# invoices. Update alongside _PROVIDER_ROLE_MODELS if pricing changes.
_PRICING_PER_MILLION_TOKENS: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-haiku-4-5-20251001"): (1.0, 5.0),
    ("anthropic", "claude-sonnet-5"): (3.0, 15.0),
    ("anthropic", "claude-opus-4-8"): (15.0, 75.0),
    ("openai", "gpt-4.1"): (2.0, 8.0),
    ("openai", "gpt-4.1-mini"): (0.4, 1.6),
}

# claude-opus-4-8 rejects `temperature` outright ("deprecated for this model" - a real
# 400 discovered running the planner eval set for real); haiku still accepts and uses
# it for judge/distiller reproducibility (AC4: two runs must differ by < 2%).
_MODELS_WITHOUT_TEMPERATURE = {"claude-opus-4-8"}

# HTTP status codes worth retrying on the same provider before falling over to the
# next one in the org's fallback order.
_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504, 529}


class UnknownRole(Exception):
    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"no model routing configured for role {role!r}")


class UnknownProvider(Exception):
    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(f"no model routing configured for provider {provider!r}")


class NoCredentialsProvided(Exception):
    pass


@dataclass(frozen=True)
class ProviderCredential:
    provider: str
    api_key: str


@dataclass(frozen=True)
class RouteAttempt:
    provider: str
    model: str
    error: str | None  # None only for the attempt that ultimately succeeded


@dataclass(frozen=True)
class RouteResult:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float
    attempts: list[RouteAttempt] = field(default_factory=list)


class AllProvidersFailed(Exception):
    """Every credential in the org's fallback order was tried and failed."""

    def __init__(self, attempts: list[RouteAttempt]) -> None:
        self.attempts = attempts
        super().__init__(f"all {len(attempts)} provider(s) failed")


def _cost_usd(provider: str, model: str, tokens_in: int, tokens_out: int) -> float:
    input_price, output_price = _PRICING_PER_MILLION_TOKENS.get((provider, model), (0.0, 0.0))
    return (tokens_in * input_price + tokens_out * output_price) / 1_000_000


def _is_transient(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None)
    if status_code in _TRANSIENT_STATUS_CODES:
        return True
    return isinstance(
        exc,
        (
            anthropic.APITimeoutError,
            anthropic.APIConnectionError,
            openai.APITimeoutError,
            openai.APIConnectionError,
        ),
    )


def _call_anthropic(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    timeout_s: float,
) -> tuple[str, int, int]:
    client = anthropic.Anthropic(api_key=api_key, timeout=timeout_s)
    kwargs: dict[str, object] = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if model not in _MODELS_WITHOUT_TEMPERATURE:
        kwargs["temperature"] = temperature
    response = client.messages.create(**kwargs)  # type: ignore[call-overload]
    block = response.content[0]
    text = block.text if hasattr(block, "text") else str(block)
    return text, response.usage.input_tokens, response.usage.output_tokens


def _call_openai(
    *,
    api_key: str,
    model: str,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
    timeout_s: float,
) -> tuple[str, int, int]:
    client = openai.OpenAI(api_key=api_key, timeout=timeout_s)
    full_messages: list[dict[str, str]] = [{"role": "system", "content": system}, *messages]
    response = client.chat.completions.create(
        model=model,
        messages=full_messages,  # type: ignore[arg-type]
        max_tokens=max_tokens,
        temperature=temperature,
    )
    text = response.choices[0].message.content or ""
    usage = response.usage
    tokens_in = usage.prompt_tokens if usage else 0
    tokens_out = usage.completion_tokens if usage else 0
    return text, tokens_in, tokens_out


_ADAPTERS = {"anthropic": _call_anthropic, "openai": _call_openai}


def route(
    role: str,
    *,
    credentials: list[ProviderCredential],
    complexity: str = "medium",
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float = 0,
    timeout_s: float = 60.0,
    max_retries_per_provider: int = 1,
) -> RouteResult:
    """Send one message-completion request for `role`, trying each credential in
    `credentials` (the org's configured fallback order) until one succeeds.

    `complexity` is accepted per SPEC-202's (agent_role, complexity, org) -> (provider,
    model, key) signature but doesn't yet subdivide model choice within a role — a
    disclosed v1 scope trim, not an oversight.
    """
    del complexity
    if not credentials:
        raise NoCredentialsProvided("route() requires at least one ProviderCredential")

    attempts: list[RouteAttempt] = []
    for credential in credentials:
        provider = credential.provider
        role_models = _PROVIDER_ROLE_MODELS.get(provider)
        if role_models is None:
            raise UnknownProvider(provider)
        if role not in role_models:
            raise UnknownRole(role)
        model = role_models[role]
        adapter = _ADAPTERS[provider]

        last_error: Exception | None = None
        for attempt_no in range(max_retries_per_provider + 1):
            try:
                text, tokens_in, tokens_out = adapter(
                    api_key=credential.api_key,
                    model=model,
                    system=system,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    timeout_s=timeout_s,
                )
            except Exception as exc:  # noqa: BLE001 — any SDK error means "this attempt failed"
                last_error = exc
                if attempt_no < max_retries_per_provider and _is_transient(exc):
                    continue
                break
            else:
                attempts.append(RouteAttempt(provider=provider, model=model, error=None))
                return RouteResult(
                    text=text,
                    provider=provider,
                    model=model,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=_cost_usd(provider, model, tokens_in, tokens_out),
                    attempts=attempts,
                )

        assert last_error is not None
        attempts.append(RouteAttempt(provider=provider, model=model, error=str(last_error)))

    raise AllProvidersFailed(attempts)


__all__ = [
    "route",
    "ProviderCredential",
    "RouteAttempt",
    "RouteResult",
    "AllProvidersFailed",
    "UnknownRole",
    "UnknownProvider",
    "NoCredentialsProvided",
]
