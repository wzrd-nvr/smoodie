"""Username claiming and account provisioning at the service layer."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from smoodie_api.auth.verifier import VerifiedIdentity
from smoodie_api.services import users as user_service


def _identity(uid: str, email: str | None = None, name: str | None = None) -> VerifiedIdentity:
    return VerifiedIdentity(uid=uid, email=email, email_verified=True, name=name)


async def test_provisioning_is_idempotent_for_the_same_uid(db: AsyncSession) -> None:
    first = await user_service.provision_from_identity(db, _identity("u1", "a@example.com"))
    await db.commit()
    second = await user_service.provision_from_identity(db, _identity("u1", "a@example.com"))

    assert first.created is True
    assert second.created is False
    assert first.user.id == second.user.id


async def test_display_name_falls_back_to_username(db: AsyncSession) -> None:
    """Email/password signups have no display name until the user sets one."""
    result = await user_service.provision_from_identity(db, _identity("u1", "angel@example.com"))
    assert result.user.display_name == "angel"


async def test_long_display_names_are_truncated_to_fit(db: AsyncSession) -> None:
    result = await user_service.provision_from_identity(
        db, _identity("u1", "a@example.com", name="N" * 200)
    )
    assert len(result.user.display_name) == 80


async def test_claiming_gives_up_rather_than_looping_forever(
    db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pathological collision run must terminate, not spin."""
    monkeypatch.setattr(user_service, "MAX_USERNAME_ATTEMPTS", 2)

    for uid in ("u1", "u2", "u3"):
        await user_service.provision_from_identity(db, _identity(uid, "angel@example.com"))
        await db.commit()

    with pytest.raises(RuntimeError, match="could not find a free username"):
        await user_service.provision_from_identity(db, _identity("u4", "angel@example.com"))


async def test_soft_deleted_users_are_not_returned_by_username(db: AsyncSession) -> None:
    from datetime import UTC, datetime

    result = await user_service.provision_from_identity(db, _identity("u1", "angel@example.com"))
    await db.commit()

    result.user.deleted_at = datetime.now(UTC)
    await db.commit()

    assert await user_service.get_by_username(db, "angel") is None
    # ...but the row is still reachable by uid, so content stays attributable.
    assert await user_service.get_by_firebase_uid(db, "u1") is not None
