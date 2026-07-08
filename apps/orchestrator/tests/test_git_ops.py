from pathlib import Path

import pytest

from orchestrator import git_ops


def _fail_if_called(*args: object, **kwargs: object) -> None:
    raise AssertionError("subprocess.run must not be called when the branch guard fires")


def test_push_to_main_is_refused_before_any_subprocess_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_ops.subprocess, "run", _fail_if_called)

    with pytest.raises(git_ops.BranchNotAllowed):
        git_ops.push(tmp_path, "main")


def test_force_push_to_main_is_refused_before_any_subprocess_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(git_ops.subprocess, "run", _fail_if_called)

    with pytest.raises(git_ops.BranchNotAllowed):
        git_ops.force_push(tmp_path, "main")


def test_push_to_an_agent_branch_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        git_ops.subprocess,
        "run",
        lambda args, **kw: calls.append(args) or _FakeCompleted(),
    )

    git_ops.push(tmp_path, "agent/T-203")

    assert calls
    assert calls[0][-2:] == ["origin", "HEAD:agent/T-203"]


def test_build_auth_header_base64_encodes_x_access_token() -> None:
    header = git_ops.build_auth_header("ghs_faketoken")

    assert header.startswith("AUTHORIZATION: basic ")
    import base64

    encoded = header.removeprefix("AUTHORIZATION: basic ")
    assert base64.b64decode(encoded).decode() == "x-access-token:ghs_faketoken"


def test_push_injects_the_auth_header_as_a_git_dash_c_arg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        git_ops.subprocess,
        "run",
        lambda args, **kw: calls.append(args) or _FakeCompleted(),
    )

    git_ops.push(tmp_path, "agent/T-203", auth_header="AUTHORIZATION: basic abc123")

    assert "-c" in calls[0]
    idx = calls[0].index("-c")
    assert calls[0][idx + 1] == "http.extraheader=AUTHORIZATION: basic abc123"


def test_push_omits_extraheader_arg_when_auth_header_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        git_ops.subprocess,
        "run",
        lambda args, **kw: calls.append(args) or _FakeCompleted(),
    )

    git_ops.push(tmp_path, "agent/T-203")

    assert "-c" not in calls[0]


class _FakeCompleted:
    returncode = 0
    stdout = ""
    stderr = ""
