"""Username rules and provisional username generation.

Rules (enforced here and mirrored by the web composer):
  - 3-30 characters
  - lowercase letters, digits and underscore only
  - must start with a letter
  - no consecutive underscores, no trailing underscore
  - not a reserved word
"""

import re

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_]{2,29}$")

# Paths the web app owns, plus words that would be confusing or impersonating.
RESERVED_USERNAMES = frozenset(
    {
        "about",
        "admin",
        "api",
        "auth",
        "help",
        "login",
        "logout",
        "me",
        "moderator",
        "new",
        "p",
        "posts",
        "recipes",
        "search",
        "settings",
        "signup",
        "smoodie",
        "staff",
        "support",
        "u",
        "user",
        "users",
    }
)

MIN_LENGTH = 3
MAX_LENGTH = 30


class InvalidUsername(ValueError):
    """Raised with a human-readable reason the username was rejected."""


def validate_username(candidate: str) -> str:
    """Return the normalized username, or raise InvalidUsername with a reason."""
    name = candidate.strip().lower()

    if len(name) < MIN_LENGTH:
        raise InvalidUsername(f"Usernames need at least {MIN_LENGTH} characters.")
    if len(name) > MAX_LENGTH:
        raise InvalidUsername(f"Usernames can be at most {MAX_LENGTH} characters.")
    if not name[0].isalpha():
        raise InvalidUsername("Usernames must start with a letter.")
    if not USERNAME_RE.match(name):
        raise InvalidUsername("Usernames can only use letters, numbers and underscores.")
    if "__" in name:
        raise InvalidUsername("Usernames can't contain two underscores in a row.")
    if name.endswith("_"):
        raise InvalidUsername("Usernames can't end with an underscore.")
    if name in RESERVED_USERNAMES:
        raise InvalidUsername("That username is reserved.")

    return name


def suggest_username(email: str | None, display_name: str | None, uid: str) -> str:
    """Build a valid provisional username for a brand-new account.

    Signup should never fail because someone's email happened to sanitize into
    something unusable, so this always returns something valid, falling back to
    the Firebase uid. Callers still resolve collisions against the database.
    """
    for source in (
        (email or "").split("@")[0],
        display_name or "",
        f"cook_{uid}",
    ):
        cleaned = re.sub(r"[^a-z0-9_]", "", source.lower().replace(" ", "_"))
        cleaned = re.sub(r"_+", "_", cleaned).strip("_")
        cleaned = re.sub(r"^[^a-z]+", "", cleaned)[:MAX_LENGTH].rstrip("_")
        if len(cleaned) >= MIN_LENGTH and cleaned not in RESERVED_USERNAMES:
            return cleaned

    # Last resort: uid is alphanumeric but may start with a digit.
    return f"cook_{re.sub(r'[^a-z0-9]', '', uid.lower())}"[:MAX_LENGTH].rstrip("_")


def with_suffix(base: str, suffix: int) -> str:
    """Append a collision-breaking suffix, trimming the base to stay in bounds."""
    tail = str(suffix)
    return f"{base[: MAX_LENGTH - len(tail)].rstrip('_')}{tail}"
