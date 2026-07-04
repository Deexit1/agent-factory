from schemas.models import AcceptanceCriterion, BusinessCase, FailureReport, TaskSpec


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
