import pytest

from orchestrator.evals.judge import extract_json_object


def test_extract_json_object_parses_raw_json() -> None:
    result = extract_json_object('{"score": 80, "rationale": "close enough"}')
    assert result == {"score": 80, "rationale": "close enough"}


def test_extract_json_object_strips_a_code_fence() -> None:
    text = '```json\n{"score": 42, "rationale": "fenced"}\n```'
    result = extract_json_object(text)
    assert result == {"score": 42, "rationale": "fenced"}


def test_extract_json_object_strips_an_unlabeled_fence() -> None:
    text = '```\n{"score": 10, "rationale": "no language tag"}\n```'
    result = extract_json_object(text)
    assert result == {"score": 10, "rationale": "no language tag"}


def test_extract_json_object_rejects_a_non_object() -> None:
    with pytest.raises(ValueError, match="expected a JSON object"):
        extract_json_object("[1, 2, 3]")
