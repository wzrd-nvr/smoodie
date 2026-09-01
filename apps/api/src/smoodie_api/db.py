import enum
from collections.abc import AsyncIterator

from sqlalchemy import Enum
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from smoodie_api.config import get_settings


class Base(DeclarativeBase):
    pass


def create_engine_from_settings() -> AsyncEngine:
    return create_async_engine(get_settings().database_url, pool_pre_ping=True)


engine = create_engine_from_settings()
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def pg_enum(enum_cls: type[enum.Enum], name: str) -> Enum:
    """A Postgres enum whose labels are the member *values*, not their names.

    Without values_callable, SQLAlchemy stores "PUBLISHED" while the API and the
    event stream both serialize "published" — the same state spelled two ways
    depending on where you look at it.
    """
    return Enum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda e: [member.value for member in e],
    )
