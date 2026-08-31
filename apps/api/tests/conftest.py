"""Test fixtures.

Integration tests run against a real Postgres (a service container in CI, a
local instance in development) because the schema leans on Postgres-specific
types and constraints that SQLite cannot represent. Each test gets a clean
schema rather than a shared one, so ordering can never leak state between tests.
"""

import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from smoodie_api.auth.dependencies import get_verifier
from smoodie_api.config import get_settings
from smoodie_api.db import Base, get_session
from smoodie_api.main import app
from smoodie_api.routers.media import get_object_store
from tests.fakes import FakeObjectStore, FakeVerifier

TEST_DATABASE_URL = os.environ.get(
    "SMOODIE_TEST_DATABASE_URL",
    os.environ.get(
        "SMOODIE_DATABASE_URL",
        "postgresql+asyncpg://smoodie:smoodie@localhost:5432/smoodie",
    ),
)


@pytest.fixture(autouse=True)
def _plain_http_cookies(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Session cookies default to Secure, which browsers and httpx both refuse
    to send over plain http. Tests (and local dev) speak http, so turn it off
    here rather than weakening the deployed default."""
    monkeypatch.setenv("SMOODIE_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
async def db_schema() -> AsyncIterator[str]:
    """Create an isolated schema per test and drop it afterwards."""
    schema = f"test_{uuid.uuid4().hex[:12]}"
    admin = create_async_engine(TEST_DATABASE_URL, poolclass=None)
    async with admin.begin() as conn:
        await conn.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    await admin.dispose()

    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": schema}},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()

    yield schema

    admin = create_async_engine(TEST_DATABASE_URL)
    async with admin.begin() as conn:
        await conn.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
    await admin.dispose()


@pytest.fixture
async def session_factory(db_schema: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"server_settings": {"search_path": db_schema}},
    )
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with session_factory() as session:
        yield session


@pytest.fixture
def verifier() -> FakeVerifier:
    return FakeVerifier()


@pytest.fixture
def store() -> FakeObjectStore:
    return FakeObjectStore()


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
    verifier: FakeVerifier,
    store: FakeObjectStore,
) -> AsyncIterator[httpx.AsyncClient]:
    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_verifier] = lambda: verifier
    app.dependency_overrides[get_object_store] = lambda: store

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
