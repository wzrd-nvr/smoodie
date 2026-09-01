import pytest

from smoodie_api.services.slugs import MAX_SLUG_LENGTH, slugify


@pytest.mark.parametrize(
    "title,expected",
    [
        ("Roast Chicken", "roast-chicken"),
        ("  Spaced   Out  ", "spaced-out"),
        ("Mac & Cheese", "mac-cheese"),
        ("30-Minute Pasta!", "30-minute-pasta"),
        ("Crème Brûlée", "creme-brulee"),
        ("Jalapeño Poppers", "jalapeno-poppers"),
        ("...leading and trailing...", "leading-and-trailing"),
        ("Multiple---Hyphens", "multiple-hyphens"),
    ],
)
def test_titles_become_readable_slugs(title: str, expected: str) -> None:
    assert slugify(title) == expected


def test_accents_are_folded_rather_than_dropped() -> None:
    """Dropping them would leave 'crm-brle', which is unreadable."""
    assert slugify("Crème") == "creme"


def test_a_long_title_is_trimmed_on_a_word_boundary() -> None:
    slug = slugify("A very long recipe title " * 10)
    assert len(slug) <= MAX_SLUG_LENGTH
    assert not slug.endswith("-")


def test_a_title_with_nothing_transliterable_returns_empty() -> None:
    """The caller falls back to the post id rather than inventing a slug."""
    assert slugify("日本語のみ") == ""
