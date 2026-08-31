"""Attaching an uploaded image to a profile."""

import uuid

import httpx

from tests.fakes import FakeObjectStore, FakeVerifier


async def _sign_in(client: httpx.AsyncClient, verifier: FakeVerifier, token: str = "tok", **kw):
    verifier.register(token, **kw)
    assert (await client.post("/v1/auth/session", json={"id_token": token})).status_code == 200


async def _ready_media(client: httpx.AsyncClient, store: FakeObjectStore) -> str:
    ticket = (await client.post("/v1/media/uploads", json={"content_type": "image/jpeg"})).json()
    store.put(store.signed[-1][0], size=1024, content_type="image/jpeg")
    assert (await client.post(f"/v1/media/{ticket['media_id']}/complete")).status_code == 200
    return ticket["media_id"]


async def test_own_ready_image_can_become_an_avatar(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    media_id = await _ready_media(client, store)

    resp = await client.patch("/v1/users/me", json={"avatar_media_id": media_id})

    assert resp.status_code == 200
    assert resp.json()["avatar_media_id"] == media_id


async def test_a_pending_image_cannot_become_an_avatar(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    """The bytes never landed, so there is nothing to show."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    ticket = (await client.post("/v1/media/uploads", json={"content_type": "image/jpeg"})).json()

    resp = await client.patch("/v1/users/me", json={"avatar_media_id": ticket["media_id"]})

    assert resp.status_code == 422


async def test_another_users_image_cannot_become_an_avatar(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, token="a", uid="u1", email="angel@example.com")
    stolen = await _ready_media(client, store)

    await _sign_in(client, verifier, token="b", uid="u2", email="other@example.com")
    resp = await client.patch("/v1/users/me", json={"avatar_media_id": stolen})

    assert resp.status_code == 422


async def test_an_unknown_media_id_is_rejected(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    resp = await client.patch("/v1/users/me", json={"avatar_media_id": str(uuid.uuid4())})
    assert resp.status_code == 422
