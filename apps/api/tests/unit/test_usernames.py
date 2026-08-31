import pytest

from smoodie_api.services.usernames import (
    MAX_LENGTH,
    InvalidUsername,
    suggest_username,
    validate_username,
    with_suffix,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("cook", "cook"),
        ("Cook", "cook"),  # normalized
        ("  spacedout  ", "spacedout"),  # trimmed
        ("a_b_c", "a_b_c"),
        ("chef99", "chef99"),
        ("abc", "abc"),  # minimum length
        ("a" * MAX_LENGTH, "a" * MAX_LENGTH),  # maximum length
    ],
)
def test_accepts_valid_usernames(value: str, expected: str) -> None:
    assert validate_username(value) == expected


@pytest.mark.parametrize(
    "value,reason",
    [
        ("ab", "at least"),
        ("a" * (MAX_LENGTH + 1), "at most"),
        ("9lives", "start with a letter"),
        ("_leading", "start with a letter"),
        ("has space", "letters, numbers"),
        ("has-dash", "letters, numbers"),
        ("emoji🍳x", "letters, numbers"),
        ("double__under", "two underscores"),
        ("trailing_", "end with an underscore"),
        ("admin", "reserved"),
        ("settings", "reserved"),
        ("SETTINGS", "reserved"),  # reserved check happens after normalization
    ],
)
def test_rejects_invalid_usernames(value: str, reason: str) -> None:
    with pytest.raises(InvalidUsername) as exc:
        validate_username(value)
    assert reason in str(exc.value)


@pytest.mark.parametrize(
    "email,display_name,uid",
    [
        ("angel@example.com", None, "abc123"),
        ("A.Nivar+tag@example.com", None, "abc123"),
        (None, "Angel Nivar", "abc123"),
        (None, None, "abc123"),
        ("99@example.com", None, "abc123"),  # digits-first local part
        ("__@example.com", None, "abc123"),  # sanitizes to nothing
        ("admin@example.com", None, "abc123"),  # reserved local part
        ("a@example.com", None, "abc123"),  # too short
        ("averyveryverylongemailaddresslocalpart@example.com", None, "abc123"),
    ],
)
def test_suggested_usernames_are_always_valid(
    email: str | None, display_name: str | None, uid: str
) -> None:
    """Signup must never fail because an email sanitized badly."""
    assert validate_username(suggest_username(email, display_name, uid))


def test_suggestion_prefers_email_local_part() -> None:
    assert suggest_username("angel@example.com", "Angel Nivar", "uid") == "angel"


def test_suggestion_falls_back_to_display_name() -> None:
    assert suggest_username("99@example.com", "Angel Nivar", "uid") == "angel_nivar"


@pytest.mark.parametrize("suffix", [2, 10, 12345])
def test_suffixed_usernames_stay_valid_and_bounded(suffix: int) -> None:
    result = with_suffix("a" * MAX_LENGTH, suffix)
    assert len(result) <= MAX_LENGTH
    assert validate_username(result) == result
    assert result.endswith(str(suffix))
