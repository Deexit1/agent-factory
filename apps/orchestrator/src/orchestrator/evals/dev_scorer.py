"""Scores prompts/dev-agent.md against evals/dev/cases (SPEC-101).

Each case gets a real, disposable workspace (a local `git clone` for "repo_snapshot"
cases pinned to a pre-recorded SHA, or a fresh git-initialised copy of embedded
"standalone" fixture files) and a LIVE SubprocessClaudeCodeRunner invocation - this is
the only way a dev-agent.md regression can actually be detected, since a canned
transcript replay would produce the same diff regardless of prompt content.
"""

import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from orchestrator.agents.prompt import build_prompt
from orchestrator.claude_runner import ClaudeCodeRunner
from orchestrator.evals.judge import JudgeFn, haiku_judge
from orchestrator.evals.loader import DevCase

_REPO_ROOT = Path(__file__).resolve().parents[5]
_DEV_MODEL = "claude-sonnet-5"
_DEFAULT_TIMEOUT_S = 600.0
_TEST_TIMEOUT_S = 120.0
_GIT_IDENTITY = ["-c", "user.email=eval@agent-factory.local", "-c", "user.name=eval-harness"]
_WORD_RE = re.compile(r"[a-zA-Z]{4,}")


@dataclass(frozen=True)
class DevCaseResult:
    case_id: str
    title: str
    deterministic_score: float
    judge_score: float
    score: float  # 0-100, combined
    rationale: str
    cost_usd: float
    diff: str
    error: str | None = None


def _venv_python(venv_dir: Path) -> Path:
    if sys.platform == "win32":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def _run(
    argv: list[str], *, cwd: Path, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, timeout=timeout, check=False
    )


def _prepare_workspace(case: DevCase, scratch: Path) -> str:
    """Returns the starting commit SHA to diff against once the agent has run."""
    if case.starter_kind == "repo_snapshot":
        assert case.starter_ref is not None
        _run(["git", "clone", "--quiet", str(_REPO_ROOT), str(scratch)], cwd=_REPO_ROOT)
        _run(["git", "checkout", "--quiet", case.starter_ref], cwd=scratch)
    else:
        assert case.starter_dir is not None
        shutil.copytree(case.starter_dir, scratch, dirs_exist_ok=True)
        _run(["git", "init", "--quiet"], cwd=scratch)
        _run(["git", "add", "-A"], cwd=scratch)
        _run(["git", *_GIT_IDENTITY, "commit", "--quiet", "-m", "starter"], cwd=scratch)

    result = _run(["git", "rev-parse", "HEAD"], cwd=scratch)
    return result.stdout.strip()


def _ensure_subpackage_venv(working_dir: Path) -> Path:
    """Mirrors the Makefile's per-app venv convention for a freshly cloned checkout,
    which has no .venv (it's gitignored)."""
    venv_dir = working_dir / ".venv"
    python = _venv_python(venv_dir)
    if python.exists():
        return python

    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], cwd=working_dir, check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--upgrade", "pip", "-q"], check=True)
    schemas_dir = working_dir.parents[1] / "packages" / "schemas"
    if schemas_dir.exists():
        subprocess.run(
            [str(python), "-m", "pip", "install", "-e", str(schemas_dir), "-q"], check=True
        )
    subprocess.run(
        [str(python), "-m", "pip", "install", "-e", ".[dev]", "-q"], cwd=working_dir, check=True
    )
    return python


def _as_number(value: object, default: float) -> float:
    return float(value) if isinstance(value, int | float) else default


def _run_agent(case: DevCase, workspace: Path, claude_runner: ClaudeCodeRunner) -> float:
    prompt = build_prompt(case.task_spec, None, 1)
    cumulative_cost = 0.0
    for event in claude_runner.run(
        prompt=prompt,
        cwd=workspace,
        model=_DEV_MODEL,
        budget_usd=case.task_spec.budget_usd,
        timeout_s=_DEFAULT_TIMEOUT_S,
    ):
        if event.kind == "cost":
            cumulative_cost = _as_number(event.payload.get("total_cost_usd"), cumulative_cost)
        if cumulative_cost > case.task_spec.budget_usd:
            break
    return cumulative_cost


def _diff_and_changed_paths(workspace: Path, starting_sha: str) -> tuple[str, list[str]]:
    # `git diff <sha>` only considers paths already in the index or in <sha>'s tree - a
    # brand-new file the agent created but never `git add`ed is invisible to it
    # otherwise, which would silently hide both real work and out-of-scope edits.
    # Staging everything here is side-effect-free: this workspace is a disposable scratch
    # clone we're about to discard regardless of outcome.
    _run(["git", "add", "-A"], cwd=workspace)
    diff = _run(["git", "diff", "--cached", starting_sha], cwd=workspace).stdout
    names = _run(["git", "diff", "--cached", "--name-only", starting_sha], cwd=workspace).stdout
    changed_paths = [line.strip() for line in names.splitlines() if line.strip()]
    return diff, changed_paths


