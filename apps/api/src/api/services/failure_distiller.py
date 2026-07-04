"""Raw CI logs -> FailureReport. Deterministic parsing, no LLM call.

Phase 1 stand-in for the haiku-class failure distiller in docs/04-agent-specs.md: a
learned model isn't needed to extract "which tests failed" from a pytest/vitest summary,
and a deterministic parser is what SPEC-005 AC2 actually requires ("FailureReport whose
failing_tests matches the CI log").
"""

import re
from collections.abc import Iterable

from schemas.models import FailureReport

_PYTEST_FAILED_LINE = re.compile(r"^FAILED (?P<nodeid>\S+) - (?P<reason>.+)$", re.MULTILINE)
_VITEST_FAIL_LINE = re.compile(r"^\s*(?:FAIL|✗|×)\s+(?P<nodeid>\S+)", re.MULTILINE)
_LOG_TAIL_CHARS = 2000


def distill(*, ticket_id: str, suite: str, raw_log: str, attempt_no: int) -> FailureReport:
    """Pure function: no I/O, no mutation."""
    clamped_attempt_no = max(1, min(attempt_no, 3))

    pytest_matches = list(_PYTEST_FAILED_LINE.finditer(raw_log))
    if pytest_matches:
        failing_tests = [m.group("nodeid") for m in pytest_matches]
        expected_vs_actual = "; ".join(m.group("reason") for m in pytest_matches)
        suspect_files = _unique(nodeid.split("::")[0] for nodeid in failing_tests)
        return FailureReport(
            ticket_id=ticket_id,
            failing_suite=suite,
            failing_tests=failing_tests,
            expected_vs_actual=expected_vs_actual,
            suspect_files=suspect_files,
            attempt_no=clamped_attempt_no,
        )

    vitest_matches = list(_VITEST_FAIL_LINE.finditer(raw_log))
    if vitest_matches:
        failing_tests = _unique(m.group("nodeid") for m in vitest_matches)
        return FailureReport(
            ticket_id=ticket_id,
            failing_suite=suite,
            failing_tests=failing_tests,
            expected_vs_actual=raw_log[-_LOG_TAIL_CHARS:].strip(),
            suspect_files=[],
            attempt_no=clamped_attempt_no,
        )

    return FailureReport(
        ticket_id=ticket_id,
        failing_suite=suite,
        failing_tests=["unknown"],
        expected_vs_actual=(raw_log[-_LOG_TAIL_CHARS:].strip() or "no log output captured"),
        suspect_files=[],
        attempt_no=clamped_attempt_no,
    )


def _unique(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        seen.setdefault(item, None)
    return list(seen)
