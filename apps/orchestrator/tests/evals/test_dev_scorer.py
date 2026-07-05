from collections.abc import Iterator
from pathlib import Path

from schemas import AcceptanceCriterion, Complexity, TaskSpec

from orchestrator.claude_runner import TranscriptEvent
from orchestrator.evals import dev_scorer
from orchestrator.evals.judge import JudgeVerdict
from orchestrator.evals.loader import DevCase, DevVerification


def _task_spec() -> TaskSpec:
    return TaskSpec(
        id="EVAL-TEST-1",
        title="Set X to 2",
        context="X should be 2.",
        acceptance_criteria=[
            AcceptanceCriterion(
                id="AC-1", description="X is 2", verification="test_app.py::test_x_is_two"
            )
        ],
        complexity=Complexity.LOW,
        budget_usd=1.0,
    )


def _case(tmp_path: Path, **overrides: object) -> DevCase:
    starter_dir = tmp_path / "starter"
    starter_dir.mkdir()
    (starter_dir / "app.py").write_text("X = 1\n")
    (starter_dir / "test_app.py").write_text("def test_placeholder():\n    assert True\n")

    defaults: dict[str, object] = dict(
        case_id="dev-test-1",
        title="bump X",
        source="synthetic",
        starter_kind="standalone",
        starter_ref=None,
        starter_dir=starter_dir,
        task_spec=_task_spec(),
        verification=DevVerification(
            mode="pytest", test_command="test_app.py -q", allowed_paths=("app.py", "test_app.py")
        ),
        reference_patch="--- a/app.py\n+++ b/app.py\n@@\n-X = 1\n+X = 2\n",
        rubric_weights={
            "tests_pass": 0.5,
            "criteria_test_mapping": 0.3,
            "no_out_of_scope_edits": 0.2,
        },
        case_dir=tmp_path,
    )
    defaults.update(overrides)
    return DevCase(**defaults)  # type: ignore[arg-type]


class _FakeClaudeCodeRunner:
    def __init__(self, edit) -> None:  # noqa: ANN001 - test double, keep it simple
        self._edit = edit

    def run(
        self, *, prompt: str, cwd: Path, model: str, budget_usd: float, timeout_s: float
    ) -> Iterator[TranscriptEvent]:
        self._edit(cwd)
        yield TranscriptEvent(
            kind="cost", payload={"total_cost_usd": 0.01, "tokens_in": 10, "tokens_out": 10}
        )


def _correct_fix(cwd: Path) -> None:
    (cwd / "app.py").write_text("X = 2\n")
    (cwd / "test_app.py").write_text(
        "def test_placeholder():\n    assert True\n\n\ndef test_x_is_two():\n"
        "    from app import X\n    assert X == 2\n"
    )


def _no_op(_cwd: Path) -> None:
    pass


def _out_of_scope_edit(cwd: Path) -> None:
    (cwd / "app.py").write_text("X = 2\n")
    (cwd / "test_app.py").write_text(
        "def test_placeholder():\n    assert True\n\n\ndef test_x_is_two():\n"
        "    from app import X\n    assert X == 2\n"
    )
    (cwd / "unrelated.py").write_text("# scope creep\n")


def _fake_judge(*, score: float, rationale: str) -> object:
    def judge(**_kwargs: object) -> JudgeVerdict:
        return JudgeVerdict(score=score, rationale=rationale)

    return judge


def test_score_case_scores_a_correct_fix_highly(tmp_path: Path) -> None:
    case = _case(tmp_path)
    result = dev_scorer.score_case(
        case,
        claude_runner=_FakeClaudeCodeRunner(_correct_fix),
        judge=_fake_judge(score=95.0, rationale="matches reference"),  # type: ignore[arg-type]
    )

    assert result.error is None
    assert result.deterministic_score == 100.0
    assert result.judge_score == 95.0
    assert result.score == 0.6 * 100.0 + 0.4 * 95.0


def test_score_case_scores_zero_when_agent_produces_no_changes(tmp_path: Path) -> None:
    case = _case(tmp_path)
    result = dev_scorer.score_case(
        case,
        claude_runner=_FakeClaudeCodeRunner(_no_op),
        judge=_fake_judge(score=0.0, rationale="no changes"),  # type: ignore[arg-type]
    )

    assert result.deterministic_score == 0.0
    assert result.diff == ""


def test_score_case_penalises_out_of_scope_edits(tmp_path: Path) -> None:
    case = _case(tmp_path)
    result = dev_scorer.score_case(
        case,
        claude_runner=_FakeClaudeCodeRunner(_out_of_scope_edit),
        judge=_fake_judge(score=95.0, rationale="matches reference"),  # type: ignore[arg-type]
    )

    # tests_pass + criteria_test_mapping still perfect, but no_out_of_scope_edits drops:
    # 2/3 changed files were in allowed_paths -> scope score 2/3.
    assert result.deterministic_score < 100.0


def test_scope_score_with_no_allowed_paths_declared(tmp_path: Path) -> None:
    case = _case(tmp_path, verification=DevVerification(mode="manual", allowed_paths=()))
    assert dev_scorer._scope_score(case, ["anything.py"]) == 1.0


def test_scope_score_zero_when_nothing_changed(tmp_path: Path) -> None:
    case = _case(tmp_path)
    assert dev_scorer._scope_score(case, []) == 0.0


def test_keywords_extracts_only_added_lines() -> None:
    diff = "+++ b/app.py\n+added_word\n-removed_word\n context_word\n"
    assert dev_scorer._keywords(diff) == {"added", "word"}
