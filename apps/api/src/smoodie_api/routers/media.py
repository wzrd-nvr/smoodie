"""Direct-to-bucket image uploads.

The browser PUTs bytes straight to GCS with a short-lived signed URL, so images
never transit the API. The tradeoff is that we cannot trust what was uploaded
until we look: /complete verifies the object exists, is the type that was
requested, and is within the size limit, deleting it otherwise.
"""

import datetime as dt
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.dependencies import CurrentUser
from smoodie_api.config import get_settings
from smoodie_api.db import get_session
from smoodie_api.models.media import Media, MediaStatus
from smoodie_api.schemas.media import MediaOut, UploadRequest, UploadTicket
from smoodie_api.services.events import record_event
from smoodie_api.services.storage import (
    ALLOWED_IMAGE_TYPES,
    MAX_UPLOAD_BYTES,
    GcsObjectStore,
    ObjectStore,
    StorageError,
)

router = APIRouter(prefix="/v1/media", tags=["media"])
logger = logging.getLogger(__name__)

UPLOAD_URL_TTL = dt.timedelta(minutes=15)


def get_object_store(request: Request) -> ObjectStore:
    """Resolve the object store, allowing tests to inject a fake via app state."""
    override: ObjectStore | None = getattr(request.app.state, "object_store", None)
    if override is not None:
        return override
    return GcsObjectStore(get_settings().media_bucket)


def _object_name(owner_id: uuid.UUID, media_id: uuid.UUID, content_type: str) -> str:
    # The UUID is what makes the path unguessable, which is what lets the bucket
    # be publicly readable without exposing uploads that were never published.
    extension = ALLOWED_IMAGE_TYPES[content_type]
    return f"uploads/{owner_id}/{media_id}.{extension}"


@router.post("/uploads", response_model=UploadTicket, status_code=status.HTTP_201_CREATED)
async def create_upload(
    body: UploadRequest,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> UploadTicket:
    media = Media(
        owner_id=user.id,
        gcs_object="",  # set below, once the id exists
        content_type=body.content_type,
        status=MediaStatus.PENDING,
    )
    session.add(media)
    await session.flush()

    media.gcs_object = _object_name(user.id, media.id, body.content_type)

    try:
        url = store.signed_upload_url(media.gcs_object, body.content_type, UPLOAD_URL_TTL)
    except StorageError as exc:
        await session.rollback()
        logger.error("could not sign an upload url: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Uploads are unavailable right now. Try again in a moment.",
        ) from exc

    await session.commit()
    return UploadTicket(
        media_id=media.id,
        upload_url=url,
        content_type=body.content_type,
        max_bytes=MAX_UPLOAD_BYTES,
    )


@router.post("/{media_id}/complete", response_model=MediaOut)
async def complete_upload(
    media_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
    store: Annotated[ObjectStore, Depends(get_object_store)],
) -> MediaOut:
    media = (
        await session.execute(select(Media).where(Media.id == media_id, Media.owner_id == user.id))
    ).scalar_one_or_none()

    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such upload.")
    if media.status is MediaStatus.READY:
        return _as_out(media, store)  # idempotent: a retried call is not an error

    stored = store.stat(media.gcs_object)
    if stored is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That upload didn't finish. Try again.",
        )

    # The signed URL pins a content type, but the stored object is the only thing
    # that can be trusted about what actually landed.
    problem: str | None = None
    if stored.size > MAX_UPLOAD_BYTES:
        problem = f"Images need to be under {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."
    elif stored.content_type.split(";")[0].strip().lower() not in ALLOWED_IMAGE_TYPES:
        problem = "That file type isn't supported."

    if problem is not None:
        store.delete(media.gcs_object)
        media.status = MediaStatus.FAILED
        await session.commit()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=problem)

    media.status = MediaStatus.READY
    media.bytes = stored.size
    media.completed_at = dt.datetime.now(dt.UTC)

    await record_event(
        session,
        event_type="media_uploaded",
        actor_id=user.id,
        entity_type="media",
        entity_id=media.id,
        payload={"content_type": media.content_type, "bytes": stored.size},
    )
    await session.commit()
    await session.refresh(media)
    return _as_out(media, store)


def _as_out(media: Media, store: ObjectStore) -> MediaOut:
    return MediaOut(
        id=media.id,
        status=str(media.status),
        content_type=media.content_type,
        bytes=media.bytes,
        url=store.public_url(media.gcs_object) if media.status is MediaStatus.READY else None,
        created_at=media.created_at,
    )
