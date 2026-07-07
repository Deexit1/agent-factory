from schemas.models import (
    AcceptanceCriterion,
    BusinessCase,
    Epic,
    FailureReport,
    PlannerPlan,
    PlannerQuestions,
    ReviewComment,
    ReviewResult,
    TaskSpec,
)


def test_task_spec_round_trips(task_spec: TaskSpec) -> None:
    dumped = task_spec.model_dump()
    assert TaskSpec.model_validate(dumped) == task_spec

    dumped_json = task_spec.model_dump_json()
    assert TaskSpec.model_validate_json(dumped_json) == task_spec


def test_acceptance_criterion_round_trips(acceptance_criterion: AcceptanceCriterion) -> None:
    dumped = acceptance_criterion.model_dump()
    assert AcceptanceCriterion.model_validate(dumped) == acceptance_criterion

    dumped_json = acceptance_criterion.model_dump_json()
    assert AcceptanceCriterion.model_validate_json(dumped_json) == acceptance_criterion


def test_failure_report_round_trips(failure_report: FailureReport) -> None:
    dumped = failure_report.model_dump()
    assert FailureReport.model_validate(dumped) == failure_report

    dumped_json = failure_report.model_dump_json()
    assert FailureReport.model_validate_json(dumped_json) == failure_report


def test_business_case_round_trips(business_case: BusinessCase) -> None:
    dumped = business_case.model_dump()
    assert BusinessCase.model_validate(dumped) == business_case

    dumped_json = business_case.model_dump_json()
    assert BusinessCase.model_validate_json(dumped_json) == business_case


def test_epic_round_trips(epic: Epic) -> None:
    dumped = epic.model_dump()
    assert Epic.model_validate(dumped) == epic

    dumped_json = epic.model_dump_json()
    assert Epic.model_validate_json(dumped_json) == epic


def test_planner_plan_round_trips(planner_plan: PlannerPlan) -> None:
    dumped = planner_plan.model_dump()
    assert PlannerPlan.model_validate(dumped) == planner_plan

    dumped_json = planner_plan.model_dump_json()
    assert PlannerPlan.model_validate_json(dumped_json) == planner_plan


def test_planner_questions_round_trips(planner_questions: PlannerQuestions) -> None:
    dumped = planner_questions.model_dump()
    assert PlannerQuestions.model_validate(dumped) == planner_questions

    dumped_json = planner_questions.model_dump_json()
    assert PlannerQuestions.model_validate_json(dumped_json) == planner_questions


def test_task_spec_depends_on_and_estimate_days_round_trip(
    acceptance_criterion: AcceptanceCriterion,
) -> None:
    task = TaskSpec(
        id="T-002",
        title="Second task",
        context="ctx",
        acceptance_criteria=[acceptance_criterion],
        complexity="low",
        budget_usd=10.0,
        depends_on=["T-001"],
        estimate_days=0.5,
        epic_id="E-001",
        repo="git@github.com:example/other-repo.git",
        required_skills=["frontend"],
    )
    assert TaskSpec.model_validate(task.model_dump()) == task


def test_task_spec_repo_defaults_to_default_repo(
    acceptance_criterion: AcceptanceCriterion,
) -> None:
    from schemas.models import DEFAULT_REPO

    task = TaskSpec(
        id="T-003",
        title="Third task",
        context="ctx",
        acceptance_criteria=[acceptance_criterion],
        complexity="low",
        budget_usd=10.0,
    )
    assert task.repo == DEFAULT_REPO


def test_task_spec_required_skills_defaults_to_empty(
    acceptance_criterion: AcceptanceCriterion,
) -> None:
    task = TaskSpec(
        id="T-004",
        title="Fourth task",
        context="ctx",
        acceptance_criteria=[acceptance_criterion],
        complexity="low",
        budget_usd=10.0,
    )
    assert task.required_skills == []


def test_review_result_round_trips() -> None:
    result = ReviewResult(
        verdict="block",
        comments=[ReviewComment(file="app.py", line=42, comment="unhandled exception")],
        scope_violations=["unrelated_file.py"],
    )
    dumped = result.model_dump()
    assert ReviewResult.model_validate(dumped) == result

    dumped_json = result.model_dump_json()
    assert ReviewResult.model_validate_json(dumped_json) == result


def test_review_result_defaults_to_empty_comments_and_scope_violations() -> None:
    result = ReviewResult(verdict="approve")
    assert result.comments == []
    assert result.scope_violations == []
