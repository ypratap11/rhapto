"""`_integrity` must log the kind of failure only.

asyncpg appends Postgres' `DETAIL: Failing row contains (...)` to the exception text, so `str(exc)`
or a formatted traceback would put a tester's free text (or profile content) in the log. This is the
DB-free twin of the sentinel test in `tests/api/test_feedback_api.py`: it builds the exception shape
SQLAlchemy raises and checks `caplog.text`, which includes formatted tracebacks.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError

from rhapto.api.errors import install_error_handlers

SENTINEL = "SENTINEL-4f1c"


class _Pg(Exception):
    constraint_name = "ck_feedback_area_iff_quick"


def _raise_integrity() -> None:
    try:
        raise _Pg(f"check violated\nDETAIL:  Failing row contains ({SENTINEL})")
    except _Pg as pg:
        orig = type("IntegrityError", (Exception,), {})(f"{type(pg)}: {pg}")
        orig.sqlstate = "23514"  # type: ignore[attr-defined]
        raise IntegrityError("INSERT INTO feedback ...", None, orig) from pg  # type: ignore[arg-type]


async def test_integrity_log_has_sqlstate_and_constraint_but_not_the_row(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = FastAPI()
    install_error_handlers(app)

    @app.post("/boom")
    async def boom() -> None:
        try:
            _raise_integrity()
        except IntegrityError as exc:
            # SQLAlchemy chains the driver error: orig.__cause__ is the asyncpg exception.
            exc.orig.__cause__ = exc.__cause__  # type: ignore[union-attr]
            raise

    caplog.set_level(logging.DEBUG)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/boom")

    assert response.status_code == 409
    assert SENTINEL not in response.text
    assert SENTINEL not in caplog.text
    assert "sqlstate=23514" in caplog.text
    assert "constraint=ck_feedback_area_iff_quick" in caplog.text
