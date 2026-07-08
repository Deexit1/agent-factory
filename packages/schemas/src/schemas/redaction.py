"""T-202 (SPEC-202 AC2): redact provider API key material before it's persisted
anywhere a human or another service can read it back (TicketEvent payloads, outgoing
orchestrator event bodies). Shared by apps/api and apps/orchestrator — both already
depend on packages/schemas, so this needs no new package.
"""

import re

_KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9\-_]{20,}"),  # Anthropic
    re.compile(r"sk-[A-Za-z0-9]{20,}"),  # OpenAI
]

_REDACTED = "[REDACTED-KEY]"


def scrub(text: str) -> str:
    for pattern in _KEY_PATTERNS:
        text = pattern.sub(_REDACTED, text)
    return text


def scrub_payload(payload: dict[str, object]) -> dict[str, object]:
    """Recursively scrubs string values in a JSON-shaped event/log payload."""
    return {key: _scrub_value(value) for key, value in payload.items()}


def _scrub_value(value: object) -> object:
    if isinstance(value, str):
        return scrub(value)
    if isinstance(value, dict):
        return scrub_payload(value)
    if isinstance(value, list):
        return [_scrub_value(item) for item in value]
    return value
