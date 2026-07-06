"""Shared JSON-from-LLM-reply parsing — models sometimes wrap JSON in a ```json ... ```
fence despite instructions not to. Used by both eval scoring (orchestrator/evals/judge.py)
and production agents (orchestrator/agents/planner.py)."""

import json
import re
from typing import Any

_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    fenced = _CODE_FENCE_RE.search(text)
    payload = fenced.group(1) if fenced else text
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object, got {type(result).__name__}")
    return result
