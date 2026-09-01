"""URL slugs for posts."""

import re
import unicodedata

MAX_SLUG_LENGTH = 80


def slugify(title: str) -> str:
    """Build a URL-safe slug from a title.

    Accents are folded rather than dropped, so "Crème Brûlée" becomes
    "creme-brulee" instead of losing half its letters. A title with nothing
    transliterable left — one written entirely in a non-Latin script, say —
    returns empty, and the caller falls back to the post id.
    """
    folded = unicodedata.normalize("NFKD", title)
    ascii_only = folded.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_only.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    if len(hyphenated) <= MAX_SLUG_LENGTH:
        return hyphenated
    # Trim on a word boundary so the slug does not end mid-word.
    clipped = hyphenated[:MAX_SLUG_LENGTH]
    return clipped.rsplit("-", 1)[0] if "-" in clipped else clipped
