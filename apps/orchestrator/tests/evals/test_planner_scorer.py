from schemas import AcceptanceCriterion, Complexity, Epic, PlannerPlan, TaskSpec

from orchestrator.evals import planner_scorer
from orchestrator.evals.judge import JudgeVerdict
from orchestrator.evals.loader import PlannerCase, PlannerIdea


def _idea(**overrides: object) -> PlannerIdea:
    defaults: dict[str, object] = dict(title="An idea", description="d", budget_usd=100.0)
    defaults.update(overrides)
    return PlannerIdea(**defaults)  # type: ignore[arg-type]


def _task(**overrides: object) -> TaskSpec:
    defaults: dict[str, object] = dict(
        id="task-1",
        title="t",
        context="ctx",
        acceptance_criteria=[AcceptanceCriterion(id="AC-1", description="d", verification="v")],
        complexity=Complexity.LOW,
        budget_usd=10.0,
        depends_on=[],
        estimate_days=0.5,
        epic_id="epic-1",
    )
    defaults.update(overrides)
    return TaskSpec(**defaults)  # type: ignore[arg-type]


def _epic(**overrides: object) -> Epic:
    defaults: dict[str, object] = dict(id="epic-1", title="e", description="d", budget_usd=10.0)
    defaults.update(overrides)
    return Epic(**defaults)  # type: ignore[arg-type]


def _case(**overrides: object) -> PlannerCase:
    defaults: dict[str, object] = dict(
        case_id="planner-t-001",
        title="test case",
        source="synthetic",
        idea=_idea(),
        reference=PlannerPlan(epics=[_epic()], tasks=[_task()]),
        rubric_weights={
            "schema_valid": 0.25,
            "dag_valid": 0.25,
            "budget_within_idea": 0.25,
            "verification_hints_present": 0.25,
        },
    )
    defaults.update(overrides)
    return PlannerCase(**defaults)  # type: ignore[arg-type]


def test_schema_valid_requires_epics_and_tasks() -> None:
    plan = PlannerPlan(epics=[_epic()], tasks=[_task()])
    assert planner_scorer._schema_valid(plan) == 1.0
    assert planner_scorer._schema_valid(PlannerPlan(epics=[], tasks=[])) == 0.0


def test_dag_valid_detects_a_cycle() -> None:
    acyclic = PlannerPlan(epics=[_epic()], tasks=[_task(id="a", depends_on=[])])
    assert planner_scorer._dag_valid(acyclic) == 1.0

    cyclic = PlannerPlan(
        epics=[_epic()],
        tasks=[_task(id="a", depends_on=["b"]), _task(id="b", depends_on=["a"])],
    )
    assert planner_scorer._dag_valid(cyclic) == 0.0


def test_budget_within_idea_flags_an_overrun() -> None:
    plan = PlannerPlan(epics=[_epic()], tasks=[_task(budget_usd=50.0)])
    assert planner_scorer._budget_within_idea(plan, 100.0) == 1.0
    assert planner_scorer._budget_within_idea(plan, 10.0) == 0.0


def test_verification_hints_present_penalises_a_blank_hint() -> None:
    good = PlannerPlan(
        epics=[_epic()],
        tasks=[
            _task(
                acceptance_criteria=[
                    AcceptanceCriterion(id="AC-1", description="d", verification="v")
                ]
            )
        ],
    )
    assert planner_scorer._verification_hints_present(good) == 1.0

    bad = PlannerPlan(
        epics=[_epic()],
        tasks=[
            _task(
                acceptance_criteria=[
                    AcceptanceCriterion(id="AC-1", description="d", verification="  ")
                ]
            )
        ],
    )
    assert planner_scorer._verification_hints_present(bad) == 0.0


def test_score_case_combines_deterministic_and_judge_scores(monkeypatch) -> None:
    case = _case()

    def fake_invoke(**_kwargs: object) -> PlannerPlan:
        return PlannerPlan(epics=[_epic()], tasks=[_task()])

    def fake_judge(**_kwargs: object) -> JudgeVerdict:
        return JudgeVerdict(score=90.0, rationale="looks right")

    monkeypatch.setattr(planner_scorer, "invoke_planner", fake_invoke)

    result = planner_scorer.score_case(case, judge=fake_judge)

    assert result.deterministic_score == 100.0
    assert result.judge_score == 90.0
    assert result.score == 0.6 * 100.0 + 0.4 * 90.0
    assert result.error is None


def test_score_case_returns_zero_on_invocation_failure(monkeypatch) -> None:
    case = _case()

    def failing_invoke(**_kwargs: object) -> PlannerPlan:
        raise RuntimeError("API exploded")

    monkeypatch.setattr(planner_scorer, "invoke_planner", failing_invoke)

    result = planner_scorer.score_case(case)

    assert result.score == 0.0
    assert result.error is not None
    assert "API exploded" in result.error
