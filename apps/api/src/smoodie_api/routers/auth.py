"""Session exchange: Firebase ID token in, http-only session cookie out.

The web app renders server-side, so its loaders need a cookie the browser sends
automatically — not an ID token held in client JavaScript. Exchanging once here
also means the short-lived ID token never has to be refreshed by the SSR layer.
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.dependencies import (
    SESSION_COOKIE_NAME,
    MaybeUser,
    get_verifier,
)
from smoodie_api.auth.verifier import InvalidToken, TokenVerifier
from smoodie_api.config import get_settings
from smoodie_api.db import get_session
from smoodie_api.schemas.user import PublicProfile, SessionRequest, SessionResponse
from smoodie_api.services import users as user_service

router = APIRouter(prefix="/v1/auth", tags=["auth"])


@router.post("/session", response_model=SessionResponse)
async def create_session(
    body: SessionRequest,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_session)],
    verifier: Annotated[TokenVerifier, Depends(get_verifier)],
) -> SessionResponse:
    settings = get_settings()
    try:
        identity = verifier.verify_id_token(body.id_token)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That sign-in couldn't be verified. Try again.",
        ) from exc

    expires_in = timedelta(days=settings.session_cookie_days)
    try:
        cookie = verifier.create_session_cookie(body.id_token, expires_in)
    except InvalidToken as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="That sign-in couldn't be verified. Try again.",
        ) from exc

    result = await user_service.provision_from_identity(session, identity)
    await session.commit()
    await session.refresh(result.user)

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=cookie,
        max_age=int(expires_in.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return SessionResponse(user=PublicProfile.model_validate(result.user), created=result.created)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(response: Response, user: MaybeUser) -> Response:
    """Sign out. Succeeds even without a valid session so the UI can always
    offer sign-out without stranding a user on an expired cookie."""
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/", httponly=True, samesite="lax")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
