"""`python -m orchestrator.evals.runner run [--set all|dev|distiller] [--only-changed]`

The `make eval` entry point (SPEC-101). Exits non-zero if any enforced set falls below
its `evals/thresholds.yaml` floor, so it behaves like any other blocking CI check.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from orchestrator.claude_runner import SubprocessClaudeCodeRunner
from orchestrator.evals import dev_scorer, distiller_scorer, planner_scorer, report, review_scorer
from orchestrator.evals.langfuse_client import LangfuseClient, parse_prompt_version
from orchestrator.evals.loader import (
    load_dev_cases,
    load_distiller_cases,
    load_planner_cases,
    load_review_cases,
    load_thresholds,
)

_REPO_ROOT = Path(__file__).resolve().parents[5]
DEV_PROMPT_PATH = _REPO_ROOT / "prompts" / "dev-agent.md"
DISTILLER_PROMPT_PATH = _REPO_ROOT / "prompts" / "failure-distiller.md"
PLANNER_PROMPT_PATH = _REPO_ROOT / "prompts" / "planner.md"
REVIEW_PROMPT_PATH = _REPO_ROOT / "prompts" / "review-agent.md"
_SCORABLE_SETS = ("dev", "distiller", "planner", "review")


def _changed_prompt_files(base_ref: str) -> set[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--", "prompts/"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def run_dev_set(*, floor: float | None, langfuse: LangfuseClient) -> report.SetReport:
    cases = load_dev_cases()
    version = parse_prompt_version(DEV_PROMPT_PATH.read_text(encoding="utf-8"))
    claude_runner = SubprocessClaudeCodeRunner()
    scores = []
    for case in cases:
        result = dev_scorer.score_case(case, claude_runner=claude_runner)
        langfuse.log_case_run(
            set_name="dev",
            case_id=result.case_id,
            prompt_version=version,
            score=result.score,
            rationale=result.rationale,
        )
        scores.append(
            report.CaseScore(
                result.case_id, result.title, result.score, result.rationale, detail=result.diff
            )
        )
    return report.SetReport(set_name="dev", floor=floor, scores=scores)


def run_distiller_set(*, floor: float | None, langfuse: LangfuseClient) -> report.SetReport:
    cases = load_distiller_cases()
    version = parse_prompt_version(DISTILLER_PROMPT_PATH.read_text(encoding="utf-8"))
    scores = []
    for case in cases:
        result = distiller_scorer.score_case(case)
        langfuse.log_case_run(
            set_name="distiller",
            case_id=result.case_id,
            prompt_version=version,
            score=result.score,
            rationale=result.rationale,
        )
        detail = result.candidate.model_dump_json(indent=2) if result.candidate else ""
        scores.append(
            report.CaseScore(
                result.case_id, result.title, result.score, result.rationale, detail=detail
            )
        )
    return report.SetReport(set_name="distiller", floor=floor, scores=scores)


def run_planner_set(*, floor: float | None, langfuse: LangfuseClient) -> report.SetReport:
    cases = load_planner_cases()
    version = parse_prompt_version(PLANNER_PROMPT_PATH.read_text(encoding="utf-8"))
    scores = []
    for case in cases:
        result = planner_scorer.score_case(case)
        langfuse.log_case_run(
            set_name="planner",
            case_id=result.case_id,
            prompt_version=version,
            score=result.score,
            rationale=result.rationale,
        )
        detail = result.candidate.model_dump_json(indent=2) if result.candidate else ""
        scores.append(
            report.CaseScore(
                result.case_id, result.title, result.score, result.rationale, detail=detail
            )
        )
    return report.SetReport(set_name="planner", floor=floor, scores=scores)


def run_review_set(*, floor: float | None, langfuse: LangfuseClient) -> report.SetReport:
    cases = load_review_cases()
    version = parse_prompt_version(REVIEW_PROMPT_PATH.read_text(encoding="utf-8"))
    scores = []
    for case in cases:
        result = review_scorer.score_case(case)
        langfuse.log_case_run(
            set_name="review",
            case_id=result.case_id,
            prompt_version=version,
            score=result.score,
            rationale=result.rationale,
        )
        detail = result.candidate.model_dump_json(indent=2) if result.candidate else ""
        scores.append(
            report.CaseScore(
                result.case_id, result.title, result.score, result.rationale, detail=detail
            )
        )
    return report.SetReport(set_name="review", floor=floor, scores=scores)


_RUNNERS = {
    "dev": run_dev_set,
    "distiller": run_distiller_set,
    "planner": run_planner_set,
    "review": run_review_set,
}


def main(argv: list[str] | None = None) -> int:
    # Case data (raw CI logs, diffs) can contain non-ASCII markers (✗, ×, ·, em dashes);
    # a Windows console defaulting to cp1252 would otherwise crash on print().
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="python -m orchestrator.evals.runner")
    parser.add_argument("action", choices=["run"])
    parser.add_argument("--set", default="all", choices=["all", *_SCORABLE_SETS])
    parser.add_argument(
        "--only-changed",
        action="store_true",
        help="Only run sets whose prompt file changed vs origin/main (bounds CI spend)",
    )
    parser.add_argument("--base-ref", default="origin/main")
    args = parser.parse_args(argv)

    thresholds = load_thresholds()
    set_names = list(_SCORABLE_SETS) if args.set == "all" else [args.set]
    set_names = [name for name in set_names if not thresholds[name].not_yet_enforced]

    if args.only_changed:
        changed = _changed_prompt_files(args.base_ref)
        relevant = {
            "dev": "prompts/dev-agent.md",
            "distiller": "prompts/failure-distiller.md",
            "planner": "prompts/planner.md",
            "review": "prompts/review-agent.md",
        }
        set_names = [name for name in set_names if relevant[name] in changed]
        if not set_names:
            print("No relevant prompt files changed against", args.base_ref, "- skipping.")
            return 0

    langfuse = LangfuseClient()
    set_reports = [
        _RUNNERS[name](floor=thresholds[name].floor, langfuse=langfuse) for name in set_names
    ]
    langfuse.flush()

    report.write_junit(set_reports, report.RESULTS_DIR / "junit.xml")
    summary = report.write_markdown_summary(set_reports, report.RESULTS_DIR / "summary.md")
    print(summary)

    failed = [r for r in set_reports if not r.passed]
    if failed:
        print(f"FAILED sets: {[r.set_name for r in failed]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
