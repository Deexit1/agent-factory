import math

from orchestrator.evals.loader import (
    load_dev_cases,
    load_distiller_cases,
    load_planner_cases,
    load_thresholds,
)


def test_thresholds_cover_every_set() -> None:
    thresholds = load_thresholds()
    assert set(thresholds) == {"dev", "distiller", "planner", "review"}
    assert thresholds["dev"].floor is not None
    assert thresholds["dev"].not_yet_enforced is False
    assert thresholds["planner"].not_yet_enforced is True
    assert thresholds["review"].not_yet_enforced is True


def test_dev_cases_load_with_at_least_ten_cases() -> None:
    cases = load_dev_cases()
    assert len(cases) >= 10
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids)), "case_ids must be unique"
    for case in cases:
        assert case.task_spec.acceptance_criteria
        assert case.reference_patch.strip()
        assert case.starter_kind in ("repo_snapshot", "standalone")
        if case.starter_kind == "repo_snapshot":
            assert case.starter_ref
        else:
            assert case.starter_dir is not None and case.starter_dir.exists()
        assert math.isclose(sum(case.rubric_weights.values()), 1.0, abs_tol=1e-6)


def test_distiller_cases_load_with_at_least_ten_cases() -> None:
    cases = load_distiller_cases()
    assert len(cases) >= 10
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids)), "case_ids must be unique"
    for case in cases:
        assert case.raw_log.strip()
        assert case.reference.failing_suite
        assert math.isclose(sum(case.rubric_weights.values()), 1.0, abs_tol=1e-6)


def test_planner_cases_load_with_at_least_ten_cases() -> None:
    cases = load_planner_cases()
    assert len(cases) >= 10
    ids = [c.case_id for c in cases]
    assert len(ids) == len(set(ids)), "case_ids must be unique"
    for case in cases:
        assert case.idea.title
        assert case.idea.budget_usd > 0
        assert case.reference.epics
        assert case.reference.tasks
        assert math.isclose(sum(case.rubric_weights.values()), 1.0, abs_tol=1e-6)
