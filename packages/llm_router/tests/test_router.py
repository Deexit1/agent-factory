import pytest

import llm_router


class _FakeBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = [_FakeBlock(text)]


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

    assert result == "ok"
    assert fake_client.messages.calls[0]["model"] == "claude-haiku-4-5-20251001"
    assert fake_client.messages.calls[0]["temperature"] == 0


def test_route_rejects_an_unknown_role() -> None:
    with pytest.raises(llm_router.UnknownRole):
        llm_router.route("not-a-real-role", system="x", messages=[], max_tokens=10)
