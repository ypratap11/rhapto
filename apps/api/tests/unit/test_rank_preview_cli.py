from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rhapto.cli.main import app
from rhapto.config import get_settings
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.scoring import score_and_store

runner = CliRunner()
QA = Track(
    id="qa",
    name="QA",
    resume_base="b",
    min_fit=60,
    field="engineering",
    role="qa",
    keywords=[
        "regression testing",
        "test automation",
        "quality engineering",
        "defect triage",
        "test strategy",
        "end to end testing",
    ],
    description="Test automation and regression testing for software quality",
)
JD = "Own the regression testing and test automation strategy. " * 4


def _seed(url: str) -> None:
    async def go() -> None:
        engine = make_engine(url)
        try:
            async with make_session_factory(engine)() as session:
                user = await get_or_create_user(session, "tester-a@example.com")
                await profile_repo.upsert_track(session, user.id, QA)
                jobs = [
                    await jobs_repo.create_job(
                        session, user.id, jd_text=JD, title=title, company=f"{title} Co"
                    )
                    for title in ("Senior QA Engineer", "Flight Test Engineer")
                ]
                await score_and_store(session, user.id, jobs, FakeEmbeddingProvider(dimensions=384))
                await session.commit()
        finally:
            await engine.dispose()

    asyncio.run(go())


@pytest.fixture
def env(migrated_db: str, session_factory: object, monkeypatch: pytest.MonkeyPatch) -> str:
    # `session_factory` is requested only for its teardown, which truncates every table.
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "cli-test-secret")
    monkeypatch.setattr("rhapto.cli.main.get_settings", get_settings.__wrapped__)
    return migrated_db


def test_rank_preview_prints_pseudonymous_lists_and_writes_blind_files(
    env: str, tmp_path: Path
) -> None:
    _seed(env)
    blind = tmp_path / "blind"
    result = runner.invoke(
        app, ["rank-preview", "--embedder", "fake", "--top", "5", "--blind-dir", str(blind)]
    )
    assert result.exit_code == 0, result.output
    assert "example.com" not in result.output  # no emails, ever
    assert "## T-" in result.output
    for heading in ("Today (as users see it)", "Today + arrange", "New scores + arrange"):
        assert heading in result.output
    assert len(list(blind.glob("judge-T-*.md"))) == 1 and (blind / "key.json").exists()


def test_rank_preview_refuses_the_wrong_database(env: str) -> None:
    right = env.rsplit("/", 1)[1]
    ok = runner.invoke(app, ["rank-preview", "--embedder", "fake", "--expect-database", right])
    assert ok.exit_code == 0, ok.output
    wrong = runner.invoke(
        app, ["rank-preview", "--embedder", "fake", "--expect-database", "rhapto"]
    )
    assert wrong.exit_code == 1 and "refusing to run" in wrong.output


def test_rank_preview_with_no_accounts_exits_zero(env: str) -> None:
    result = runner.invoke(app, ["rank-preview", "--embedder", "fake"])
    assert result.exit_code == 0, result.output


def test_rank_preview_refuses_to_run_without_a_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """The pseudonym key derives from the secret; an empty one must not silently weaken it."""
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "")
    monkeypatch.setattr("rhapto.cli.main.get_settings", get_settings.__wrapped__)
    result = runner.invoke(app, ["rank-preview", "--embedder", "fake"])
    assert result.exit_code == 1
    assert "RHAPTO_SECRET_KEY" in result.output
