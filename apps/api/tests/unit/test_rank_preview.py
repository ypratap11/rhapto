from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.feedback import pseudonym
from rhapto.services.rank_preview import (
    DatabaseMismatchError,
    excerpt_of,
    read_only_session,
    render_report,
    run_rank_preview,
    score_judgements,
    with_handwritten_track,
    write_blind_files,
)
from rhapto.services.scoring import score_and_store

KEY = b"rank-preview-test-key"
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
JD = (
    "Own the regression testing and test automation strategy, triage defects and drive end to end "
    "testing. "
) * 3


async def _seed(session: AsyncSession, user: User) -> None:
    """A wrong role on top by its stored (pre-change) score, the real role below it, and three
    copies of one posting."""
    await profile_repo.upsert_track(session, user.id, QA)
    flight = await jobs_repo.create_job(
        session,
        user.id,
        jd_text=JD,
        title="Flight Test Engineer",
        company="Shield AI",
        location="Boston, MA",
    )
    real = await jobs_repo.create_job(
        session,
        user.id,
        jd_text=JD,
        title="Senior QA Engineer",
        company="Acme",
        location="Denver, CO",
    )
    copies = [
        await jobs_repo.create_job(
            session,
            user.id,
            jd_text=f"{JD} copy {n}",
            title=f"Staff QA Engineer (R{7000 + n})",
            company="Dup Co",
            location="Austin, TX",
        )
        for n in range(3)
    ]
    await score_and_store(
        session, user.id, [flight, real, *copies], FakeEmbeddingProvider(dimensions=384)
    )
    flight.best_fit, flight.best_track_id = 90, "qa"  # what the old scorer said
    real.best_fit, real.best_track_id = 50, "qa"
    await session.commit()


async def _fingerprint(factory: async_sessionmaker[AsyncSession]) -> list[str]:
    async with factory() as check:
        out = []
        for table in ("jobs", "job_scores", "tracks", "answers"):
            row = await check.execute(
                text(
                    f"SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), '')) FROM {table} t"
                )
            )
            out.append(str(row.scalar()))
        return out


async def test_new_scores_demote_the_wrong_role_and_the_old_order_is_what_is_stored(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session, user)
    [preview] = await run_rank_preview(session_factory, FakeEmbeddingProvider(dimensions=384), KEY)

    assert preview.old_plain[0].title == "Flight Test Engineer"  # stored fit 90
    assert preview.new_plain[0].title != "Flight Test Engineer"
    flight = next(j for j in preview.new_plain if j.title == "Flight Test Engineer")
    assert flight.best_fit is not None and flight.best_fit <= 45
    real = next(j for j in preview.new_plain if j.title == "Senior QA Engineer")
    assert real.best_fit is not None and real.best_fit >= 60
    assert preview.track_names == ("QA",) and preview.window_jobs == 5


async def test_collapse_shows_in_the_arranged_lists_only(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session, user)
    [preview] = await run_rank_preview(session_factory, FakeEmbeddingProvider(dimensions=384), KEY)
    is_copy = lambda j: (j.title or "").startswith("Staff QA Engineer")  # noqa: E731
    assert sum(1 for j in preview.new_plain if is_copy(j)) == 3
    assert sum(1 for j in preview.new_arranged if is_copy(j)) == 1
    assert sum(1 for j in preview.old_plain if is_copy(j)) == 3
    assert sum(1 for j in preview.old_arranged if is_copy(j)) == 1


async def test_a_run_changes_nothing_in_the_database(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    tmp_path: Path,
) -> None:
    await _seed(session, user)
    before = await _fingerprint(session_factory)
    previews = await run_rank_preview(
        session_factory, FakeEmbeddingProvider(dimensions=384), KEY, synthetic_mixed=True
    )
    write_blind_files(previews, tmp_path, seed="s")
    assert (
        await _fingerprint(session_factory) == before
    )  # byte-for-byte: jobs, scores, tracks, answers


