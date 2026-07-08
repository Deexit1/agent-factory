"""T-204 (SPEC-204): the real dev-agent execution path through apps/sandbox, closing
the gap disclosed since T-105/106/107 — `SubprocessClaudeCodeRunner` (claude_runner.py)
spawns `claude` as a bare host subprocess against a plain git worktree; this module execs
it inside an isolated, org-scoped Docker sandbox container instead. Implements the same
`ClaudeCodeRunner` Protocol, so `agents/dev.py`'s call site is unchanged beyond passing
`org_id`/`ticket_id` through — see claude_runner.py's Protocol docstring.

Reuses `claude_runner.py`'s private NDJSON-parsing helpers verbatim rather than
duplicating them, so the retry-on-transient-API-error behavior matches
`SubprocessClaudeCodeRunner`'s exactly.
"""

import time
from collections.abc import Iterator
from pathlib import Path

from sandbox.config import STATE_DIR, SandboxConfig, org_state_dir_for
from sandbox.pool import SandboxPool
from sandbox.runtime import DockerRuntime, SandboxRuntime
from sandbox.scheduler import HostPool

from orchestrator.api_client import ApiClient
from orchestrator.claude_runner import (
    DEFAULT_DEV_AGENT_PROMPT_PATH,
    TranscriptEvent,
    _is_transient_api_error,
    _parse_stream_json_line,
)

_MAX_TRANSIENT_RETRIES = 2
_RETRY_BACKOFF_S = 3.0


class SandboxClaudeCodeRunner:
    """Real implementation: execs Claude Code headless inside an org-scoped, pre-warmed
    sandbox container (apps/sandbox), instead of on the bare orchestrator host.

    One instance is meant to be reused across many `run()` calls — it owns the
    `SandboxPool` (and its pre-warmed idle slots) and the `HostPool` scheduler, not a
    single ticket's lifecycle. Every `run()` first acquires a `HostPool` slot lease
    before provisioning a container — this is what makes AC2's "two orgs never
    co-locate" guarantee real for actual ticket dispatch, not just apps/sandbox's own
    isolated scheduler tests (see scheduler.py's module docstring for its honest scope:
    one process, one host, today's actual deployment shape).
    """

    def __init__(
        self,
        *,
        api: ApiClient,
        system_prompt_path: Path = DEFAULT_DEV_AGENT_PROMPT_PATH,
        runtime: SandboxRuntime | None = None,
        pool_size: int = 2,
        host_slots: int = 4,
        sandbox_config: SandboxConfig | None = None,
    ) -> None:
        self._api = api
        self._system_prompt_path = system_prompt_path
        self._config = sandbox_config or SandboxConfig()
        self._runtime = runtime or DockerRuntime()
        self._pool = SandboxPool(
            runtime=self._runtime,
            config=self._config,
            pool_size=pool_size,
            state_root=STATE_DIR / "pool",
        )
        self._host_pool = HostPool(host_slots=host_slots)
        self._warmed = False

    def close(self) -> None:
        """Tear down every remaining pre-warmed idle slot. Without this, a process
        using this runner across many tickets and then exiting would leak every idle
        network+proxy pair the pool ever pre-warmed — see SandboxPool.shutdown()."""
        self._pool.shutdown()

    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        model: str,
        budget_usd: float,
        timeout_s: float,
        anthropic_api_key: str | None = None,
        org_id: str | None = None,
        ticket_id: str | None = None,
    ) -> Iterator[TranscriptEvent]:
        if org_id is None or ticket_id is None:
            raise ValueError(
                "SandboxClaudeCodeRunner.run() requires org_id and ticket_id "
                "(agents/dev.py's call site threads both through)"
            )
        if not self._warmed:
            self._pool.warm()
            self._warmed = True

        allowed_domains = self._api.get_org_egress_rules(org_id)
        extra_env = {"ANTHROPIC_API_KEY": anthropic_api_key} if anthropic_api_key else None

        # AC2: admission into the scheduler's slot pool gates provisioning itself — no
        # sandbox container is created until a slot is actually held, so two orgs never
        # co-locate on the same logical VM slot at once.
        lease = self._host_pool.acquire(org_id=org_id, ticket_id=ticket_id, timeout_s=timeout_s)
        try:
            org_state_dir_for(org_id, ticket_id).mkdir(parents=True, exist_ok=True)
            container = self._pool.acquire_for(
                org_id=org_id,
                ticket_id=ticket_id,
                worktree_host_path=str(cwd),
                allowed_domains=allowed_domains,
                extra_env=extra_env,
            )
            try:
                yield from self._exec_claude(
                    container,
                    prompt=prompt,
                    model=model,
                    timeout_s=timeout_s,
                )
            finally:
                self._pool.release(ticket_id)
        finally:
            self._host_pool.release(lease)

    def _exec_claude(
        self, container: str, *, prompt: str, model: str, timeout_s: float
    ) -> Iterator[TranscriptEvent]:
        system_prompt = self._system_prompt_path.read_text(encoding="utf-8")
        cmd = [
            "claude",
            "-p",
            prompt,
            "--model",
            model,
            "--append-system-prompt",
            system_prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-mode",
            "acceptEdits",
        ]

        deadline = time.monotonic() + timeout_s
        for attempt in range(_MAX_TRANSIENT_RETRIES + 1):
            yielded_any = False
            retry = False
            for line in self._runtime.exec_stream(container, cmd):
                if time.monotonic() > deadline:
                    break
                line = line.strip()
                if not line:
                    continue
                event = _parse_stream_json_line(line)
                if event is None:
                    continue
                if not yielded_any and event.kind == "message" and _is_transient_api_error(
                    event.payload
                ):
                    retry = attempt < _MAX_TRANSIENT_RETRIES
                    break
                yielded_any = True
                yield event

            if not retry:
                return
            time.sleep(_RETRY_BACKOFF_S)
