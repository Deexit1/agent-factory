from api.services.failure_distiller import distill

PYTEST_LOG = """\
============================= test session starts ==============================
collected 12 items

tests/test_health.py::test_health_ok PASSED
tests/test_widget.py::test_widget_returns_200 FAILED
tests/test_widget.py::test_widget_shape FAILED

=================================== FAILURES ====================================
__________________________ test_widget_returns_200 ______________________________
assert 500 == 200
__________________________ test_widget_shape ______________________________
KeyError: 'id'
=========================== short test summary info =============================
FAILED tests/test_widget.py::test_widget_returns_200 - assert 500 == 200
FAILED tests/test_widget.py::test_widget_shape - KeyError: 'id'
========================= 2 failed, 10 passed in 1.23s ===========================
"""

VITEST_LOG = """\
 ✗ src/widget.test.ts > renders the widget
 FAIL  src/widget.test.ts
   AssertionError: expected 1 to be 2
"""


def test_distill_parses_pytest_failed_summary_lines() -> None:
    report = distill(ticket_id="T-123", suite="unit", raw_log=PYTEST_LOG, attempt_no=1)

    assert report.ticket_id == "T-123"
    assert report.failing_suite == "unit"
    assert report.failing_tests == [
        "tests/test_widget.py::test_widget_returns_200",
        "tests/test_widget.py::test_widget_shape",
    ]
    assert "assert 500 == 200" in report.expected_vs_actual
    assert "KeyError: 'id'" in report.expected_vs_actual
    assert report.suspect_files == ["tests/test_widget.py"]
    assert report.attempt_no == 1


def test_distill_clamps_attempt_no_to_schema_max() -> None:
    report = distill(ticket_id="T-1", suite="unit", raw_log=PYTEST_LOG, attempt_no=7)
    assert report.attempt_no == 3


def test_distill_falls_back_to_vitest_fail_lines() -> None:
    report = distill(ticket_id="T-1", suite="web-unit", raw_log=VITEST_LOG, attempt_no=1)

    assert report.failing_tests == ["src/widget.test.ts"]
    assert "AssertionError" in report.expected_vs_actual


def test_distill_falls_back_to_raw_tail_when_unparseable() -> None:
    report = distill(
        ticket_id="T-1", suite="e2e", raw_log="boom, everything is on fire", attempt_no=1
    )

    assert report.failing_tests == ["unknown"]
    assert "boom" in report.expected_vs_actual


def test_distill_handles_empty_log() -> None:
    report = distill(ticket_id="T-1", suite="e2e", raw_log="", attempt_no=1)

    assert report.failing_tests == ["unknown"]
    assert report.expected_vs_actual == "no log output captured"
