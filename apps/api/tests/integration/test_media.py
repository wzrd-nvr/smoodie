"""Direct-to-bucket upload flow."""

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.models.event import EventOutbox
from smoodie_api.models.media import Media, MediaStatus
from smoodie_api.services.storage import MAX_UPLOAD_BYTES
from tests.fakes import FakeObjectStore, FakeVerifier


async def _sign_in(client: httpx.AsyncClient, verifier: FakeVerifier, token: str = "tok", **kw):
    verifier.register(token, **kw)
    resp = await client.post("/v1/auth/session", json={"id_token": token})
    assert resp.status_code == 200
    return resp.json()["user"]


async def _ticket(client: httpx.AsyncClient, content_type: str = "image/jpeg") -> dict:
    resp = await client.post("/v1/media/uploads", json={"content_type": content_type})
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_upload_ticket_is_issued_for_a_supported_image(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    ticket = await _ticket(client)

    assert ticket["upload_url"].startswith("https://upload.example/")
    assert ticket["max_bytes"] == MAX_UPLOAD_BYTES
    assert len(store.signed) == 1
    signed_name, signed_type = store.signed[0]
    assert signed_type == "image/jpeg", "the signed URL must pin the content type"
    assert ticket["media_id"] in signed_name, "object path must carry the unguessable id"


async def test_uploads_require_auth(client: httpx.AsyncClient) -> None:
    resp = await client.post("/v1/media/uploads", json={"content_type": "image/png"})
    assert resp.status_code == 401


async def test_unsupported_types_are_rejected_with_guidance(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    resp = await client.post("/v1/media/uploads", json={"content_type": "image/svg+xml"})

    assert resp.status_code == 422
    assert "isn't supported" in resp.json()["detail"][0]["msg"]


async def test_oversized_declared_uploads_are_refused_before_transfer(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")

    resp = await client.post(
        "/v1/media/uploads",
        json={"content_type": "image/jpeg", "size_bytes": MAX_UPLOAD_BYTES + 1},
    )

    assert resp.status_code == 422
    assert store.signed == [], "no URL should be issued for a doomed upload"


async def test_completing_marks_ready_and_emits_the_event(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, db: AsyncSession
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    ticket = await _ticket(client)
    store.put(store.signed[0][0], size=2048, content_type="image/jpeg")

    resp = await client.post(f"/v1/media/{ticket['media_id']}/complete")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["bytes"] == 2048
    assert body["url"], "a ready image must expose a URL"

    event = (
        (await db.execute(select(EventOutbox).where(EventOutbox.event_type == "media_uploaded")))
        .scalars()
        .one()
    )
    assert event.payload["bytes"] == 2048


async def test_completing_without_the_object_is_a_conflict(
    client: httpx.AsyncClient, verifier: FakeVerifier
) -> None:
    """The browser abandoned the PUT — the row must not become usable."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    ticket = await _ticket(client)

    resp = await client.post(f"/v1/media/{ticket['media_id']}/complete")

    assert resp.status_code == 409
    assert "didn't finish" in resp.json()["detail"]


async def test_an_oversized_object_is_deleted_not_accepted(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, db: AsyncSession
) -> None:
    """A signed PUT cannot enforce a size limit, so completion has to."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    ticket = await _ticket(client)
    name = store.signed[0][0]
    store.put(name, size=MAX_UPLOAD_BYTES + 1, content_type="image/jpeg")

    resp = await client.post(f"/v1/media/{ticket['media_id']}/complete")

    assert resp.status_code == 422
    assert name in store.deleted, "an oversized object must not be left in the bucket"
    media = (await db.execute(select(Media))).scalar_one()
    assert media.status is MediaStatus.FAILED


async def test_a_mismatched_content_type_is_deleted(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    """Someone PUT something other than what the URL was signed for."""
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    ticket = await _ticket(client)
    name = store.signed[0][0]
    store.put(name, size=1024, content_type="application/zip")

    resp = await client.post(f"/v1/media/{ticket['media_id']}/complete")

    assert resp.status_code == 422
    assert name in store.deleted


async def test_completing_twice_is_idempotent(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    ticket = await _ticket(client)
    store.put(store.signed[0][0], size=512, content_type="image/jpeg")

    first = await client.post(f"/v1/media/{ticket['media_id']}/complete")
    second = await client.post(f"/v1/media/{ticket['media_id']}/complete")

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "ready"


async def test_cannot_complete_someone_elses_upload(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore
) -> None:
    await _sign_in(client, verifier, token="a", uid="u1", email="angel@example.com")
    ticket = await _ticket(client)
    store.put(store.signed[0][0], size=512, content_type="image/jpeg")

    await _sign_in(client, verifier, token="b", uid="u2", email="other@example.com")
    resp = await client.post(f"/v1/media/{ticket['media_id']}/complete")

    assert resp.status_code == 404, "another user's upload must not even be visible"


async def test_signing_failure_surfaces_as_unavailable_and_leaves_no_row(
    client: httpx.AsyncClient, verifier: FakeVerifier, store: FakeObjectStore, db: AsyncSession
) -> None:
    await _sign_in(client, verifier, uid="u1", email="angel@example.com")
    store.fail_signing = True

    resp = await client.post("/v1/media/uploads", json={"content_type": "image/jpeg"})

    assert resp.status_code == 503
    assert (await db.execute(select(Media))).scalars().all() == [], (
        "a media row without a usable upload URL is orphaned state"
    )
