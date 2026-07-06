"""Scores prompts/review-agent.md against evals/review/cases (SPEC-105 AC5).

Invokes the Review agent directly via packages/llm_router (role="review",
sonnet-class), independent of apps/api and apps/orchestrator.agents.review — this
module only scores prompt quality against fixture diffs, it doesn't touch a real
ticket, GitHub PR, or apps/api transition.

AC5's "false-block rate ≤10%" is satisfied via the same avg-score/floor mechanism
every other set uses, not a separately-computed rate: a false block on any clean
case (wrong verdict) scores nowhere near full marks, pulling the set average down —
so a floor comfortably above 0 already bounds how often that can happen across the
golden set. This is a disclosed interpretation choice, not a literal false-block-rate
computation.
"""

from dataclasses import dataclass
from pathlib import Path

from llm_router import route
from schemas import ReviewResult, TaskSpec

from orchestrator.evals.judge import JudgeFn, haiku_judge
from orchestrator.evals.loader import ReviewCase, ReviewExpected
from orchestrator.json_utils import extract_json_object

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_REVIEW_PROMPT_PATH = _REPO_ROOT / "prompts" / "review-agent.md"
_STYLE_GUIDE_PATH = _REPO_ROOT / "docs" / "07-conventions.md"
_MAX_TOKENS = 1200


@dataclass(frozen=True)
class ReviewCaseResult:
    case_id: str
    title: str
    deterministic_score: float
    judge_score: float
    score: float  # 0-100, combined
    rationale: str
    candidate: ReviewResult | None
    error: str | None = None


def _user_message(*, diff: str, task_spec: TaskSpec, style_guide: str) -> str:
    lines = [
        "## TaskSpec",
        f"id: {task_spec.id}",
        f"title: {task_spec.title}",
        f"context: {task_spec.context}",
        "acceptance_criteria:",
    ]
    for ac in task_spec.acceptance_criteria:
        lines.append(f"- [{ac.id}] {ac.description} (verify: {ac.verification})")
    lines.append("")
    lines.append("## PR diff")
    lines.append(diff)
    lines.append("")
    lines.append("## Style guide (docs/07-conventions.md)")
    lines.append(style_guide)
    lines.append("")
    lines.append("## Semgrep findings")
    lines.append("(none provided)")
    return "\n".join(lines)


def invoke_review(*, diff: str, task_spec: TaskSpec, system_prompt: str) -> ReviewResult:
    style_guide = _STYLE_GUIDE_PATH.read_text(encoding="utf-8")
    result = route(
        "review",
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": _user_message(diff=diff, task_spec=task_spec, style_guide=style_guide),
            }
        ],
        max_tokens=_MAX_TOKENS,
    )
    parsed = extract_json_object(result.text)
    return ReviewResult.model_validate(parsed)


def _verdict_match_score(expected: ReviewExpected, candidate: ReviewResult) -> float:
    return 1.0 if candidate.verdict == expected.verdict else 0.0


def _scope_violation_precision(expected: ReviewExpected, candidate: ReviewResult) -> float:
    expected_files = set(expected.scope_violations)
    candidate_files = set(candidate.scope_violations)
    if not expected_files:
        return 1.0 if not candidate_files else 0.0
    return len(expected_files & candidate_files) / len(expected_files)


def _deterministic_score(case: ReviewCase, candidate: ReviewResult) -> float:
    dimension_scores = {
        "verdict_match": _verdict_match_score(case.expected, candidate),
        "scope_violation_precision": _scope_violation_precision(case.expected, candidate),
    }
    weights = case.rubric_weights
    total_weight = sum(weights.get(k, 0.0) for k in dimension_scores) or 1.0
    weighted = sum(dimension_scores[k] * weights.get(k, 0.0) for k in dimension_scores)
    return (weighted / total_weight) * 100


def _reference_text(expected: ReviewExpected) -> str:
    return f"verdict: {expected.verdict}\nscope_violations: {list(expected.scope_violations)}"


def score_case(
    case: ReviewCase,
    *,
    prompt_path: Path = DEFAULT_REVIEW_PROMPT_PATH,
    judge: JudgeFn = haiku_judge,
) -> ReviewCaseResult:
    system_prompt = prompt_path.read_text(encoding="utf-8")
    try:
        candidate = invoke_review(
            diff=case.diff, task_spec=case.task_spec, system_prompt=system_prompt
        )
    except Exception as exc:  # noqa: BLE001 - any failure here is a real 0-score result
        return ReviewCaseResult(
            case_id=case.case_id,
            title=case.title,
            deterministic_score=0.0,
            judge_score=0.0,
            score=0.0,
            rationale=f"invocation/parsing failed: {exc}",
            candidate=None,
            error=str(exc),
        )

    deterministic_score = _deterministic_score(case, candidate)
    verdict = judge(
        set_name="review",
        case_title=case.title,
        reference=_reference_text(case.expected),
        candidate=candidate.model_dump_json(indent=2),
    )
    # Verdict correctness is the ground truth for this task (a wrong verdict is the
    # worst failure mode); the judge is blended in at a fixed 30% to catch qualitative
    # issues (vague comments, weak scope-violation evidence) the deterministic side
    # can't see.
    combined = 0.7 * deterministic_score + 0.3 * verdict.score
    return ReviewCaseResult(
        case_id=case.case_id,
        title=case.title,
        deterministic_score=deterministic_score,
        judge_score=verdict.score,
        score=combined,
        rationale=verdict.rationale,
        candidate=candidate,
    )
