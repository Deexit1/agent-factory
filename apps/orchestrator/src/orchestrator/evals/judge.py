"""Haiku-class rubric judge, shared by every eval set (SPEC-101).

Temperature 0 for reproducibility (AC4: two runs on identical input must differ by
< 2%). Real implementation calls the Anthropic API directly - unlike the dev/distiller
agents, the judge has no production counterpart to reuse, so this is eval-only code.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

_JUDGE_MODEL = "claude-haiku-4-5-20251001"
_MAX_TOKENS = 300
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Haiku sometimes wraps JSON in a ```json ... ``` fence despite instructions not to."""
    fenced = _CODE_FENCE_RE.search(text)
    payload = fenced.group(1) if fenced else text
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError(f"expected a JSON object, got {type(result).__name__}")
    return result

_RUBRIC_PROMPTS = {
    "dev": """You are grading a coding agent's diff against a reference (known-good) diff \
for the same task. Score 0-100 on how well the candidate satisfies the task's intent:
- Does it cover the same functional ground as the reference (even if the exact code differs)?
- Is anything the reference does NOT do added (scope creep)?
- Is the candidate's approach reasonable engineering, not just textually similar?
A candidate that solves the task differently but correctly should score highly. A
candidate that copies reference wording without solving the task should score low.""",
    "distiller": """You are grading an extracted FailureReport against a reference \
FailureReport for the same raw CI log. Score 0-100 on:
- failing_suite/failing_tests match the reference's real failures (not noise)
- expected_vs_actual captures the same assertion/error the reference does
- suspect_files overlaps meaningfully with the reference
- warnings, flaky-marked skips, and infra noise were correctly ignored unless nothing
  else failed (in which case failing_suite should be "infra")""",
}


@dataclass(frozen=True)
class JudgeVerdict:
    score: float  # 0-100
    rationale: str


class JudgeFn(Protocol):
    def __call__(
        self, *, set_name: str, case_title: str, reference: str, candidate: str
    ) -> JudgeVerdict: ...


def haiku_judge(
    *, set_name: str, case_title: str, reference: str, candidate: str
) -> JudgeVerdict:
    client = anthropic.Anthropic()
    response = client.messages.create(
        model=_JUDGE_MODEL,
        max_tokens=_MAX_TOKENS,
        temperature=0,
        system=_RUBRIC_PROMPTS[set_name],
        messages=[
            {
                "role": "user",
                "content": (
                    f"## Case: {case_title}\n\n"
                    f"## Reference\n{reference}\n\n"
                    f"## Candidate\n{candidate}\n\n"
                    'Respond with ONLY JSON on one line: {"score": <integer 0-100>, '
                    '"rationale": "<one sentence>"}'
                ),
            }
        ],
    )
    block = response.content[0]
    text = block.text if hasattr(block, "text") else str(block)
    parsed = extract_json_object(text)
    return JudgeVerdict(score=float(parsed["score"]), rationale=str(parsed["rationale"]))
