from orchestrator.claude_runner import _parse_stream_json_line

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
