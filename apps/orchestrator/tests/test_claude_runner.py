from pathlib import Path

from orchestrator.claude_runner import (
    SubprocessClaudeCodeRunner,
    _is_transient_api_error,
    _parse_stream_json_line,
)

# Captured verbatim from a real `claude -p ... --output-format stream-json --verbose` run
# (T-009 pilot validation) - `_parse_stream_json_line` was never exercised against real
# output before that run surfaced two bugs: --verbose is required or the CLI errors before
# emitting anything, and tool calls arrive nested inside assistant/user turns rather than
# as their own top-level "tool_use"/"tool_result" event types.
REAL_ASSISTANT_TOOL_USE = (
    '{"type":"assistant","message":{"model":"claude-sonnet-5","content":'
    '[{"type":"tool_use","id":"toolu_1","name":"Write",'
    '"input":{"file_path":"hello.txt","content":"hello"}}]},'
    '"session_id":"abc"}'
)
REAL_ASSISTANT_TEXT = (
    '{"type":"assistant","message":{"model":"claude-sonnet-5",'
    '"content":[{"type":"text","text":"Created hello.txt."}]},"session_id":"abc"}'
)
REAL_USER_TOOL_RESULT = (
    '{"type":"user","message":{"role":"user","content":'
    '[{"tool_use_id":"toolu_1","type":"tool_result","content":"File created"}]},'
    '"session_id":"abc"}'
)
REAL_RESULT = (
    '{"type":"result","subtype":"success","is_error":false,'
    '"total_cost_usd":0.128,"usage":{"input_tokens":4,"output_tokens":115}}'
)


def test_assistant_message_with_tool_use_is_classified_as_tool_call() -> None:
    event = _parse_stream_json_line(REAL_ASSISTANT_TOOL_USE)
    assert event is not None
    assert event.kind == "tool_call"


def test_assistant_message_with_only_text_is_classified_as_message() -> None:
    event = _parse_stream_json_line(REAL_ASSISTANT_TEXT)
    assert event is not None
    assert event.kind == "message"


def test_user_turn_with_tool_result_is_classified_as_tool_call() -> None:
    event = _parse_stream_json_line(REAL_USER_TOOL_RESULT)
    assert event is not None
    assert event.kind == "tool_call"


def test_result_event_extracts_cost_and_tokens() -> None:
    event = _parse_stream_json_line(REAL_RESULT)
    assert event is not None
    assert event.kind == "cost"
    assert event.payload["total_cost_usd"] == 0.128
    assert event.payload["tokens_in"] == 4
    assert event.payload["tokens_out"] == 115


def test_unparseable_line_returns_none() -> None:
    assert _parse_stream_json_line("not json") is None


def test_system_init_event_returns_none() -> None:
    assert _parse_stream_json_line('{"type":"system","subtype":"init"}') is None


# Captured verbatim from a real run (T-009 pilot validation) - the API intermittently
# 400s on the very first turn with this exact shape, reproducibly transient (identical
# prompt succeeded on retry), which is what SubprocessClaudeCodeRunner's retry loop keys on.
REAL_TRANSIENT_API_ERROR = {
    "error": "unknown",
    "message": {
        "content": [
            {
                "type": "text",
                "text": (
                    'API Error: 400 {"type":"error","error":{"type":"invalid_request_error",'
                    '"message":"\\"thinking.type.enabled\\" is not supported for this model."}}'
                ),
            }
        ]
    },
}


def test_is_transient_api_error_matches_the_observed_shape() -> None:
    assert _is_transient_api_error(REAL_TRANSIENT_API_ERROR) is True


def test_is_transient_api_error_false_for_normal_text_message() -> None:
    event = _parse_stream_json_line(REAL_ASSISTANT_TEXT)
    assert event is not None
    assert _is_transient_api_error(event.payload) is False


def test_is_transient_api_error_false_for_tool_use() -> None:
    event = _parse_stream_json_line(REAL_ASSISTANT_TOOL_USE)
    assert event is not None
    assert _is_transient_api_error(event.payload) is False


class _FakePopen:
    """Records the argv it was constructed with; yields no stdout lines."""

    def __init__(self, argv: list[str], **_kwargs: object) -> None:
        _FakePopen.last_argv = argv
        self.stdout = iter(())
        self.stderr = None

    def poll(self) -> int:
        return 0

    def terminate(self) -> None:
        pass


def test_run_appends_the_current_dev_agent_prompt_to_the_cli_invocation(
    tmp_path: Path, monkeypatch
) -> None:
    # T-101: prompts/dev-agent.md must actually reach the CLI, or a golden-set eval
    # degrading it could never change a real run's behaviour.
    prompt_path = tmp_path / "dev-agent.md"
    prompt_path.write_text("# System prompt · Dev Agent · v0.2\n\nBe careful.", encoding="utf-8")

    monkeypatch.setattr("orchestrator.claude_runner.shutil.which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr("orchestrator.claude_runner.subprocess.Popen", _FakePopen)

    runner = SubprocessClaudeCodeRunner(system_prompt_path=prompt_path)
    list(
        runner.run(
            prompt="do the task",
            cwd=tmp_path,
            model="claude-sonnet-5",
            budget_usd=1.0,
            timeout_s=60.0,
        )
    )

    argv = _FakePopen.last_argv
    assert "--append-system-prompt" in argv
    assert argv[argv.index("--append-system-prompt") + 1] == prompt_path.read_text(
        encoding="utf-8"
    )
