"""Session exchange and the auth dependency, end to end against Postgres."""

from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.dependencies import SESSION_COOKIE_NAME
from smoodie_api.models.event import EventOutbox
from smoodie_api.models.user import User
from tests.fakes import FakeVerifier


async def test_valid_token_creates_session_and_user(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    verifier.register("tok", uid="firebase-1", email="angel@example.com", name="Angel")

    resp = await client.post("/v1/auth/session", json={"id_token": "tok"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] is True
    assert body["user"]["username"] == "angel"
    assert body["user"]["display_name"] == "Angel"

    cookie = resp.cookies.get(SESSION_COOKIE_NAME)
    assert cookie, "session cookie must be set"
    set_cookie = resp.headers["set-cookie"]
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie

    users = (await db.execute(select(User))).scalars().all()
    assert len(users) == 1
    assert users[0].firebase_uid == "firebase-1"


async def test_signup_emits_user_signed_up_event_once(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    verifier.register("tok", uid="firebase-1", email="angel@example.com")

    await client.post("/v1/auth/session", json={"id_token": "tok"})
    await client.post("/v1/auth/session", json={"id_token": "tok"})  # sign in again

    events = (
        (await db.execute(select(EventOutbox).where(EventOutbox.event_type == "user_signed_up")))
        .scalars()
        .all()
    )
    assert len(events) == 1, "the event marks account creation, not every sign-in"
    assert events[0].payload["username"] == "angel"
    assert events[0].published_at is None, "publisher has not run yet"


async def test_second_sign_in_reuses_the_account(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    verifier.register("tok", uid="firebase-1", email="angel@example.com")

    first = await client.post("/v1/auth/session", json={"id_token": "tok"})
    second = await client.post("/v1/auth/session", json={"id_token": "tok"})

    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert first.json()["user"]["id"] == second.json()["user"]["id"]
    assert len((await db.execute(select(User))).scalars().all()) == 1


async def test_colliding_usernames_get_distinct_suffixes(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    """Two people whose emails sanitize identically must both be able to sign up."""
    verifier.register("tok1", uid="uid-1", email="angel@example.com")
    verifier.register("tok2", uid="uid-2", email="angel@other.com")
    verifier.register("tok3", uid="uid-3", email="angel@third.com")

    names = []
    for token in ("tok1", "tok2", "tok3"):
        resp = await client.post("/v1/auth/session", json={"id_token": token})
        assert resp.status_code == 200
        names.append(resp.json()["user"]["username"])

    assert names[0] == "angel"
    assert len(set(names)) == 3, f"usernames must be unique, got {names}"


@pytest.mark.parametrize("token", ["not-a-real-token", ""])
async def test_invalid_token_is_rejected(client: httpx.AsyncClient, token: str) -> None:
    resp = await client.post("/v1/auth/session", json={"id_token": token})
    assert resp.status_code in (401, 422)
    assert SESSION_COOKIE_NAME not in resp.cookies


async def test_protected_route_requires_a_session(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/users/me")
    assert resp.status_code == 401


async def test_protected_route_rejects_a_bogus_cookie(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/users/me", cookies={SESSION_COOKIE_NAME: "forged"})
    assert resp.status_code == 401


async def test_session_cookie_grants_access(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    verifier.register("tok", uid="firebase-1", email="angel@example.com")
    await client.post("/v1/auth/session", json={"id_token": "tok"})

    resp = await client.get("/v1/users/me")

    assert resp.status_code == 200
    assert resp.json()["username"] == "angel"


async def test_logout_clears_the_session(client: httpx.AsyncClient, verifier: FakeVerifier) -> None:
    verifier.register("tok", uid="firebase-1", email="angel@example.com")
    await client.post("/v1/auth/session", json={"id_token": "tok"})

    resp = await client.delete("/v1/auth/session")
    assert resp.status_code == 204

    assert (await client.get("/v1/users/me")).status_code == 401


async def test_logout_without_a_session_still_succeeds(client: httpx.AsyncClient) -> None:
    """Signing out should never strand someone whose cookie already expired."""
    assert (await client.delete("/v1/auth/session")).status_code == 204


async def test_deleted_account_cannot_use_its_session(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    verifier.register("tok", uid="firebase-1", email="angel@example.com")
    await client.post("/v1/auth/session", json={"id_token": "tok"})

    user = (await db.execute(select(User))).scalar_one()
    from datetime import UTC, datetime

    user.deleted_at = datetime.now(UTC)
    await db.commit()

    assert (await client.get("/v1/users/me")).status_code == 401


async def test_sessions_issued_before_revocation_are_refused(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    """Firebase's own revocation check is skipped on the hot path, so this is
    the mechanism that has to hold: invalidating sessions must take effect on
    the very next request, not whenever the cookie happens to expire."""
    from datetime import UTC, datetime, timedelta

    signed_in_at = datetime.now(UTC) - timedelta(hours=1)
    verifier.register("tok", uid="firebase-1", email="angel@example.com", auth_time=signed_in_at)
    await client.post("/v1/auth/session", json={"id_token": "tok"})
    assert (await client.get("/v1/users/me")).status_code == 200

    user = (await db.execute(select(User))).scalar_one()
    user.sessions_valid_after = datetime.now(UTC)
    await db.commit()

    assert (await client.get("/v1/users/me")).status_code == 401


async def test_sessions_issued_after_revocation_still_work(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    from datetime import UTC, datetime, timedelta

    verifier.register("tok", uid="firebase-1", email="angel@example.com")
    await client.post("/v1/auth/session", json={"id_token": "tok"})

    user = (await db.execute(select(User))).scalar_one()
    user.sessions_valid_after = datetime.now(UTC) - timedelta(hours=1)
    await db.commit()

    assert (await client.get("/v1/users/me")).status_code == 200


async def test_a_session_without_auth_time_is_treated_as_revoked(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    """Fail closed: a session we cannot date cannot be proven current."""
    from datetime import UTC, datetime

    verifier.register("tok", uid="firebase-1", email="angel@example.com")
    await client.post("/v1/auth/session", json={"id_token": "tok"})

    verifier.identities["tok"] = replace(verifier.identities["tok"], auth_time=None)
    user = (await db.execute(select(User))).scalar_one()
    user.sessions_valid_after = datetime.now(UTC)
    await db.commit()

    assert (await client.get("/v1/users/me")).status_code == 401
