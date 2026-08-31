"""Test doubles."""

from datetime import UTC, datetime, timedelta

from smoodie_api.auth.verifier import InvalidToken, VerifiedIdentity


class FakeVerifier:
    """Stands in for Firebase.

    Tokens are plain strings mapped to identities, so tests can express "a valid
    token for this user" or "a token Firebase rejects" without a live project or
    an emulator subprocess. The real verifier is a thin adapter with no logic of
    its own, which is what makes swapping it out here safe.
    """

    def __init__(self) -> None:
        self.identities: dict[str, VerifiedIdentity] = {}
        self.revoked: list[str] = []
        self.session_cookies: dict[str, str] = {}

    def register(
        self,
        token: str,
        *,
        uid: str | None = None,
        email: str | None = None,
        name: str | None = None,
        email_verified: bool = True,
        auth_time: datetime | None = None,
    ) -> VerifiedIdentity:
        identity = VerifiedIdentity(
            uid=uid or f"uid-{token}",
            email=email,
            email_verified=email_verified,
            name=name,
            auth_time=auth_time or datetime.now(UTC),
        )
        self.identities[token] = identity
        return identity

    def verify_id_token(self, id_token: str) -> VerifiedIdentity:
        if id_token not in self.identities:
            raise InvalidToken("unknown token")
        return self.identities[id_token]

    def create_session_cookie(self, id_token: str, expires_in: timedelta) -> str:
        if id_token not in self.identities:
            raise InvalidToken("unknown token")
        cookie = f"session-for-{id_token}"
        self.session_cookies[cookie] = id_token
        return cookie

    def verify_session_cookie(self, cookie: str) -> VerifiedIdentity:
        token = self.session_cookies.get(cookie)
        if token is None:
            raise InvalidToken("unknown session cookie")
        return self.identities[token]

    def revoke_refresh_tokens(self, uid: str) -> None:
        self.revoked.append(uid)
