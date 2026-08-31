"""Firebase token verification, behind a protocol.

The protocol exists so the routers can be exercised in tests with a fake
verifier instead of a live Firebase project or an emulator subprocess. The real
implementation is a thin adapter over firebase-admin and holds no logic of its
own, which is what makes that substitution safe.
"""

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials


class InvalidToken(Exception):
    """Raised when a Firebase ID token or session cookie fails verification."""


@dataclass(frozen=True)
class VerifiedIdentity:
    uid: str
    email: str | None
    email_verified: bool
    name: str | None


class TokenVerifier(Protocol):
    def verify_id_token(self, id_token: str) -> VerifiedIdentity: ...

    def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str: ...

    def verify_session_cookie(self, cookie: str) -> VerifiedIdentity: ...

    def revoke_refresh_tokens(self, uid: str) -> None: ...


def _identity_from_claims(claims: dict[str, Any]) -> VerifiedIdentity:
    return VerifiedIdentity(
        uid=claims["uid"] if "uid" in claims else claims["sub"],
        email=claims.get("email"),
        email_verified=bool(claims.get("email_verified", False)),
        name=claims.get("name"),
    )


class FirebaseTokenVerifier:
    """Real verifier. Uses Application Default Credentials on Cloud Run."""

    def __init__(self, project_id: str) -> None:
        if not firebase_admin._apps:  # noqa: SLF001 - documented module-level registry
            firebase_admin.initialize_app(
                credentials.ApplicationDefault(), {"projectId": project_id}
            )

    def verify_id_token(self, id_token: str) -> VerifiedIdentity:
        try:
            claims = firebase_auth.verify_id_token(id_token, check_revoked=True)
        except Exception as exc:  # firebase-admin raises a family of subclasses
            raise InvalidToken(str(exc)) from exc
        return _identity_from_claims(claims)

    def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str:
        try:
            cookie = firebase_auth.create_session_cookie(id_token, expires_in=expires_in)
        except Exception as exc:
            raise InvalidToken(str(exc)) from exc
        return str(cookie)

    def verify_session_cookie(self, cookie: str) -> VerifiedIdentity:
        # check_revoked is deliberately off here. This runs on every
        # authenticated request, and each revocation check is a network round
        # trip to Identity Toolkit — that cost belongs on the once-per-login
        # path, not on every page load. Sign-out clears the cookie, and the
        # cookie's own expiry bounds the window.
        try:
            claims = firebase_auth.verify_session_cookie(cookie, check_revoked=False)
        except Exception as exc:
            raise InvalidToken(str(exc)) from exc
        return _identity_from_claims(claims)

    def revoke_refresh_tokens(self, uid: str) -> None:
        firebase_auth.revoke_refresh_tokens(uid)
