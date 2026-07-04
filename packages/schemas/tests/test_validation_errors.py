import pytest
from pydantic import ValidationError

from schemas.models import (
    AcceptanceCriterion,
    BusinessCase,
    Complexity,
    FailureReport,
    TaskSpec,
)


def test_task_spec_rejects_non_positive_budget(acceptance_criterion: AcceptanceCriterion) -> None:
    with pytest.raises(ValidationError) as exc_info:
        TaskSpec(
            id="T-001",
            title="Bad budget",
            context="ctx",
            acceptance_criteria=[acceptance_criterion],
            complexity=Complexity.LOW,
            budget_usd=0,
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("budget_usd",) for error in errors)


def test_task_spec_rejects_missing_required_fields() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TaskSpec.model_validate({"id": "T-001"})

    missing_fields = {error["loc"][0] for error in exc_info.value.errors()}
    assert {"title", "context", "acceptance_criteria", "complexity", "budget_usd"} <= missing_fields


def test_task_spec_rejects_invalid_nested_acceptance_criterion() -> None:
    with pytest.raises(ValidationError) as exc_info:
        TaskSpec.model_validate(
            {
                "id": "T-001",
                "title": "t",
                "context": "ctx",
                "acceptance_criteria": [{"id": "AC-1"}],
                "complexity": "low",
                "budget_usd": 10,
            }
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("acceptance_criteria", 0, "description") for error in errors)
    assert any(error["loc"] == ("acceptance_criteria", 0, "verification") for error in errors)


def test_failure_report_rejects_attempt_no_above_max() -> None:
    with pytest.raises(ValidationError) as exc_info:
        FailureReport(
            ticket_id="T-001",
            failing_suite="pytest",
            failing_tests=["test_x"],
            expected_vs_actual="expected/actual",
            attempt_no=4,
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("attempt_no",) for error in errors)


def test_business_case_rejects_invalid_source_url() -> None:
    with pytest.raises(ValidationError) as exc_info:
        BusinessCase.model_validate(
            {
                "idea_id": "IDEA-1",
                "opportunity": "op",
                "market_evidence": [{"claim": "x", "source_url": "not-a-url"}],
                "cost_estimate": 100,
                "recommendation": "go",
            }
        )

    errors = exc_info.value.errors()
    assert any(error["loc"] == ("market_evidence", 0, "source_url") for error in errors)
