import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Index, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from smoodie_api.db import Base


class EventOutbox(Base):
    """Transactional outbox: events are written in the same transaction as the
    data they describe, then drained to Pub/Sub by the publisher (M4).

    Writing here from M1 onward means M4 only has to wire up publishing — there
    is no retrofit of event emission across every endpoint later.
    """

    __tablename__ = "event_outbox"
    __table_args__ = (
        # The publisher only scans undrained events, a set that stays near-empty
        # while the pipeline keeps up. Partial index keeps that scan cheap no
        # matter how large the table grows.
        Index(
            "ix_event_outbox_unpublished",
            "occurred_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
