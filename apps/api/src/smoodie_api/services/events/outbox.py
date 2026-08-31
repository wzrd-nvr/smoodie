"""Transactional outbox writer.

Callers pass their existing session so the event lands in the same transaction
as the change it describes: if the business write rolls back, so does the event.
The publisher (M4) drains unpublished rows to Pub/Sub.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.models.event import EventOutbox


async def record_event(
    session: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    actor_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    schema_version: int = 1,
) -> EventOutbox:
    event = EventOutbox(
        event_type=event_type,
        schema_version=schema_version,
        actor_id=actor_id,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
    )
    session.add(event)
    # Deliberately no commit: the caller owns the transaction boundary, which is
    # the whole point of an outbox.
    await session.flush()
    return event
