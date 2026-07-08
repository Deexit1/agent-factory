import json
import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# apps/orchestrator/src/orchestrator/claude_runner.py -> repo root is 4 parents up.
# Orchestrator always runs from a checkout of this repo (it has no standalone
# deployment/Dockerfile in this phase - see docs/01-architecture.md's layer split), so a
# repo-relative default is safe; callers that need a different prompt (tests, evals) pass
# `system_prompt_path` explicitly.
_REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_DEV_AGENT_PROMPT_PATH = _REPO_ROOT / "prompts" / "dev-agent.md"


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str  # "message" | "tool_call" | "test_result" | "cost"
    payload: dict[str, object]


class ClaudeCodeRunner(Protocol):
    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        model: str,
        budget_usd: float,
        timeout_s: float,
        anthropic_api_key: str | None = None,
    ) -> Iterator[TranscriptEvent]: ...


class SubprocessClaudeCodeRunner:
    """Real implementation: spawns Claude Code headless in the sandbox worktree.

    Parses `claude -p <prompt> --output-format stream-json`'s newline-delimited JSON
    stream into TranscriptEvents. Not exercised against a real API by tests per the
    project's decision to use a hand-authored fixture instead of live API calls — see
    FixtureClaudeCodeRunner and tasks/CHANGELOG.md (T-006). The subprocess invocation
    itself (argv construction) is covered by test_claude_runner.py via a faked Popen.
    """

    # Defensive: retry a first-turn API error before surfacing it as a real failure.
    # T-009 hit this ~100% of the time with an outdated `claude` CLI (2.1.50) paired with
    # ANTHROPIC_API_KEY auth + the newest model - retrying never helped, upgrading the CLI
    # to 2.1.201 did. Kept as a small safety net for genuine transient API errors, which
    # this exact detection can't distinguish from a systematic one - if this starts firing
    # often, check `claude update` before assuming the API is flaky.
    _MAX_TRANSIENT_RETRIES = 2
    _RETRY_BACKOFF_S = 3.0

    def __init__(self, system_prompt_path: Path = DEFAULT_DEV_AGENT_PROMPT_PATH) -> None:
        self._system_prompt_path = system_prompt_path

    def run(
        self,
        *,
        prompt: str,
        cwd: Path,
        model: str,
        budget_usd: float,
        timeout_s: float,
        anthropic_api_key: str | None = None,
    ) -> Iterator[TranscriptEvent]:
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH (npm install -g @anthropic-ai/claude-code)"
            )

        # T-101: prompts/dev-agent.md is a versioned artifact (CLAUDE.md) but was never
        # actually reaching the CLI before this - build_prompt() only assembles the
        # per-task TaskSpec/FailureReport content. Without this, the golden-set eval could
        # never detect a dev-agent.md regression, since degrading it would change nothing
        # about a real run.
        system_prompt = self._system_prompt_path.read_text(encoding="utf-8")

        # T-202 (SPEC-202): the org's own key, scoped to this subprocess's env only —
        # never written to a TranscriptEvent payload, never part of argv (unlike
        # --append-system-prompt's content, a separate pre-existing exposure this
        # ticket doesn't touch). None preserves the pre-BYOK behavior exactly: the
        # subprocess inherits whatever ANTHROPIC_API_KEY is already in this process's
        # environment (local dev / tests that pass no key explicitly).
        subprocess_env = (
            {**os.environ, "ANTHROPIC_API_KEY": anthropic_api_key}
            if anthropic_api_key
            else None
        )

        deadline = time.monotonic() + timeout_s
        for attempt in range(self._MAX_TRANSIENT_RETRIES + 1):
            process = subprocess.Popen(
                [
                    claude_bin,
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
                ],
                cwd=cwd,
                env=subprocess_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            assert process.stdout is not None

            yielded_any = False
            retry = False
            try:
                for line in process.stdout:
                    if time.monotonic() > deadline:
                        break
                    line = line.strip()
                    if not line:
                        continue
                    event = _parse_stream_json_line(line)
                    if event is None:
                        continue
                    # Only retry if it's the first thing this attempt produced, so a real
                    # mid-run failure still surfaces normally.
                    if not yielded_any and event.kind == "message" and _is_transient_api_error(
                        event.payload
                    ):
                        retry = attempt < self._MAX_TRANSIENT_RETRIES
                        break
                    yielded_any = True
                    yield event
            finally:
                if process.poll() is None:
                    process.terminate()

            if not retry:
                return
            time.sleep(self._RETRY_BACKOFF_S)


def _content_blocks(raw: dict[str, object]) -> list[dict[str, object]]:
    message = raw.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def _is_transient_api_error(payload: dict[str, object]) -> bool:
    blocks = _content_blocks(payload)
    if payload.get("error") != "unknown" or len(blocks) != 1:
        return False
    block = blocks[0]
    text = block.get("text")
    return block.get("type") == "text" and isinstance(text, str) and text.startswith("API Error:")


def _parse_stream_json_line(line: str) -> TranscriptEvent | None:
    try:
        raw = json.loads(line)
    except json.JSONDecodeError:
        return None

    msg_type = raw.get("type")
    if msg_type == "assistant":
        # Tool calls arrive nested in an assistant message's content blocks, not as a
        # distinct top-level event type - classify by what's actually inside.
        is_tool_call = any(b.get("type") == "tool_use" for b in _content_blocks(raw))
        return TranscriptEvent(kind="tool_call" if is_tool_call else "message", payload=raw)
    if msg_type == "user":
        # Tool results come back as a "user" turn containing a tool_result block.
        if any(b.get("type") == "tool_result" for b in _content_blocks(raw)):
            return TranscriptEvent(kind="tool_call", payload=raw)
        return None
    if msg_type == "result":
        usage = raw.get("usage", {})
        return TranscriptEvent(
            kind="cost",
            payload={
                "total_cost_usd": raw.get("total_cost_usd", 0),
                "tokens_in": usage.get("input_tokens", 0),
                "tokens_out": usage.get("output_tokens", 0),
            },
        )
    return None
