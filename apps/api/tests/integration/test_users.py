"""Profile read and update."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.models.event import EventOutbox
from tests.fakes import FakeVerifier


async def _sign_in(
    client: httpx.AsyncClient, verifier: FakeVerifier, token: str = "tok", **kwargs: object
) -> dict:
    verifier.register(token, **kwargs)  # type: ignore[arg-type]
    resp = await client.post("/v1/auth/session", json={"id_token": token})
    assert resp.status_code == 200
    return resp.json()["user"]


async def test_public_profile_is_readable_without_auth(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    anon = httpx.AsyncClient(transport=client._transport, base_url="http://test")

    resp = await anon.get("/v1/users/angel")

    assert resp.status_code == 200
    assert resp.json()["username"] == "angel"
    await anon.aclose()


async def test_profile_lookup_is_case_insensitive(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    assert (await client.get("/v1/users/ANGEL")).status_code == 200


async def test_unknown_profile_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/v1/users/nobody")).status_code == 404


async def test_update_profile_fields(client: httpx.AsyncClient, verifier: FakeVerifier) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    resp = await client.patch(
        "/v1/users/me",
        json={"display_name": "Angel N", "bio": "I cook things."},
    )

    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Angel N"
    assert resp.json()["bio"] == "I cook things."


async def test_partial_update_leaves_other_fields_alone(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    await client.patch("/v1/users/me", json={"bio": "original"})

    resp = await client.patch("/v1/users/me", json={"display_name": "Renamed"})

    assert resp.json()["bio"] == "original", "PATCH must not blank unsent fields"


async def test_username_change_takes_effect(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    resp = await client.patch("/v1/users/me", json={"username": "chef_angel"})

    assert resp.status_code == 200
    assert resp.json()["username"] == "chef_angel"
    assert (await client.get("/v1/users/chef_angel")).status_code == 200
    assert (await client.get("/v1/users/angel")).status_code == 404


async def test_username_is_normalized_to_lowercase(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    resp = await client.patch("/v1/users/me", json={"username": "ChefAngel"})
    assert resp.json()["username"] == "chefangel"


async def test_taken_username_is_rejected_with_conflict(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, token="a", uid="u1", email="angel@example.com")
    await _sign_in(client, verifier, token="b", uid="u2", email="taken@example.com")
    # currently signed in as the second account
    resp = await client.patch("/v1/users/me", json={"username": "angel"})
    assert resp.status_code == 409
    assert "taken" in resp.json()["detail"].lower()


async def test_invalid_username_is_rejected_with_a_reason(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    resp = await client.patch("/v1/users/me", json={"username": "no"})

    assert resp.status_code == 422
    detail = resp.json()["detail"][0]
    assert detail["loc"][-1] == "username", "error must be addressed to the field"
    assert "at least" in detail["msg"]


async def test_reserved_username_is_rejected(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    resp = await client.patch("/v1/users/me", json={"username": "settings"})
    assert resp.status_code == 422
    assert "reserved" in resp.json()["detail"][0]["msg"]


async def test_update_requires_auth(client: httpx.AsyncClient) -> None:
    assert (await client.patch("/v1/users/me", json={"bio": "x"})).status_code == 401


async def test_update_emits_profile_updated_with_field_names_only(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    await client.patch("/v1/users/me", json={"bio": "something personal"})

    event = (
        (await db.execute(select(EventOutbox).where(EventOutbox.event_type == "profile_updated")))
        .scalars()
        .one()
    )
    assert event.payload == {"fields": ["bio"]}
    assert "something personal" not in str(event.payload), (
        "profile contents are personal data and must not reach the warehouse"
    )


async def test_empty_patch_is_a_no_op(
    client: httpx.AsyncClient, verifier: FakeVerifier, db: AsyncSession
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    resp = await client.patch("/v1/users/me", json={})

    assert resp.status_code == 200
    events = (
        (await db.execute(select(EventOutbox).where(EventOutbox.event_type == "profile_updated")))
        .scalars()
        .all()
    )
    assert events == [], "a no-op update should not emit an event"
