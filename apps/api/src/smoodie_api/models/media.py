import enum
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from smoodie_api.db import Base, pg_enum


class MediaStatus(enum.StrEnum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"


class Media(Base):
    """An uploaded image.

    A row is created when an upload URL is issued and only becomes usable once
    the object is confirmed present in the bucket, so a row that was abandoned
    mid-upload can never be attached to a profile or a post.
    """

    __tablename__ = "media"
    __table_args__ = (
        CheckConstraint("bytes IS NULL OR bytes > 0", name="ck_media_bytes_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    gcs_object: Mapped[str] = mapped_column(String(256), unique=True)
    content_type: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[MediaStatus] = mapped_column(
        pg_enum(MediaStatus, "media_status"),
        default=MediaStatus.PENDING,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
