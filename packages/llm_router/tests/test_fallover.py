"""T-202 (SPEC-202 AC4): real router fallover control flow, fault-injected at the HTTP
boundary via respx — zero live provider spend. Both SDKs are httpx-based under the
hood, so stubbing their actual endpoints proves route()'s retry/fallover logic for
real, not just a mocked-away happy path.
"""

import httpx
import pytest
import respx

import llm_router
from llm_router import ProviderCredential

_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

_OPENAI_SUCCESS_BODY = {
    "id": "chatcmpl-fake",
    "object": "chat.completion",
    "created": 0,
    "model": "gpt-4.1",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "fallover worked"},
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 42, "completion_tokens": 7, "total_tokens": 49},
}


@respx.mock
def test_fallover_moves_to_the_next_provider_on_a_primary_outage() -> None:
    respx.post(_ANTHROPIC_URL).mock(
        return_value=httpx.Response(529, json={"type": "error", "error": {"message": "overloaded"}})
    )
    respx.post(_OPENAI_URL).mock(return_value=httpx.Response(200, json=_OPENAI_SUCCESS_BODY))

    result = llm_router.route(
        "planner",
        credentials=[
            ProviderCredential(provider="anthropic", api_key="sk-ant-fake-primary"),
            ProviderCredential(provider="openai", api_key="sk-fake-fallback-key-000000"),
        ],
        system="plan",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
        max_retries_per_provider=0,
    )

    assert result.provider == "openai"
    assert result.text == "fallover worked"
    assert result.tokens_in == 42
    assert result.tokens_out == 7
    assert len(result.attempts) == 2
    assert result.attempts[0].provider == "anthropic"
    assert result.attempts[0].error is not None
    assert result.attempts[1].provider == "openai"
    assert result.attempts[1].error is None


@respx.mock
def test_all_providers_failing_raises_with_the_full_attempt_trail() -> None:
    respx.post(_ANTHROPIC_URL).mock(return_value=httpx.Response(529, json={"error": "down"}))
    respx.post(_OPENAI_URL).mock(return_value=httpx.Response(503, json={"error": "down"}))

    with pytest.raises(llm_router.AllProvidersFailed) as exc_info:
        llm_router.route(
            "review",
            credentials=[
                ProviderCredential(provider="anthropic", api_key="sk-ant-fake"),
                ProviderCredential(provider="openai", api_key="sk-fake-000000000000000000"),
            ],
            system="review",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100,
            max_retries_per_provider=0,
        )

    assert len(exc_info.value.attempts) == 2


@respx.mock
def test_transient_error_is_retried_before_falling_over() -> None:
    route = respx.post(_ANTHROPIC_URL)
    route.side_effect = [
        httpx.Response(529, json={"error": "overloaded"}),
        httpx.Response(
            200,
            json={
                "id": "msg-fake",
                "type": "message",
                "role": "assistant",
                "model": "claude-opus-4-8",
                "content": [{"type": "text", "text": "recovered on retry"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        ),
    ]

    result = llm_router.route(
        "planner",
        credentials=[ProviderCredential(provider="anthropic", api_key="sk-ant-fake")],
        system="plan",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
        max_retries_per_provider=1,
    )

    assert result.text == "recovered on retry"
    assert result.provider == "anthropic"
    assert len(result.attempts) == 1
    assert result.attempts[0].error is None
