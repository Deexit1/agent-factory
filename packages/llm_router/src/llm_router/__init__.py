"""Sole owner of provider SDKs (docs/00-vision.md SaaS-readiness rule 2): every LLM
call in the repo goes through `route()` — nothing outside this package imports
`anthropic`/`openai` directly (enforced by scripts/check_llm_router_gate.py).

T-102 scope is a skeleton: a role -> model map (docs/06-tech-stack.md's routing table)
and one Anthropic call site, using the process-wide ANTHROPIC_API_KEY. Per-org BYOK key
selection, fallback ordering and retries are SPEC-202/T-202 — not built here.
"""

import anthropic

# role -> model, per docs/06-tech-stack.md ("sonnet default, opus for planning/complex,
# haiku for classification & log distillation"). Only eval-judge/eval-distiller route
# through here today; more roles are added as callers migrate off direct SDK use.
_ROLE_MODELS = {
    "eval-judge": "claude-haiku-4-5-20251001",
    "eval-distiller": "claude-haiku-4-5-20251001",
}


class UnknownRole(Exception):
    def __init__(self, role: str) -> None:
        self.role = role
        super().__init__(f"no model routing configured for role {role!r}")


def route(
    role: str,
    *,
    system: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float = 0,
) -> str:
    """Send one message-completion request for `role` and return the reply text."""
    if role not in _ROLE_MODELS:
        raise UnknownRole(role)

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=_ROLE_MODELS[role],
        max_tokens=max_tokens,
        temperature=temperature,
        system=system,
        messages=messages,  # type: ignore[arg-type]
    )
    block = response.content[0]
    return block.text if hasattr(block, "text") else str(block)


__all__ = ["route", "UnknownRole"]
