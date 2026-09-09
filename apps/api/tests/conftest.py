from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from rhapto.db.base import Base
from rhapto.db.models import User
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PROFILE = REPO_ROOT / "profile.example"

DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def demo_profile_dir() -> Path:
    return DEMO_PROFILE


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin = _dsn(url).rsplit("/", 1)[0] + "/postgres"
    dbname = url.rsplit("/", 1)[1]

    async def ensure() -> None:
        conn = await asyncpg.connect(admin)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
            if not exists:
                await conn.execute(f'CREATE DATABASE "{dbname}"')
        finally:
            await conn.close()

    import asyncio

    try:
        asyncio.run(ensure())
    except OSError as exc:
        pytest.skip(
            f"Postgres not reachable at {admin}: {exc}. Run `docker compose up -d db redis`."
        )
    return url


@pytest.fixture(scope="session")
def migrated_db(test_db_url: str) -> str:
    cfg = Config(str(API_DIR / "alembic.ini"))
    os.environ["DATABASE_URL"] = test_db_url
    command.upgrade(cfg, "head")
    return test_db_url


@pytest.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = make_session_factory(engine)
    yield factory
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest.fixture
async def user(session: AsyncSession) -> User:
    u = await get_or_create_user(session, "test@example.com")
    await session.commit()
    return u
