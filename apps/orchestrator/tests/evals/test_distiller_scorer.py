from schemas import FailureReport

from orchestrator.evals import distiller_scorer
from orchestrator.evals.judge import JudgeVerdict
from orchestrator.evals.loader import DistillerCase, DistillerReference


def _case(**overrides: object) -> DistillerCase:
    defaults: dict[str, object] = dict(
        case_id="t-001",
        title="test case",
        ticket_id="T-1",
        suite="pytest",
        attempt_no=1,
        raw_log="irrelevant for these unit tests",
        reference=DistillerReference(
            failing_suite="pytest",
            failing_tests=("test_app.py::test_thing",),
            expected_vs_actual="assert 404 == 200",
            suspect_files=("test_app.py",),
        ),
        rubric_weights={"field_accuracy": 0.6, "suspect_file_hit_rate": 0.3, "ignores_noise": 0.1},
    )
    defaults.update(overrides)
    return DistillerCase(**defaults)  # type: ignore[arg-type]


def _report(**overrides: object) -> FailureReport:
    defaults: dict[str, object] = dict(
        ticket_id="T-1",
        failing_suite="pytest",
        failing_tests=["test_app.py::test_thing"],
        expected_vs_actual="assert 404 == 200",
        suspect_files=["test_app.py"],
        attempt_no=1,
    )
    defaults.update(overrides)
    return FailureReport(**defaults)  # type: ignore[arg-type]


def test_field_accuracy_is_perfect_for_an_exact_match() -> None:
    case = _case()
    candidate = _report()
    assert distiller_scorer._field_accuracy(case.reference, candidate) == 1.0


def test_field_accuracy_penalises_a_wrong_suite() -> None:
    case = _case()
    candidate = _report(failing_suite="vitest")
    assert distiller_scorer._field_accuracy(case.reference, candidate) == 0.5


def test_suspect_file_hit_rate_partial_overlap() -> None:
    case = _case(
        reference=DistillerReference(
            failing_suite="pytest",
            failing_tests=("a.py::t1",),
            expected_vs_actual="x",
            suspect_files=("a.py", "b.py"),
        )
    )
    candidate = _report(suspect_files=["a.py"])
    assert distiller_scorer._suspect_file_hit_rate(case.reference, candidate) == 0.5


def test_ignores_noise_rewards_matching_infra_classification() -> None:
    case = _case(
        reference=DistillerReference(
            failing_suite="infra", failing_tests=("none",), expected_vs_actual="x", suspect_files=()
        )
    )
    candidate = _report(failing_suite="infra", failing_tests=["none"], suspect_files=[])
    assert distiller_scorer._ignores_noise(case.reference, candidate) == 1.0


def test_ignores_noise_penalises_missed_infra_classification() -> None:
    case = _case(
        reference=DistillerReference(
            failing_suite="infra", failing_tests=("none",), expected_vs_actual="x", suspect_files=()
        )
    )
    candidate = _report(failing_suite="pytest", failing_tests=["some_test"])
    assert distiller_scorer._ignores_noise(case.reference, candidate) == 0.0


def test_score_case_combines_deterministic_and_judge_scores(monkeypatch) -> None:
    case = _case()

    def fake_invoke(**_kwargs: object) -> FailureReport:
        return _report()

    def fake_judge(**_kwargs: object) -> JudgeVerdict:
        return JudgeVerdict(score=90.0, rationale="looks right")

    monkeypatch.setattr(distiller_scorer, "invoke_distiller", fake_invoke)

    result = distiller_scorer.score_case(case, judge=fake_judge)

    assert result.deterministic_score == 100.0
    assert result.judge_score == 90.0
    assert result.score == 0.7 * 100.0 + 0.3 * 90.0
    assert result.error is None


def test_score_case_returns_zero_on_invocation_failure(monkeypatch) -> None:
    case = _case()

    def failing_invoke(**_kwargs: object) -> FailureReport:
        raise RuntimeError("API exploded")

    monkeypatch.setattr(distiller_scorer, "invoke_distiller", failing_invoke)

    result = distiller_scorer.score_case(case)

    assert result.score == 0.0
    assert result.error is not None
    assert "API exploded" in result.error
