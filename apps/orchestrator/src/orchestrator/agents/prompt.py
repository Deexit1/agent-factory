from schemas import FailureReport, TaskSpec


def build_prompt(task_spec: TaskSpec, failure_report: FailureReport | None, attempt_no: int) -> str:
    lines = [
        f"# Task {task_spec.id}: {task_spec.title}",
        "",
        task_spec.context,
        "",
        "## Acceptance criteria",
    ]
    for criterion in task_spec.acceptance_criteria:
        lines.append(
            f"- [{criterion.id}] {criterion.description} (verify: {criterion.verification})"
        )

    if task_spec.constraints:
        lines.append("")
        lines.append("## Constraints")
        for constraint in task_spec.constraints:
            lines.append(f"- {constraint}")

    lines.append("")
    lines.append(f"This is attempt {attempt_no}.")

    if failure_report is not None:
        lines.append("")
        lines.append("## Previous attempt failed — fix this before anything else")
        lines.append(f"- Failing suite: {failure_report.failing_suite}")
        lines.append(f"- Failing tests: {', '.join(failure_report.failing_tests)}")
        lines.append(f"- Expected vs actual: {failure_report.expected_vs_actual}")
        if failure_report.suspect_files:
            lines.append(f"- Suspect files: {', '.join(failure_report.suspect_files)}")

    return "\n".join(lines)
