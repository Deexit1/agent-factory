"""Proves `SandboxClaudeCodeRunner`'s own control flow (acquire -> exec -> parse ->
release) via a monkeypatched exec boundary — no Docker, no live API, no live Anthropic
key. Same "faked Popen" precedent `SubprocessClaudeCodeRunner`'s own docstring already
establishes (test_claude_runner.py); this fakes the `SandboxRuntime` protocol instead of
`subprocess.Popen` directly, since the exec boundary here is `docker exec`, not a bare
host subprocess."""

import threading
import time
from pathlib import Path

from orchestrator.sandbox_runner import SandboxClaudeCodeRunner


class _FakeApiClient:
    def __init__(self, domains: list[str]) -> None:
        self.domains = domains
        self.calls: list[str] = []
        self.usage_events: list[tuple[str, float]] = []

    def get_org_egress_rules(self, org_id: str) -> list[str]:
        self.calls.append(org_id)
        return self.domains

    def record_sandbox_usage_minutes(self, ticket_id: str, minutes: float) -> dict[str, object]:
        self.usage_events.append((ticket_id, minutes))
        return {"id": len(self.usage_events)}


class _FakeRuntime:
    def __init__(self, stdout_lines: list[str]) -> None:
        self._stdout_lines = stdout_lines
        self.created_networks: list[str] = []
        self.run_sandboxes: list[dict[str, object]] = []
        self.exec_streams: list[dict[str, object]] = []
        self.removed_containers: list[str] = []
        self.removed_networks: list[str] = []

    def create_network(self, ticket_id: str) -> str:
        self.created_networks.append(ticket_id)
        return f"net-{ticket_id}"

    def run_proxy(self, ticket_id, config, squid_conf_host_path):  # noqa: ANN001
        return f"proxy-{ticket_id}"

    def run_sandbox(
        self,
        ticket_id,
        config,
        worktree_host_path,
        git_token,
        extra_mount=None,
        extra_env=None,
        network=None,
        proxy_url=None,
    ):  # noqa: ANN001
        self.run_sandboxes.append(
            {
                "ticket_id": ticket_id,
                "worktree_host_path": worktree_host_path,
                "extra_env": extra_env,
            }
        )
        return f"sandbox-{ticket_id}"

    def exec_in(self, container: str, cmd: list[str]):  # noqa: ANN001
        class _Result:
            returncode = 0

        return _Result()

    def exec_stream(self, container: str, cmd: list[str], env=None):  # noqa: ANN001
        self.exec_streams.append({"container": container, "cmd": cmd, "env": env})
        yield from self._stdout_lines

    def teardown(self, ticket_id: str) -> None:
        pass

    def remove_container_named(self, name: str) -> None:
        self.removed_containers.append(name)

    def remove_network_named(self, name: str) -> None:
        self.removed_networks.append(name)


REAL_ASSISTANT_TEXT = (
    '{"type":"assistant","message":{"model":"claude-sonnet-5",'
    '"content":[{"type":"text","text":"Created hello.txt."}]},"session_id":"abc"}\n'
)
REAL_RESULT = (
    '{"type":"result","subtype":"success","is_error":false,'
    '"total_cost_usd":0.05,"usage":{"input_tokens":4,"output_tokens":10}}\n'
)


def _runner(tmp_path: Path, runtime: _FakeRuntime, api: _FakeApiClient) -> SandboxClaudeCodeRunner:
    prompt_path = tmp_path / "dev-agent.md"
    prompt_path.write_text("# System prompt", encoding="utf-8")
    return SandboxClaudeCodeRunner(
        api=api, system_prompt_path=prompt_path, runtime=runtime, pool_size=0
    )


def test_run_requires_org_id_and_ticket_id(tmp_path: Path) -> None:
    runtime = _FakeRuntime([])
    api = _FakeApiClient(["api.anthropic.com"])
    runner = _runner(tmp_path, runtime, api)

    raised = False
    try:
        list(
            runner.run(
                prompt="do the task",
                cwd=tmp_path,
                model="claude-sonnet-5",
                budget_usd=1.0,
                timeout_s=60.0,
            )
        )
    except ValueError:
        raised = True
    assert raised
    assert api.usage_events == []


