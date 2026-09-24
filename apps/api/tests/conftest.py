from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import asyncpg
import pytest
import redis.asyncio
import redis.exceptions
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from alembic import command
from rhapto.db.base import Base
from rhapto.db.models import User
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

# `get_settings()` (rhapto.config) now refuses to run with no RHAPTO_SECRET_KEY, and some test
# modules import `rhapto.worker.main` / `rhapto.api.app`, both of which call it at *import* time
# (a cron schedule and the module-level `app`, respectively) -- before any fixture, including
# `_no_provider_env` below, gets a chance to run. A bare test environment has no `.env` and no
# such variable, so collection itself would fail without a value seeded here first, before any of
# those test modules are imported. This value is never used to encrypt anything real; the tests
# that care about the derive-from-token fallback or an unset key construct `Settings(...)`
# directly and are unaffected by it.
os.environ.setdefault(
    "RHAPTO_SECRET_KEY",
    base64.urlsafe_b64encode(hashlib.sha256(b"rhapto-test-suite-secret-key").digest()).decode(),
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEMO_PROFILE = REPO_ROOT / "profile.example"

DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _reset_root_logging_handlers() -> Iterator[None]:
    """`rhapto db upgrade` runs alembic/env.py, which calls `logging.config.fileConfig` and
    installs a `StreamHandler` on the root logger bound to whatever `sys.stderr` object is
    current at that moment. Inside a `CliRunner`-invoked test that stream is a capture pipe
    torn down when the test ends, so a later, unrelated log call anywhere else in the suite
    that propagates to the root logger fails to write to it; Python's logging module then
    dumps a "Logging error" traceback into *that* test's captured output. Snapshot and
    restore the root logger's handlers/level around every test so this can't leak across
    tests.
    """
    root = logging.getLogger()
    handlers = list(root.handlers)
    level = root.level
    try:
        yield
    finally:
        root.handlers[:] = handlers
        root.setLevel(level)


# Every variable the LLM settings read. `Settings(_env_file=None)` only disables the dotenv file;
# pydantic-settings still reads os.environ, so a contributor with their own provider key exported
# would otherwise have it decide what these tests see — and a failing assertion would print it into
# the pytest report, the terminal, any saved log and any CI job where it is an injected secret.
# Cleared for every test so the suite starts from a known-empty environment; tests that want a value
# set it themselves.
PROVIDER_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "RHAPTO_LLM_PROVIDER",
    "RHAPTO_LLM_MODEL",
    "RHAPTO_SECRET_KEY",
)


@pytest.fixture(autouse=True)
def _no_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in PROVIDER_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


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


DEFAULT_TEST_REDIS_URL = "redis://localhost:6379/1"


@pytest.fixture(scope="session")
def test_redis_url() -> str:
    """URL of a reachable Redis, or skip. Mirrors `test_db_url` for the broker-backed tests."""
    url = os.environ.get("RHAPTO_TEST_REDIS_URL", DEFAULT_TEST_REDIS_URL)

    async def ping() -> None:
        client = redis.asyncio.from_url(url)
        try:
            await client.ping()
        finally:
            await client.aclose()

    try:
        asyncio.run(ping())
    except (OSError, redis.exceptions.RedisError) as exc:
        pytest.skip(f"Redis not reachable at {url}: {exc}. Run `docker compose up -d db redis`.")
    return url
