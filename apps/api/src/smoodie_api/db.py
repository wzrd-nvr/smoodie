from collections.abc import AsyncIterator

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
