"""Real Docker proof that `docker_runtime.exec_stream` genuinely streams a running
container's stdout line-by-line, not just an argv-shape claim — this is the exact
boundary `orchestrator.sandbox_runner.SandboxClaudeCodeRunner` execs `claude` through
in the real dev-agent path (T-204). `SandboxClaudeCodeRunner`'s own control flow
(acquire -> exec -> parse -> release) is proven separately with a monkeypatched
runtime (apps/orchestrator/tests/test_sandbox_runner.py, same "faked exec boundary"
precedent claude_runner.py's own tests already established) — this file is the one
piece that needs a real container to mean anything."""

from pathlib import Path

from sandbox import cli, docker_runtime
from sandbox.config import SandboxConfig


def test_exec_stream_yields_real_multiline_stdout_from_a_running_container(
    ticket_id: str, origin_repo: Path
) -> None:
    config = SandboxConfig(api_url="http://127.0.0.1:1")
    cli.up(ticket_id, str(origin_repo), "main", config)
    try:
        name = docker_runtime.sandbox_name(ticket_id)
        lines = list(
            docker_runtime.exec_stream(
                name, ["sh", "-c", "echo line-one; echo line-two; echo line-three"]
            )
        )
        assert [line.strip() for line in lines] == ["line-one", "line-two", "line-three"]
    finally:
        cli.down(ticket_id)


def test_exec_stream_passes_env_into_the_running_container(
    ticket_id: str, origin_repo: Path
) -> None:
    config = SandboxConfig(api_url="http://127.0.0.1:1")
    cli.up(ticket_id, str(origin_repo), "main", config)
    try:
        name = docker_runtime.sandbox_name(ticket_id)
        lines = list(
            docker_runtime.exec_stream(
                name, ["sh", "-c", "echo $MY_TEST_VAR"], env={"MY_TEST_VAR": "hello-from-env"}
            )
        )
        assert [line.strip() for line in lines] == ["hello-from-env"]
    finally:
        cli.down(ticket_id)
