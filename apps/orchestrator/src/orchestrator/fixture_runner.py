import json
import shutil
from collections.abc import Iterator
from pathlib import Path

from orchestrator.claude_runner import TranscriptEvent


class FixtureClaudeCodeRunner:
    """Replays a recorded transcript instead of invoking the real `claude` CLI.

    `fixture_dir` must contain `transcript.jsonl` (one TranscriptEvent per line) and
    optionally `workspace_diff/` (files copied into `cwd` once the transcript finishes
    streaming, simulating the edits Claude Code would have made on disk).

    Records the last prompt and model it was called with, for tests that assert on
    injected context (e.g. that a FailureReport/attempt number reached the agent, or
    T-105: that a profile's model actually reached the runner).
    """

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir
        self.last_prompt: str | None = None
        self.last_model: str | None = None
        self.last_anthropic_api_key: str | None = None

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
        self.last_prompt = prompt
        self.last_model = model
        self.last_anthropic_api_key = anthropic_api_key

        transcript_path = self.fixture_dir / "transcript.jsonl"
        for line in transcript_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            yield TranscriptEvent(kind=raw["kind"], payload=raw["payload"])

        diff_dir = self.fixture_dir / "workspace_diff"
        if diff_dir.exists():
            for src in diff_dir.rglob("*"):
                if src.is_dir():
                    continue
                relative = src.relative_to(diff_dir)
                dest = cwd / relative
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dest)