def _run_verification(case: DevCase, workspace: Path) -> tuple[bool, float | None, str]:
    """Returns (overall tests passed, criteria-node-ids score or None, log tail).

    The criteria score runs pytest against ONLY the acceptance criteria's own
    `verification` node IDs (when they look like pytest node IDs) - a case-level
    "don't touch the test file" constraint (e.g. evals/dev/cases/dev-005) means a
    correct fix may legitimately never modify the verification file, so "was that file
    changed" is not a safe proxy for "did its test pass". Returns None when no AC
    verification string looks like a node ID, so the caller can fall back to the
    overall test_command result instead.
    """
    if case.verification.mode != "pytest":
        return True, None, "manual verification mode - no automated test run"

    assert case.verification.test_command is not None
    test_dir = (
        workspace / case.verification.working_dir if case.verification.working_dir else workspace
    )

    if case.starter_kind == "repo_snapshot":
        python = _ensure_subpackage_venv(test_dir)
    else:
        python = Path(sys.executable)

    args = [str(python), "-m", "pytest", *shlex.split(case.verification.test_command)]
    try:
        result = _run(args, cwd=test_dir, timeout=_TEST_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return False, 0.0, "test command timed out"
    tests_passed = result.returncode == 0
    detail = (result.stdout + result.stderr)[-2000:]

    node_ids = [
        ac.verification for ac in case.task_spec.acceptance_criteria if "::" in ac.verification
    ]
    if not node_ids:
        return tests_passed, None, detail
    try:
        criteria_result = _run(
            [str(python), "-m", "pytest", *node_ids, "-q"], cwd=test_dir, timeout=_TEST_TIMEOUT_S
        )
    except subprocess.TimeoutExpired:
        return tests_passed, 0.0, detail
    return tests_passed, (1.0 if criteria_result.returncode == 0 else 0.0), detail


def _scope_score(case: DevCase, changed_paths: list[str]) -> float:
    if not case.verification.allowed_paths:
        return 1.0
    if not changed_paths:
        return 0.0
    allowed = set(case.verification.allowed_paths)
    out_of_scope = [p for p in changed_paths if p not in allowed]
    return 1.0 - (len(out_of_scope) / len(changed_paths))


def _added_lines(diff_text: str) -> str:
    return "\n".join(
        line[1:]
        for line in diff_text.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _keywords(diff_text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(_added_lines(diff_text))}


def _dimension_scores(
    case: DevCase,
    *,
    produced_changes: bool,
    tests_passed: bool,
    criteria_score: float | None,
    changed_paths: list[str],
    diff: str,
) -> dict[str, float]:
    weights = case.rubric_weights
    scores: dict[str, float] = {}

    if "tests_pass" in weights:
        scores["tests_pass"] = 1.0 if tests_passed else 0.0
    if "criteria_test_mapping" in weights:
        # criteria_score is None when no AC verification string is a pytest node ID
        # (e.g. manual-mode doc cases) - overall tests_passed is the only signal then.
        scores["criteria_test_mapping"] = (
            criteria_score if criteria_score is not None else (1.0 if tests_passed else 0.0)
        )
    if "criteria_coverage" in weights:
        reference_keywords = _keywords(case.reference_patch)
        candidate_keywords = _keywords(diff)
        scores["criteria_coverage"] = (
            len(reference_keywords & candidate_keywords) / len(reference_keywords)
            if reference_keywords
            else 1.0
        )
    if "factual_accuracy" in weights:
        # No reliable deterministic signal for factual correctness of prose - left to
        # the judge; score neutrally here so it doesn't skew the deterministic half.
        scores["factual_accuracy"] = 0.5
    if "no_out_of_scope_edits" in weights:
        scores["no_out_of_scope_edits"] = _scope_score(case, changed_paths)

    if not produced_changes:
        scores = dict.fromkeys(scores, 0.0)
    return scores


def _weighted_average(scores: dict[str, float], weights: dict[str, float]) -> float:
    total_weight = sum(weights.get(k, 0.0) for k in scores) or 1.0
    weighted = sum(scores[k] * weights.get(k, 0.0) for k in scores)
    return (weighted / total_weight) * 100


def score_case(
    case: DevCase,
    *,
    claude_runner: ClaudeCodeRunner,
    judge: JudgeFn = haiku_judge,
) -> DevCaseResult:
    with tempfile.TemporaryDirectory(prefix="eval-dev-") as scratch_str:
        scratch = Path(scratch_str)
        try:
            starting_sha = _prepare_workspace(case, scratch)
            cost_usd = _run_agent(case, scratch, claude_runner)
            diff, changed_paths = _diff_and_changed_paths(scratch, starting_sha)
            tests_passed, criteria_score, _detail = _run_verification(case, scratch)
        except Exception as exc:  # noqa: BLE001 - any failure here is a real 0-score result
            return DevCaseResult(
                case_id=case.case_id,
                title=case.title,
                deterministic_score=0.0,
                judge_score=0.0,
                score=0.0,
                rationale=f"case run failed: {exc}",
                cost_usd=0.0,
                diff="",
                error=str(exc),
            )

    produced_changes = bool(diff.strip())
    dimension_scores = _dimension_scores(
        case,
        produced_changes=produced_changes,
        tests_passed=tests_passed,
        criteria_score=criteria_score,
        changed_paths=changed_paths,
        diff=diff,
    )
    deterministic_score = _weighted_average(dimension_scores, case.rubric_weights)

    verdict = judge(
        set_name="dev",
        case_title=case.title,
        reference=case.reference_patch,
        candidate=diff or "(agent produced no changes)",
    )
    # Deterministic checks anchor the score for measurable dimensions (tests/scope); the
    # judge covers everything text-quality-shaped (coverage, factual accuracy) that no
    # deterministic check here can verify.
    combined = 0.6 * deterministic_score + 0.4 * verdict.score
    return DevCaseResult(
        case_id=case.case_id,
        title=case.title,
        deterministic_score=deterministic_score,
        judge_score=verdict.score,
        score=combined,
        rationale=verdict.rationale,
        cost_usd=cost_usd,
        diff=diff,
    )
