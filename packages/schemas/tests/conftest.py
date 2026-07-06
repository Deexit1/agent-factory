import pytest

from schemas.models import (
    AcceptanceCriterion,
    BusinessCase,
    Complexity,
    Epic,
    FailureReport,
    MarketEvidence,
    PlannerPlan,
    PlannerQuestions,
    TaskSpec,
)


@pytest.fixture
def acceptance_criterion() -> AcceptanceCriterion:
    return AcceptanceCriterion(
        id="AC-1",
        description="Health endpoint returns 200",
        verification="tests/test_health.py::test_health_returns_200_ok",
    )


@pytest.fixture
def task_spec(acceptance_criterion: AcceptanceCriterion) -> TaskSpec:
    return TaskSpec(
        id="T-001",
        title="Repo scaffold & tooling",
        context="Bootstrap the monorepo.",
        constraints=["Use locked tech stack"],
        acceptance_criteria=[acceptance_criterion],
        complexity=Complexity.LOW,
        budget_usd=25.0,
    )


@pytest.fixture
def epic() -> Epic:
    return Epic(
        id="E-001",
        title="Repo scaffold",
        description="Bootstrap the monorepo and tooling.",
        budget_usd=100.0,
    )


@pytest.fixture
def planner_plan(epic: Epic, task_spec: TaskSpec) -> PlannerPlan:
    return PlannerPlan(epics=[epic], tasks=[task_spec])


@pytest.fixture
def planner_questions() -> PlannerQuestions:
    return PlannerQuestions(questions=["What's the target user for this idea?"])


@pytest.fixture
def failure_report() -> FailureReport:
    return FailureReport(
        ticket_id="T-001",
        failing_suite="pytest",
        failing_tests=["tests/test_health.py::test_health_returns_200_ok"],
        expected_vs_actual="expected 200, got 500",
        suspect_files=["apps/api/src/api/routers/health.py"],
        attempt_no=1,
    )


@pytest.fixture
def business_case() -> BusinessCase:
    return BusinessCase(
        idea_id="IDEA-1",
        opportunity="Automate ticket triage",
        market_evidence=[
            MarketEvidence(
                claim="70% of dev time is spent on repetitive tickets",
                source_url="https://example.com/report",
            )
        ],
        cost_estimate=15000.0,
        risks=["Model drift"],
        recommendation="Proceed to planning",
    )
