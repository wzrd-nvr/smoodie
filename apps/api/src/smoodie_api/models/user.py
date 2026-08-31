import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from smoodie_api.db import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Usernames are normalized to lowercase before insert and lookup; this
        # stops a mixed-case value slipping in through a path that forgets to.
        CheckConstraint("username = lower(username)", name="ck_users_username_lowercase"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Identity lives in Firebase; this row is the app-side profile.
    firebase_uid: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    username: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_media_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    # Soft delete: keeps authored content attributable after account removal.
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Sessions established before this instant are refused. Lets us invalidate
    # every outstanding session for an account immediately — a password reset,
    # a compromise, a "sign out everywhere" — without a per-request round trip
    # to Identity Toolkit.
    sessions_valid_after: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
