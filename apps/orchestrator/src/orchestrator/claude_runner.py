import json
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class TranscriptEvent:
    kind: str  # "message" | "tool_call" | "test_result" | "cost"
    payload: dict[str, object]


class ClaudeCodeRunner(Protocol):
    def run(
        self, *, prompt: str, cwd: Path, model: str, budget_usd: float, timeout_s: float
    ) -> Iterator[TranscriptEvent]: ...


class SubprocessClaudeCodeRunner:
    """Real implementation: spawns Claude Code headless in the sandbox worktree.

    Parses `claude -p <prompt> --output-format stream-json`'s newline-delimited JSON
    stream into TranscriptEvents. Not exercised by tests per the project's decision to
    use a hand-authored fixture instead of live API calls — see
    FixtureClaudeCodeRunner and tasks/CHANGELOG.md (T-006).
    """

    def run(
        self, *, prompt: str, cwd: Path, model: str, budget_usd: float, timeout_s: float
    ) -> Iterator[TranscriptEvent]:
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            raise RuntimeError(
                "claude CLI not found on PATH (npm install -g @anthropic-ai/claude-code)"
            )

        process = subprocess.Popen(
            [
                claude_bin,
                "-p",
                prompt,
                "--model",
                model,
                "--output-format",
                "stream-json",
                "--verbose",
                "--permission-mode",
                "acceptEdits",
            ],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        assert process.stdout is not None

        deadline = time.monotonic() + timeout_s
        try:
            for line in process.stdout:
                if time.monotonic() > deadline:
                    break
                line = line.strip()
                if not line:
                    continue
                event = _parse_stream_json_line(line)
                if event is not None:
                    yield event
        finally:
            if process.poll() is None:
                process.terminate()


def _content_blocks(raw: dict[str, object]) -> list[dict[str, object]]:
    message = raw.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


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
