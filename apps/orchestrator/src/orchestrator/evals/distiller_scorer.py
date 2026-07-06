"""Scores prompts/failure-distiller.md against evals/distiller/cases (SPEC-101 AC1/AC2).

apps/api's production failure_distiller.py is a deliberate deterministic stand-in (its
own docstring says so) - it never calls an LLM. This module is eval-only: it invokes a
haiku-class model directly with the CURRENT failure-distiller.md as system prompt, so a
degradation of that file's rules actually changes what this scorer sees. It does not
touch apps/api's production code path.
"""

from dataclasses import dataclass
from pathlib import Path

from llm_router import route
from schemas import FailureReport

from orchestrator.evals.judge import JudgeFn, extract_json_object, haiku_judge
from orchestrator.evals.loader import DistillerCase, DistillerReference

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_DISTILLER_PROMPT_PATH = _REPO_ROOT / "prompts" / "failure-distiller.md"
_MAX_TOKENS = 800


@dataclass(frozen=True)
class DistillerCaseResult:
    case_id: str
    title: str
    deterministic_score: float
    judge_score: float
    score: float  # 0-100, combined
    rationale: str
    candidate: FailureReport | None
    error: str | None = None


def invoke_distiller(
    *,
    raw_log: str,
    ticket_id: str,
    suite: str,
    attempt_no: int,
    system_prompt: str,
) -> FailureReport:
    text = route(
        "eval-distiller",
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    f"ticket_id: {ticket_id}\nsuite: {suite}\nattempt_no: {attempt_no}\n\n"
                    f"Raw CI log:\n{raw_log}"
                ),
            }
        ],
        max_tokens=_MAX_TOKENS,
    )
    parsed = extract_json_object(text)
    parsed.setdefault("ticket_id", ticket_id)
    parsed.setdefault("attempt_no", attempt_no)
    return FailureReport(**parsed)


def _field_accuracy(reference: DistillerReference, candidate: FailureReport) -> float:
    suite_match = 1.0 if candidate.failing_suite == reference.failing_suite else 0.0
    ref_tests = set(reference.failing_tests)
    cand_tests = set(candidate.failing_tests)
    if ref_tests:
        test_overlap = len(ref_tests & cand_tests) / len(ref_tests)
    else:
        test_overlap = 1.0 if not cand_tests else 0.0
    return (suite_match + test_overlap) / 2


def _suspect_file_hit_rate(reference: DistillerReference, candidate: FailureReport) -> float:
    ref_files = set(reference.suspect_files)
    if not ref_files:
        return 1.0 if not candidate.suspect_files else 0.5
    return len(ref_files & set(candidate.suspect_files)) / len(ref_files)


def _ignores_noise(reference: DistillerReference, candidate: FailureReport) -> float:
    # For infra/no-real-failure cases the reference already encodes the desired ignore
    # behaviour, so re-checking suite equality is the whole signal. Nothing to ignore in
    # a real-failure case, so don't penalise those on this dimension.
    if reference.failing_suite == "infra":
        return 1.0 if candidate.failing_suite == "infra" else 0.0
    return 1.0


def _deterministic_score(case: DistillerCase, candidate: FailureReport) -> float:
    dimension_scores = {
        "field_accuracy": _field_accuracy(case.reference, candidate),
        "suspect_file_hit_rate": _suspect_file_hit_rate(case.reference, candidate),
        "ignores_noise": _ignores_noise(case.reference, candidate),
    }
    weights = case.rubric_weights
    total_weight = sum(weights.get(k, 0.0) for k in dimension_scores) or 1.0
    weighted = sum(dimension_scores[k] * weights.get(k, 0.0) for k in dimension_scores)
    return (weighted / total_weight) * 100


def _reference_text(reference: DistillerReference) -> str:
    return (
        f"failing_suite: {reference.failing_suite}\n"
        f"failing_tests: {list(reference.failing_tests)}\n"
        f"expected_vs_actual: {reference.expected_vs_actual}\n"
        f"suspect_files: {list(reference.suspect_files)}"
    )


def score_case(
    case: DistillerCase,
    *,
    prompt_path: Path = DEFAULT_DISTILLER_PROMPT_PATH,
    judge: JudgeFn = haiku_judge,
) -> DistillerCaseResult:
    system_prompt = prompt_path.read_text(encoding="utf-8")
    try:
        candidate = invoke_distiller(
            raw_log=case.raw_log,
            ticket_id=case.ticket_id,
            suite=case.suite,
            attempt_no=case.attempt_no,
            system_prompt=system_prompt,
        )
    except Exception as exc:  # noqa: BLE001 - any failure here is a real 0-score result
        return DistillerCaseResult(
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
        set_name="distiller",
        case_title=case.title,
        reference=_reference_text(case.reference),
        candidate=candidate.model_dump_json(indent=2),
    )
    # Deterministic checks are the ground truth for this narrow extraction task; the
    # judge is blended in at a fixed 30% to catch qualitative issues (e.g. a technically
    # matching but poorly-explained expected_vs_actual) the deterministic side can't see.
    combined = 0.7 * deterministic_score + 0.3 * verdict.score
    return DistillerCaseResult(
        case_id=case.case_id,
        title=case.title,
        deterministic_score=deterministic_score,
        judge_score=verdict.score,
        score=combined,
        rationale=verdict.rationale,
        candidate=candidate,
    )
