"""Profile read and update."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.dependencies import CurrentUser
from smoodie_api.db import get_session
from smoodie_api.schemas.user import ProfileUpdate, PublicProfile
from smoodie_api.services import users as user_service
from smoodie_api.services.events import record_event

router = APIRouter(prefix="/v1/users", tags=["users"])


@router.get("/me", response_model=PublicProfile)
async def read_me(user: CurrentUser) -> PublicProfile:
    return PublicProfile.model_validate(user)


@router.patch("/me", response_model=PublicProfile)
async def update_me(
    body: ProfileUpdate,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PublicProfile:
    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return PublicProfile.model_validate(user)

    for field, value in changes.items():
        setattr(user, field, value)

    # The whole write is guarded, not just the commit: recording the event
    # flushes the pending update, so a username collision surfaces there rather
    # than at commit time. Guarding only the commit turns a taken username into
    # a 500.
    try:
        await session.flush()
        await record_event(
            session,
            event_type="profile_updated",
            actor_id=user.id,
            entity_type="user",
            entity_id=user.id,
            # Field names only: profile contents are personal data and the
            # analytics warehouse has no need for them.
            payload={"fields": sorted(changes.keys())},
        )
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That username is already taken.",
        ) from exc

    await session.refresh(user)
    return PublicProfile.model_validate(user)


@router.get("/{username}", response_model=PublicProfile)
async def read_profile(
    username: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PublicProfile:
    profile = await user_service.get_by_username(session, username.lower())
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such profile.")
    return PublicProfile.model_validate(profile)