def test_run_provisions_execs_and_tears_down(tmp_path: Path) -> None:
    runtime = _FakeRuntime([REAL_ASSISTANT_TEXT, REAL_RESULT])
    api = _FakeApiClient(["api.anthropic.com", "pypi.org"])
    runner = _runner(tmp_path, runtime, api)

    events = list(
        runner.run(
            prompt="do the task",
            cwd=tmp_path,
            model="claude-sonnet-5",
            budget_usd=1.0,
            timeout_s=60.0,
            anthropic_api_key="sk-ant-fake",
            org_id="org-1",
            ticket_id="T-1",
        )
    )

    assert api.calls == ["org-1"]
    assert len(runtime.run_sandboxes) == 1
    assert runtime.run_sandboxes[0]["ticket_id"] == "T-1"
    assert runtime.run_sandboxes[0]["extra_env"] == {
        "ANTHROPIC_API_KEY": "sk-ant-fake",
        "AGENT_FACTORY_ORG_ID": "org-1",
    }
    assert len(runtime.exec_streams) == 1
    assert runtime.exec_streams[0]["cmd"][0] == "claude"

    kinds = [e.kind for e in events]
    assert kinds == ["message", "cost"]
    assert events[-1].payload["total_cost_usd"] == 0.05

    # T-205: one sandbox_minutes usage event per run, measured from the real
    # HostPool.acquire()/release() bracket above.
    assert len(api.usage_events) == 1
    reported_ticket_id, reported_minutes = api.usage_events[0]
    assert reported_ticket_id == "T-1"
    assert reported_minutes >= 0.0


def test_run_releases_sandbox_even_on_exception(tmp_path: Path) -> None:
    class _ExplodingRuntime(_FakeRuntime):
        def exec_stream(self, container, cmd, env=None):  # noqa: ANN001
            raise RuntimeError("boom")
            yield  # pragma: no cover - unreachable, keeps this a generator

    runtime = _ExplodingRuntime([])
    api = _FakeApiClient(["api.anthropic.com"])
    runner = _runner(tmp_path, runtime, api)

    raised = False
    try:
        list(
            runner.run(
                prompt="do the task",
                cwd=tmp_path,
                model="claude-sonnet-5",
                budget_usd=1.0,
                timeout_s=60.0,
                org_id="org-1",
                ticket_id="T-2",
            )
        )
    except RuntimeError:
        raised = True
    assert raised
    assert len(runtime.run_sandboxes) == 1
    # T-205: a failed run still held the sandbox for real wall-clock time and must
    # still be billed for it — usage recording lives in the same finally block as the
    # lease release above, not gated on success.
    assert len(api.usage_events) == 1
    assert api.usage_events[0][0] == "T-2"


def test_host_pool_serializes_two_orgs_when_only_one_slot_exists(tmp_path: Path) -> None:
    """T-204 (SPEC-204 AC2): proves the HostPool integration actually gates real
    `run()` admission, not just apps/sandbox's own isolated scheduler tests — with
    host_slots=1, two concurrent runs from different orgs must never hold the slot
    (i.e. actually be doing exec work) at the same time.

    Measures the real-work interval (exec_stream's own entry/exit), not the thread's
    launch-to-finish span — a thread legitimately launches immediately and then blocks
    inside HostPool.acquire(), so the outer span is expected to overlap; only the
    inner "holding the lease and doing work" interval must not.
    """

    intervals: list[tuple[str, float, float]] = []
    lock = threading.Lock()

    class _SlowFakeRuntime(_FakeRuntime):
        def exec_stream(self, container, cmd, env=None):  # noqa: ANN001
            start = time.monotonic()
            time.sleep(0.08)
            with lock:
                intervals.append((container, start, time.monotonic()))
            yield from self._stdout_lines

    runtime = _SlowFakeRuntime([REAL_RESULT])
    api = _FakeApiClient(["api.anthropic.com"])
    prompt_path = tmp_path / "dev-agent.md"
    prompt_path.write_text("# System prompt", encoding="utf-8")
    runner = SandboxClaudeCodeRunner(
        api=api, system_prompt_path=prompt_path, runtime=runtime, pool_size=0, host_slots=1
    )

    def _worker(org_id: str, ticket_id: str) -> None:
        list(
            runner.run(
                prompt="do the task",
                cwd=tmp_path,
                model="claude-sonnet-5",
                budget_usd=1.0,
                timeout_s=10.0,
                org_id=org_id,
                ticket_id=ticket_id,
            )
        )

    threads = [
        threading.Thread(target=_worker, args=("org-a", "T-a")),
        threading.Thread(target=_worker, args=("org-b", "T-b")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10.0)

    assert len(intervals) == 2
    intervals.sort(key=lambda i: i[1])
    (_, _start_first, end_first), (_, start_second, _end_second) = intervals
    assert start_second >= end_first, f"work intervals overlapped: {intervals}"
