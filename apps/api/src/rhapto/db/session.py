from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


def make_engine(url: str) -> AsyncEngine:
    # hide_parameters: a DB error's text must not carry the bound values (tester feedback, profile
    # content) into a log line. It hides SQLAlchemy's `[parameters: ...]` suffix only; Postgres'
    # own `DETAIL: Failing row contains (...)` is handled in `api/errors.py::_integrity`.
    return create_async_engine(url, pool_pre_ping=True, hide_parameters=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
