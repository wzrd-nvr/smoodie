"""Auth dependencies: session cookie in, User row out."""

from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.verifier import (
    FirebaseTokenVerifier,
    InvalidToken,
    TokenVerifier,
)
from smoodie_api.config import get_settings
from smoodie_api.db import get_session
from smoodie_api.models.user import User
from smoodie_api.services import users as user_service

SESSION_COOKIE_NAME = "smoodie_session"


def get_verifier(request: Request) -> TokenVerifier:
    """Resolve the token verifier, allowing tests to inject a fake via app state."""
    override: TokenVerifier | None = getattr(request.app.state, "token_verifier", None)
    if override is not None:
        return override
    return FirebaseTokenVerifier(get_settings().firebase_project_id)


async def get_current_user(
    session: Annotated[AsyncSession, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
    smoodie_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User:
    if not smoodie_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not signed in.")
    try:
        identity = verifier.verify_session_cookie(smoodie_session)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session has expired. Sign in again.",
        ) from exc

    user = await user_service.get_by_firebase_uid(session, identity.uid)
    if user is None or user.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account not found.")
    return user


async def get_current_user_optional(
    session: Annotated[AsyncSession, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
    smoodie_session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> User | None:
    """For public pages that render differently when signed in."""
    if not smoodie_session:
        return None
    try:
        identity = verifier.verify_session_cookie(smoodie_session)
    except InvalidToken:
        return None
    user = await user_service.get_by_firebase_uid(session, identity.uid)
    return user if user is not None and user.deleted_at is None else None


CurrentUser = Annotated[User, Depends(get_current_user)]
MaybeUser = Annotated[User | None, Depends(get_current_user_optional)]
