"""Proves `MicroVMRuntime`'s own control flow (argv shapes against `ctr`) via a
monkeypatched `subprocess.run`/`subprocess.Popen` — the same fault-injection precedent
T-203 used for `respx` against `api.github.com`. This does NOT prove a real Firecracker
VM boots; no hypervisor is reachable in this environment. See runtime.py's docstring."""

import subprocess

from sandbox.config import SandboxConfig
from sandbox.runtime import MicroVMRuntime


class _FakeCompletedProcess:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_run_sandbox_invokes_ctr_with_firecracker_runtime(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(args, **kwargs):
        captured.append(args)
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    runtime = MicroVMRuntime()
    name = runtime.run_sandbox("T-1", SandboxConfig(), "/host/wt", "git-token")

    assert name == "sandbox-T-1"
    assert len(captured) == 1
    args = captured[0]
    assert args[0] == "ctr"
    assert "--runtime" in args
    assert args[args.index("--runtime") + 1] == "aws.firecracker"
    assert "sandbox-T-1" in args


def test_run_sandbox_raises_on_nonzero_exit(monkeypatch) -> None:
    def fake_run(args, **kwargs):
        return _FakeCompletedProcess(returncode=1, stderr="no such runtime")

    monkeypatch.setattr(subprocess, "run", fake_run)

    runtime = MicroVMRuntime()
    try:
        runtime.run_sandbox("T-1", SandboxConfig(), "/host/wt", "git-token")
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "no such runtime" in str(exc)
    assert raised


def test_exec_stream_streams_stdout_lines(monkeypatch) -> None:
    class _FakeProcess:
        def __init__(self) -> None:
            self.stdout = iter(["line1\n", "line2\n"])
            self._polled = False

        def poll(self):
            return 0 if self._polled else None

        def terminate(self):
            self._polled = True

    captured: list[list[str]] = []

    def fake_popen(args, **kwargs):
        captured.append(args)
        return _FakeProcess()

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    runtime = MicroVMRuntime()
    lines = list(runtime.exec_stream("sandbox-T-1", ["echo", "hi"], env={"FOO": "bar"}))

    assert lines == ["line1\n", "line2\n"]
    args = captured[0]
    assert args[0] == "ctr"
    assert "sandbox-T-1" in args
    assert "echo" in args and "hi" in args


def test_teardown_kills_and_removes_sandbox_and_proxy(monkeypatch) -> None:
    captured: list[list[str]] = []

    def fake_run(args, **kwargs):
        captured.append(args)
        return _FakeCompletedProcess(returncode=0)

    monkeypatch.setattr(subprocess, "run", fake_run)

    MicroVMRuntime().teardown("T-1")

    joined = [" ".join(a) for a in captured]
    assert any("task kill" in c and "sandbox-T-1" in c for c in joined)
    assert any("container rm" in c and "sandbox-T-1" in c for c in joined)
    assert any("sandbox-T-1-proxy" in c for c in joined)
