import pytest

import llm_router


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


class _FakeClient:
    def __init__(self) -> None:
        self.messages = _FakeMessages()


def test_route_calls_the_model_configured_for_the_role(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_router.anthropic, "Anthropic", lambda: fake_client)

    result = llm_router.route(
        "eval-judge",
        system="be a judge",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert result.text == "ok"
    assert result.model == "claude-haiku-4-5-20251001"
    assert fake_client.messages.calls[0]["model"] == "claude-haiku-4-5-20251001"
    assert fake_client.messages.calls[0]["temperature"] == 0


def test_route_reports_tokens_and_cost(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_router.anthropic, "Anthropic", lambda: fake_client)

    result = llm_router.route(
        "planner",
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
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_router.anthropic, "Anthropic", lambda: fake_client)

    llm_router.route(
        "planner", system="plan", messages=[{"role": "user", "content": "hi"}], max_tokens=100
    )

    assert "temperature" not in fake_client.messages.calls[0]


def test_route_reports_sonnet_pricing_for_delivery_manager(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_client = _FakeClient()
    monkeypatch.setattr(llm_router.anthropic, "Anthropic", lambda: fake_client)

    result = llm_router.route(
        "delivery-manager",
        system="assign",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=100,
    )

    assert result.model == "claude-sonnet-5"
    # sonnet pricing: (3.0, 15.0) per million tokens
    assert result.cost_usd == pytest.approx((100 * 3.0 + 50 * 15.0) / 1_000_000)
    assert fake_client.messages.calls[0]["temperature"] == 0


def test_route_rejects_an_unknown_role() -> None:
    with pytest.raises(llm_router.UnknownRole):
        llm_router.route("not-a-real-role", system="x", messages=[], max_tokens=10)