async def test_a_write_attempted_during_a_run_is_refused_and_the_database_is_unchanged(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run itself is made to try a COMMITTED write (the shape of a future change that calls
    score_and_store). With the guard it is refused before anything lands; without the guard the
    commit succeeds, nothing raises and the fingerprint changes, so this test fails."""
    await _seed(session, user)
    before = await _fingerprint(session_factory)
    real_get_answers = profile_repo.get_answers

    async def get_answers_then_write(s: AsyncSession, user_id: object) -> dict[str, str]:
        answers = await real_get_answers(s, user_id)  # type: ignore[arg-type]
        s.add(
            Job(
                user_id=user.id,
                source="manual",
                jd_text="x" * 60,
                dedupe_hash="written-by-the-preview",
                discovered_at=datetime.now(UTC),
            )
        )
        await s.commit()
        return answers

    monkeypatch.setattr(profile_repo, "get_answers", get_answers_then_write)
    with pytest.raises(DBAPIError, match="read-only transaction"):
        await run_rank_preview(session_factory, FakeEmbeddingProvider(dimensions=384), KEY)
    assert await _fingerprint(session_factory) == before


async def test_a_write_inside_the_read_only_session_is_refused(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    """Proves the guard is live: without SET TRANSACTION READ ONLY this flush would succeed."""
    with pytest.raises(DBAPIError, match="read-only transaction"):
        async with read_only_session(session_factory) as ro:
            ro.add(
                Job(
                    user_id=user.id,
                    source="manual",
                    jd_text="x" * 60,
                    dedupe_hash="h",
                    discovered_at=datetime.now(UTC),
                )
            )
            await ro.flush()


async def test_the_report_names_testers_by_pseudonym_and_never_by_email(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session, user)
    previews = await run_rank_preview(session_factory, FakeEmbeddingProvider(dimensions=384), KEY)
    report = render_report(previews)
    assert previews[0].label == pseudonym(user.id, KEY) and previews[0].label.startswith("T-")
    assert f"## {previews[0].label}" in report
    assert user.email not in report and "example.com" not in report


async def test_synthetic_mixed_account_pairs_a_hand_written_track_with_the_role_track(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session, user)
    assert [t.role for t in with_handwritten_track([QA])] == ["qa", None]
    previews = await run_rank_preview(
        session_factory, FakeEmbeddingProvider(dimensions=384), KEY, synthetic_mixed=True
    )
    assert [p.label for p in previews] == [pseudonym(user.id, KEY), "SYNTH-MIXED"]
    assert previews[-1].track_names == ("QA", "QA (hand-written)")


async def test_blind_files_are_one_shuffled_union_with_no_list_labels(
    session: AsyncSession,
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    tmp_path: Path,
) -> None:
    """Plan review I-2: the judge marks every job in the de-duplicated UNION of the four lists
    once, with nothing to say which list(s) it came from, so it cannot tell old from new (the old
    list is the one with visible duplicates) and the counts for ALL four lists come from the same
    marks."""
    await _seed(session, user)
    previews = await run_rank_preview(session_factory, FakeEmbeddingProvider(dimensions=384), KEY)
    [preview] = previews
    write_blind_files(previews, tmp_path / "a", seed="s1")
    write_blind_files(previews, tmp_path / "b", seed="s1")
    label = preview.label

    judge = (tmp_path / "a" / f"judge-{label}.md").read_text(encoding="utf-8")
    # The tester's role names, on their own line (a bare `"QA" in judge` would also pass on a job
    # title or excerpt).
    assert "Target role(s): QA" in judge.splitlines()
    for leak in ("List X", "List Y", "Today", "New scores", "old", "stored", "arrange"):
        assert leak not in judge, leak
    numbered = [line for line in judge.splitlines() if line[:1].isdigit()]
    four_lists = (preview.old_plain, preview.old_arranged, preview.new_plain, preview.new_arranged)
    union_ids = {j.id for jobs in four_lists for j in jobs}
    assert len(numbered) == len(union_ids)  # each job once, however many lists it is in
    excerpts = [line for line in judge.splitlines() if line.startswith("   ")]
    assert excerpts and all(len(line) <= 3 + 300 for line in excerpts)

    key = json.loads((tmp_path / "a" / "key.json").read_text(encoding="utf-8"))[label]
    assert set(key) == {str(n) for n in range(1, len(union_ids) + 1)}
    allowed = {"old_plain", "old_arranged", "new_plain", "new_arranged"}
    assert all(lists and set(lists) <= allowed for lists in key.values())
    # Deterministic for a given seed, so the key can be regenerated.
    assert key == json.loads((tmp_path / "b" / "key.json").read_text(encoding="utf-8"))[label]


def test_score_judgements_counts_relevant_marks_per_list() -> None:
    key = {
        "1": ["old_plain", "new_plain"],
        "2": ["old_plain"],
        "3": ["new_plain", "new_arranged"],
        "4": ["new_arranged"],
    }
    marks = {"1": "R", "2": "N", "3": "R", "4": "r"}  # case-insensitive
    assert score_judgements(key, marks) == {
        "old_plain": (1, 2),
        "new_plain": (2, 2),
        "new_arranged": (2, 2),
    }
    with pytest.raises(ValueError):
        score_judgements(key, {"1": "R"})  # every job must be marked


async def test_the_database_guard_refuses_a_run_against_the_wrong_database(
    session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    async with session_factory() as probe:
        actual = str((await probe.execute(text("SELECT current_database()"))).scalar())
    embedder = FakeEmbeddingProvider(dimensions=384)
    await run_rank_preview(
        session_factory, embedder, KEY, expect_database=actual
    )  # right one: runs
    with pytest.raises(DatabaseMismatchError):
        await run_rank_preview(session_factory, embedder, KEY, expect_database="rhapto")


async def test_title_coverage_lists_what_matched_and_what_was_capped(
    session: AsyncSession, session_factory: async_sessionmaker[AsyncSession], user: User
) -> None:
    await _seed(session, user)
    [preview] = await run_rank_preview(session_factory, FakeEmbeddingProvider(dimensions=384), KEY)
    matched = dict(preview.matched_titles)
    capped = dict(preview.capped_titles)
    assert matched["Senior QA Engineer"] == 1 and "Flight Test Engineer" not in matched
    assert capped["Flight Test Engineer"] == 1 and "Senior QA Engineer" not in capped
    assert "Flight Test Engineer" in render_report([preview])


def test_excerpt_is_whitespace_collapsed_and_bounded() -> None:
    assert excerpt_of("a  b\n\n c") == "a b c"
    long = excerpt_of("word " * 200)
    assert len(long) <= 300 and long.endswith("...")
