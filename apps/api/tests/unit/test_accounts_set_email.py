from __future__ import annotations

import asyncio
import uuid

from typer.testing import CliRunner

from rhapto.cli.main import app
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

runner = CliRunner()


def test_set_email_renames_an_existing_account(migrated_db, monkeypatch, session_factory) -> None:
    # `session_factory` is otherwise unused here -- it's requested purely for its function-scoped
    # teardown (tests/conftest.py), which truncates every table including `users` after the test.
    # Without it, the row this test creates via its own `make_engine(migrated_db)` session (below)
    # is never cleaned up: `migrated_db` is a session-scoped fixture backed by a real Postgres
    # database, so a leftover row from one pytest invocation collides with the NEXT invocation's
    # fresh seed of the same rename, producing a flaky "already in use" failure that depends on run
    # order and history rather than on this test's own behaviour.
    #
    # That teardown alone is not enough (N2): a database already dirty when THIS run starts --
    # from a killed process, a manual invocation, or any other source that never reached the
    # teardown -- would still fail once even with it in place. Fixed at the source instead: a
    # per-run unique target address, so this test can never collide with whatever a prior run left
    # behind, dirty or not.
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    old_email = f"user-{uuid.uuid4().hex}@example.com"
    new_email = f"owner-{uuid.uuid4().hex}@realdomain.com"

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            await get_or_create_user(session, old_email)
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "set-email", old_email, new_email])
    assert result.exit_code == 0, result.output
    assert "renamed" in result.output


def test_set_email_unknown_account_exits_1(migrated_db, monkeypatch, session_factory) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    result = runner.invoke(app, ["accounts", "set-email", "nobody@example.com", "x@example.com"])
    assert result.exit_code == 1


def test_set_email_refuses_a_taken_target(migrated_db, monkeypatch, session_factory) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            await get_or_create_user(session, "one@example.com")
            await get_or_create_user(session, "two@example.com")
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "set-email", "one@example.com", "two@example.com"])
    assert result.exit_code == 1
    assert "already in use" in result.output
