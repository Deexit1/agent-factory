import pytest

import llm_router
from llm_router import ProviderCredential


class _FakeUsage:
    def __init__(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str, input_tokens: int = 100, output_tokens: int = 50) -> None:
        self.content = [_FakeBlock(text)]
        self.usage = _FakeUsage(input_tokens, output_tokens)


class _FakeMessages:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse("ok")


class _FakeAnthropicClient:
    def __init__(self, **kwargs: object) -> None:
        self.init_kwargs = kwargs
        self.messages = _FakeMessages()


_ANTHROPIC_CRED = ProviderCredential(provider="anthropic", api_key="sk-ant-fake-test-key")


def _patch_anthropic(monkeypatch: pytest.MonkeyPatch) -> _FakeAnthropicClient:
    fake_client = _FakeAnthropicClient()
    monkeypatch.setattr(llm_router.anthropic, "Anthropic", lambda **kwargs: fake_client)
    return fake_client


def test_route_calls_the_model_configured_for_the_role(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _patch_anthropic(monkeypatch)

    result = llm_router.route(
        "eval-judge",
        credentials=[_ANTHROPIC_CRED],
        system="be a judge",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert result.text == "ok"
    assert result.provider == "anthropic"
    assert result.model == "claude-haiku-4-5-20251001"
    assert fake_client.messages.calls[0]["model"] == "claude-haiku-4-5-20251001"
    assert fake_client.messages.calls[0]["temperature"] == 0
    assert result.attempts == [
        llm_router.RouteAttempt(provider="anthropic", model="claude-haiku-4-5-20251001", error=None)
    ]


def test_route_reports_tokens_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anthropic(monkeypatch)

    result = llm_router.route(
        "planner",
        credentials=[_ANTHROPIC_CRED],
        system="plan",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert result.model == "claude-opus-4-8"
    assert result.tokens_in == 100
    assert result.tokens_out == 50
    # opus pricing: (15.0, 75.0) per million tokens
    assert result.cost_usd == pytest.approx((100 * 15.0 + 50 * 75.0) / 1_000_000)


def test_route_omits_temperature_for_models_that_reject_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _patch_anthropic(monkeypatch)

    llm_router.route(
        "planner",
        credentials=[_ANTHROPIC_CRED],
        system="plan",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert "temperature" not in fake_client.messages.calls[0]


def test_route_reports_sonnet_pricing_for_delivery_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_anthropic(monkeypatch)

    result = llm_router.route(
        "delivery-manager",
        credentials=[_ANTHROPIC_CRED],
        system="assign",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert result.model == "claude-sonnet-5"
    # sonnet pricing: (3.0, 15.0) per million tokens
    assert result.cost_usd == pytest.approx((100 * 3.0 + 50 * 15.0) / 1_000_000)


def test_route_reports_sonnet_pricing_for_review(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anthropic(monkeypatch)

    result = llm_router.route(
        "review",
        credentials=[_ANTHROPIC_CRED],
        system="review",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert result.model == "claude-sonnet-5"
    assert result.cost_usd == pytest.approx((100 * 3.0 + 50 * 15.0) / 1_000_000)


def test_route_rejects_an_unknown_role(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_anthropic(monkeypatch)

    with pytest.raises(llm_router.UnknownRole):
        llm_router.route(
            "not-a-real-role", credentials=[_ANTHROPIC_CRED], system="x", messages=[], max_tokens=10
        )


def test_route_rejects_an_unknown_provider() -> None:
    with pytest.raises(llm_router.UnknownProvider):
        llm_router.route(
            "planner",
            credentials=[ProviderCredential(provider="not-a-real-provider", api_key="x")],
            system="x",
            messages=[],
            max_tokens=10,
        )


def test_route_rejects_no_credentials() -> None:
    with pytest.raises(llm_router.NoCredentialsProvided):
        llm_router.route("planner", credentials=[], system="x", messages=[], max_tokens=10)


def test_route_passes_the_credentials_api_key_to_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_anthropic(**kwargs: object) -> _FakeAnthropicClient:
        captured.update(kwargs)
        return _FakeAnthropicClient()

    monkeypatch.setattr(llm_router.anthropic, "Anthropic", fake_anthropic)

    llm_router.route(
        "planner",
        credentials=[ProviderCredential(provider="anthropic", api_key="sk-ant-org-specific-key")],
        system="plan",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert captured["api_key"] == "sk-ant-org-specific-key"
