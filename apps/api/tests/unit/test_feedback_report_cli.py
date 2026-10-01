"""`rhapto feedback report` end to end against the test database, plus the CLI-only guard.

Expected values below are LITERALS taken from the fixture input, not a re-flatten through the
renderer's own helpers: a check built from the implementation's premise would share its blind spot.
"""

from __future__ import annotations

import asyncio
import csv
import io
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rhapto.cli.main import app
from rhapto.config import get_settings
from rhapto.db.repositories import feedback as feedback_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

runner = CliRunner()
API_SRC = Path(__file__).resolve().parents[2] / "src" / "rhapto" / "api"


def test_the_cross_user_read_is_not_mentioned_anywhere_under_api() -> None:
    """Any occurrence, not only import lines: a router must not reach `all_with_email` at all."""
    offenders = [
        str(path)
        for path in API_SRC.rglob("*.py")
        if "all_with_email" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


def _seed(url: str) -> None:
    async def go() -> None:
        engine = make_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                a = await get_or_create_user(session, "tester-a@example.com")
                b = await get_or_create_user(session, "tester-b@example.com")
                await feedback_repo.insert(
                    session,
                    user_id=a.id,
                    form="survey",
                    page_area=None,
                    schema_version=1,
                    answers={
                        "getting_started": {"ease": 4, "stuck": "Could not find, the menu."},
                        "overall": {"would_use": "yes", "fix_first": "Speed.", "quote_ok": True},
                    },
                    app_version="0.1.0+abc123",
                    job_id=None,
                    package_id=None,
                )
                await feedback_repo.insert(
                    session,
                    user_id=b.id,
                    form="quick",
                    page_area="review",
                    schema_version=1,
                    answers={"kind": "bug", "rating": 2, "text": "Review froze"},
                    app_version="0.1.0+abc123",
                    job_id=None,
                    package_id=None,
                )
                await feedback_repo.insert(
                    session,
                    user_id=b.id,
                    form="quick",
                    page_area="other",
                    schema_version=1,
                    answers={"kind": "idea"},
                    app_version="0.1.0",
                    job_id=None,
                    package_id=None,
                )
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(go())


@pytest.fixture
def env(migrated_db: str, session_factory: object, monkeypatch: pytest.MonkeyPatch) -> str:
    # `session_factory` is requested only for its teardown, which truncates every table.
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "cli-test-secret")
    get_settings.cache_clear()
    return migrated_db


def test_csv_matches_the_stored_rows(env: str) -> None:
    _seed(env)
    result = runner.invoke(app, ["feedback", "report", "--csv"])
    get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    rows = list(csv.DictReader(io.StringIO(result.output)))
    assert len(rows) == 3
    by_kind = {(r["form"], r["page_area"], r["quick.kind"]): r for r in rows}

    survey = by_kind[("survey", "", "")]
    assert survey["getting_started.ease"] == "4"
    assert survey["getting_started.stuck"] == "Could not find, the menu."
    assert survey["overall.would_use"] == "yes"
    assert survey["overall.fix_first"] == "Speed."
    assert survey["overall.quote_ok"] == "true"
    assert survey["app_version"] == "0.1.0+abc123"
    assert survey["quick.text"] == ""

    review = by_kind[("quick", "review", "bug")]
    assert review["quick.rating"] == "2"
    assert review["quick.text"] == "Review froze"
    assert review["getting_started.ease"] == ""

    other = by_kind[("quick", "other", "idea")]
    assert other["quick.rating"] == "" and other["quick.text"] == ""
    assert other["app_version"] == "0.1.0"

    # Two quick rows share a tester; the survey is a different one.
    assert review["tester"] == other["tester"] != survey["tester"]
    assert "email" not in rows[0]


def test_default_output_has_no_email_and_the_flag_adds_it(env: str) -> None:
    _seed(env)
    plain = runner.invoke(app, ["feedback", "report"])
    assert plain.exit_code == 0, plain.output
    assert "example.com" not in plain.output
    assert "Could not find, the menu." in plain.output
    flagged = runner.invoke(app, ["feedback", "report", "--with-emails"])
    get_settings.cache_clear()
    assert flagged.exit_code == 0, flagged.output
    assert "tester-a@example.com" in flagged.output
    assert "tester-b@example.com" in flagged.output


def test_csv_with_emails_adds_the_column(env: str) -> None:
    _seed(env)
    result = runner.invoke(app, ["feedback", "report", "--csv", "--with-emails"])
    get_settings.cache_clear()
    rows = list(csv.DictReader(io.StringIO(result.output)))
    assert {r["email"] for r in rows} == {"tester-a@example.com", "tester-b@example.com"}


def test_empty_table_exits_zero(env: str) -> None:
    result = runner.invoke(app, ["feedback", "report"])
    get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "No feedback yet." in result.output


def test_since_in_the_future_filters_everything(env: str) -> None:
    _seed(env)
    result = runner.invoke(app, ["feedback", "report", "--since", "2999-01-01"])
    get_settings.cache_clear()
    assert result.exit_code == 0, result.output
    assert "No feedback yet." in result.output


def test_bad_since_is_a_clean_error(env: str) -> None:
    result = runner.invoke(app, ["feedback", "report", "--since", "yesterday"])
    get_settings.cache_clear()
    assert result.exit_code == 1


def test_refuses_to_run_without_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pseudonym key derives from the secret; an empty one must not silently weaken it."""
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "")
    get_settings.cache_clear()
    result = runner.invoke(app, ["feedback", "report"])
    get_settings.cache_clear()
    assert result.exit_code == 1
    assert "RHAPTO_SECRET_KEY" in result.output
