"""User provisioning and lookup."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.verifier import VerifiedIdentity
from smoodie_api.models.user import User
from smoodie_api.services.events import record_event
from smoodie_api.services.usernames import suggest_username, with_suffix

# Bounded so a pathological collision run cannot loop forever.
MAX_USERNAME_ATTEMPTS = 50


@dataclass(frozen=True)
class ProvisionResult:
    user: User
    created: bool


async def get_by_firebase_uid(session: AsyncSession, uid: str) -> User | None:
    result = await session.execute(select(User).where(User.firebase_uid == uid))
    return result.scalar_one_or_none()


async def get_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(
        select(User).where(User.username == username, User.deleted_at.is_(None))
    )
    return result.scalar_one_or_none()


async def _claim_username(session: AsyncSession, base: str) -> str:
    """Find a free username, starting from `base`."""
    if await get_by_username(session, base) is None:
        return base
    for suffix in range(2, MAX_USERNAME_ATTEMPTS + 2):
        candidate = with_suffix(base, suffix)
        if await get_by_username(session, candidate) is None:
            return candidate
    raise RuntimeError(f"could not find a free username derived from {base!r}")


async def provision_from_identity(
    session: AsyncSession, identity: VerifiedIdentity
) -> ProvisionResult:
    """Return the app user for a verified Firebase identity, creating it once.

    First sign-in creates the row and emits user_signed_up; later sign-ins are a
    plain lookup, so the event fires exactly once per account.
    """
    existing = await get_by_firebase_uid(session, identity.uid)
    if existing is not None:
        return ProvisionResult(user=existing, created=False)

    base = suggest_username(identity.email, identity.name, identity.uid)
    username = await _claim_username(session, base)

    user = User(
        firebase_uid=identity.uid,
        username=username,
        display_name=(identity.name or username)[:80],
    )
    session.add(user)
    await session.flush()

    await record_event(
        session,
        event_type="user_signed_up",
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        payload={
            "username": user.username,
            "has_email": identity.email is not None,
            "email_verified": identity.email_verified,
        },
    )
    return ProvisionResult(user=user, created=True)
