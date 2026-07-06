"""Scores prompts/planner.md against evals/planner/cases (SPEC-102 AC1/AC5).

Invokes the Planner directly via packages/llm_router (role="planner", opus-class),
independent of apps/api and apps/orchestrator.agents.planner — this module only
scores prompt quality against synthetic idea fixtures, it doesn't touch a real ticket
tree or the API.
"""

from dataclasses import dataclass
from pathlib import Path

from llm_router import route
from schemas import PlannerPlan, PlannerQuestions

from orchestrator.evals.judge import JudgeFn, haiku_judge
from orchestrator.evals.loader import PlannerCase
from orchestrator.json_utils import extract_json_object

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_PLANNER_PROMPT_PATH = _REPO_ROOT / "prompts" / "planner.md"
_MAX_TOKENS = 4000


@dataclass(frozen=True)
class PlannerCaseResult:
    case_id: str
    title: str
    deterministic_score: float
    judge_score: float
    score: float  # 0-100, combined
    rationale: str
    candidate: PlannerPlan | None
    questions: list[str] | None = None
    error: str | None = None


def invoke_planner(
    *, idea_title: str, idea_description: str, idea_budget_usd: float, system_prompt: str
) -> PlannerPlan | PlannerQuestions:
    result = route(
        "planner",
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": (
                    f"# Idea: {idea_title}\n\n{idea_description}\n\n"
                    f"Approved budget: ${idea_budget_usd:.2f}"
                ),
            }
        ],
        max_tokens=_MAX_TOKENS,
    )
    parsed = extract_json_object(result.text)
    if "questions" in parsed:
        return PlannerQuestions.model_validate(parsed)
    return PlannerPlan.model_validate(parsed)


def _has_cycle(plan: PlannerPlan) -> bool:
    graph = {task.id: list(task.depends_on) for task in plan.tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def _visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for dep in graph.get(node, []):
            if _visit(dep):
                return True
        visiting.discard(node)
        visited.add(node)
        return False

    return any(_visit(node) for node in graph)


def _schema_valid(plan: PlannerPlan) -> float:
    return 1.0 if plan.epics and plan.tasks else 0.0


def _dag_valid(plan: PlannerPlan) -> float:
    return 0.0 if _has_cycle(plan) else 1.0


def _budget_within_idea(plan: PlannerPlan, idea_budget_usd: float) -> float:
    total = sum(task.budget_usd for task in plan.tasks)
    return 1.0 if total <= idea_budget_usd else 0.0


def _verification_hints_present(plan: PlannerPlan) -> float:
    if not plan.tasks:
        return 0.0
    tasks_with_hints = sum(
        1
        for task in plan.tasks
        if task.acceptance_criteria
        and all(c.verification.strip() for c in task.acceptance_criteria)
    )
    return tasks_with_hints / len(plan.tasks)


def _deterministic_score(case: PlannerCase, candidate: PlannerPlan) -> float:
    dimension_scores = {
        "schema_valid": _schema_valid(candidate),
        "dag_valid": _dag_valid(candidate),
        "budget_within_idea": _budget_within_idea(candidate, case.idea.budget_usd),
        "verification_hints_present": _verification_hints_present(candidate),
    }
    weights = case.rubric_weights
    total_weight = sum(weights.get(k, 0.0) for k in dimension_scores) or 1.0
    weighted = sum(dimension_scores[k] * weights.get(k, 0.0) for k in dimension_scores)
    return (weighted / total_weight) * 100


def _reference_text(reference: PlannerPlan) -> str:
    return reference.model_dump_json(indent=2)


def _score_questions_response(
    case: PlannerCase, questions: PlannerQuestions, *, judge: JudgeFn
) -> PlannerCaseResult:
    # Every reference in this golden set is a full PlannerPlan — the idea was
    # demonstrably plannable from the same input. A questions[] response here is a
    # real miss (over-conservative), not a neutral alternative: no plan means none of
    # the deterministic sanity checks (schema/DAG/budget/verification) can even run.
    verdict = judge(
        set_name="planner",
        case_title=case.title,
        reference=_reference_text(case.reference),
        candidate=questions.model_dump_json(indent=2),
    )
    combined = 0.6 * 0.0 + 0.4 * verdict.score
    return PlannerCaseResult(
        case_id=case.case_id,
        title=case.title,
        deterministic_score=0.0,
        judge_score=verdict.score,
        score=combined,
        rationale=verdict.rationale,
        candidate=None,
        questions=questions.questions,
    )


def score_case(
    case: PlannerCase,
    *,
    prompt_path: Path = DEFAULT_PLANNER_PROMPT_PATH,
    judge: JudgeFn = haiku_judge,
) -> PlannerCaseResult:
    system_prompt = prompt_path.read_text(encoding="utf-8")
    try:
        candidate = invoke_planner(
            idea_title=case.idea.title,
            idea_description=case.idea.description,
            idea_budget_usd=case.idea.budget_usd,
            system_prompt=system_prompt,
        )
    except Exception as exc:  # noqa: BLE001 - any failure here is a real 0-score result
        return PlannerCaseResult(
            case_id=case.case_id,
            title=case.title,
            deterministic_score=0.0,
            judge_score=0.0,
            score=0.0,
            rationale=f"invocation/parsing failed: {exc}",
            candidate=None,
            error=str(exc),
        )

    if isinstance(candidate, PlannerQuestions):
        return _score_questions_response(case, candidate, judge=judge)

    deterministic_score = _deterministic_score(case, candidate)
    verdict = judge(
        set_name="planner",
        case_title=case.title,
        reference=_reference_text(case.reference),
        candidate=candidate.model_dump_json(indent=2),
    )
    # Same 60/40 deterministic/judge split as the dev set — deterministic checks carry
    # the sanity gates a human would enforce anyway; the judge catches decomposition
    # quality the gates can't see (e.g. a technically-valid but nonsensical slicing).
    combined = 0.6 * deterministic_score + 0.4 * verdict.score
    return PlannerCaseResult(
        case_id=case.case_id,
        title=case.title,
        deterministic_score=deterministic_score,
        judge_score=verdict.score,
        score=combined,
        rationale=verdict.rationale,
        candidate=candidate,
    )
