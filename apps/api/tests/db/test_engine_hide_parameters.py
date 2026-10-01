"""`make_engine` must not let bound parameters (a tester's free text, profile content) into the error
text that `_integrity`/`_unexpected` and any caller may log.

The trigger is an error whose *server* message cannot contain row values (a missing table), so the
only place the sentinel could come from is SQLAlchemy's `[parameters: ...]` suffix. A CHECK
violation is deliberately not used: Postgres' own DETAIL carries row values (covered in T2).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

STATEMENT = "SELECT CAST(:p AS text) FROM feedback_no_such_table"


async def _error_text(engine: AsyncEngine, sentinel: str) -> str:
    async with engine.connect() as conn:
        with pytest.raises(ProgrammingError) as info:
            await conn.execute(text(STATEMENT), {"p": sentinel})
    return str(info.value)


async def test_make_engine_hides_parameters(engine: AsyncEngine) -> None:
    sentinel = f"SENTINEL-{uuid.uuid4()}"
    message = await _error_text(engine, sentinel)
    assert sentinel not in message
    assert "[SQL parameters hidden" in message


async def test_the_same_error_leaks_without_the_flag(migrated_db: str) -> None:
    """Control: proves the assertion above can fail. A plain engine puts the sentinel in the text."""
    sentinel = f"SENTINEL-{uuid.uuid4()}"
    plain = create_async_engine(migrated_db)
    try:
        message = await _error_text(plain, sentinel)
    finally:
        await plain.dispose()
    assert sentinel in message
