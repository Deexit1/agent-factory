import pytest

from registration import validate_password, validate_username


def test_validate_username_accepts_valid_value():
    assert validate_username("alice") == "alice"


def test_validate_username_rejects_empty():
    with pytest.raises(ValueError):
        validate_username("")


def test_validate_username_rejects_too_long():
    with pytest.raises(ValueError):
        validate_username("a" * 21)


def test_validate_password_accepts_valid_value():
    assert validate_password("hunter2") == "hunter2"


def test_validate_password_rejects_empty():
    with pytest.raises(ValueError):
        validate_password("")


def test_validate_password_rejects_too_long():
    with pytest.raises(ValueError):
        validate_password("a" * 65)
