from schemas.redaction import scrub, scrub_payload

_FAKE_ANTHROPIC_KEY = "sk-ant-api03-FAKE00000000000000000000000000000000000000000000"
_FAKE_OPENAI_KEY = "sk-FAKE000000000000000000000000000000"


def test_scrub_redacts_an_anthropic_shaped_key() -> None:
    text = f"here is my key: {_FAKE_ANTHROPIC_KEY} please use it"
    scrubbed = scrub(text)

    assert _FAKE_ANTHROPIC_KEY not in scrubbed
    assert "[REDACTED-KEY]" in scrubbed


def test_scrub_redacts_an_openai_shaped_key() -> None:
    text = f"OPENAI_API_KEY={_FAKE_OPENAI_KEY}"
    scrubbed = scrub(text)

    assert _FAKE_OPENAI_KEY not in scrubbed
    assert "[REDACTED-KEY]" in scrubbed


def test_scrub_leaves_unrelated_text_untouched() -> None:
    text = "the ticket transitioned to in_review with no issues"
    assert scrub(text) == text


def test_scrub_payload_redacts_nested_dict_and_list_values() -> None:
    payload = {
        "message": f"leaked key: {_FAKE_ANTHROPIC_KEY}",
        "nested": {"inner": _FAKE_OPENAI_KEY},
        "items": [f"key={_FAKE_ANTHROPIC_KEY}", "clean value"],
        "count": 3,
    }

    scrubbed = scrub_payload(payload)

    assert _FAKE_ANTHROPIC_KEY not in str(scrubbed)
    assert _FAKE_OPENAI_KEY not in str(scrubbed)
    assert scrubbed["count"] == 3
    assert scrubbed["items"][1] == "clean value"
