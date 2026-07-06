"""Sole owner of provider SDKs (docs/00-vision.md SaaS-readiness rule 2): every LLM
call in the repo goes through `route()` — nothing outside this package imports
`anthropic`/`openai` directly (enforced by scripts/check_llm_router_gate.py).

T-102 scope was a skeleton: a role -> model map (docs/06-tech-stack.md's routing
table) and one Anthropic call site, using the process-wide ANTHROPIC_API_KEY. T-103
adds a "planner" role and usage/cost reporting (needed to record real agent_runs/
cost_ledger rows). T-104 adds a "delivery-manager" role (sonnet-class) and a
claude-sonnet-5 pricing entry (missing until now — no prior caller needed it). Still
no per-org BYOK key selection, fallback ordering or retries; that's SPEC-202/T-202.
"""

from dataclasses import dataclass

import anthropic

# role -> model, per docs/06-tech-stack.md ("sonnet default, opus for planning/complex,
# haiku for classification & log distillation").
_ROLE_MODELS = {
    "eval-judge": "claude-haiku-4-5-20251001",
    "eval-distiller": "claude-haiku-4-5-20251001",
    "planner": "claude-opus-4-8",
    "delivery-manager": "claude-sonnet-5",
}

# Approximate $/million tokens (input, output). Good enough for cost_ledger's
# unit-economics tracking; not a substitute for reconciling against real provider
# invoices. Update alongside _ROLE_MODELS if pricing changes.
_PRICING_PER_MILLION_TOKENS: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5-20251001": (1.0, 5.0),
    "claude-sonnet-5": (3.0, 15.0),
    "claude-opus-4-8": (15.0, 75.0),
}

# claude-opus-4-8 rejects `temperature` outright ("deprecated for this model" - a real
# 400 discovered running the planner eval set for real); haiku still accepts and uses
# it for judge/distiller reproducibility (AC4: two runs must differ by < 2%).
_MODELS_WITHOUT_TEMPERATURE = {"claude-opus-4-8"}


class UnknownRole(Exception):
    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"no model routing configured for role {role!r}")


@dataclass(frozen=True)
class RouteResult:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_usd: float


def _cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    input_price, output_price = _PRICING_PER_MILLION_TOKENS.get(model, (0.0, 0.0))
    return (tokens_in * input_price + tokens_out * output_price) / 1_000_000


def route(
    role: str,
    *,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float = 0,
) -> RouteResult:
    """Send one message-completion request for `role` and return the reply + usage."""
    if role not in _ROLE_MODELS:
        raise UnknownRole(role)
    model = _ROLE_MODELS[role]

    client = anthropic.Anthropic()
    if model in _MODELS_WITHOUT_TEMPERATURE:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=messages,  # type: ignore[arg-type]
        )
    else:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,  # type: ignore[arg-type]
        )
    block = response.content[0]
    text = block.text if hasattr(block, "text") else str(block)
    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    return RouteResult(
        text=text,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=_cost_usd(model, tokens_in, tokens_out),
    )


__all__ = ["route", "RouteResult", "UnknownRole"]
