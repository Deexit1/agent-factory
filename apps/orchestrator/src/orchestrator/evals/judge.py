"""Haiku-class rubric judge, shared by every eval set (SPEC-101).

Temperature 0 for reproducibility (AC4: two runs on identical input must differ by
< 2%). Real implementation calls the Anthropic API directly - unlike the dev/distiller
agents, the judge has no production counterpart to reuse, so this is eval-only code.
"""

from dataclasses import dataclass
from typing import Protocol

from llm_router import route

from orchestrator.json_utils import extract_json_object

_MAX_TOKENS = 300

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
    "planner": """You are grading a Planner agent's epic/task decomposition of an idea
against a reference decomposition. Score 0-100 on:
- Does the candidate cover the same functional scope as the reference (even if the
  exact epic/task split differs)?
- Are acceptance criteria specific and machine-verifiable, not vague?
- Is the task breakdown a reasonable, independently-shippable slicing, not arbitrary?
A candidate that slices the work differently but sensibly should score highly. A
candidate that copies reference wording without a coherent decomposition should score
low.
If the candidate is a list of clarifying questions instead of a decomposition: the
reference successfully produced a full plan from the same idea input, so the idea was
NOT actually under-specified. Score low (0-25) unless the questions identify a real,
material gap a competent planner genuinely could not have proceeded without (in which
case score higher in proportion to how essential the missing information truly was).
Being needlessly conservative about a well-specified idea is the failure mode this
rubric exists to catch.""",
    "review": """You are grading a Review agent's verdict on a PR diff against a
reference (expected) verdict for the same diff. Score 0-100 on:
- Does the candidate's verdict (approve/block) match the reference's expected
  verdict? A wrong verdict (approving a diff that should be blocked, or blocking a
  clean diff) is the single worst failure mode and should score near 0.
- When blocking, are the comments/scope_violations concrete and specific (naming
  the actual file/problem), not vague boilerplate?
- Style nits alone should never justify a block — a block needs real, quoted
  evidence.
A candidate whose verdict matches the reference and whose reasoning is specific
and well-grounded should score highly.""",
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
    result = route(
        "eval-judge",
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
        max_tokens=_MAX_TOKENS,
    )
    parsed = extract_json_object(result.text)
    return JudgeVerdict(score=float(parsed["score"]), rationale=str(parsed["rationale"]))


__all__ = ["JudgeVerdict", "JudgeFn", "haiku_judge", "extract_json_object"]
