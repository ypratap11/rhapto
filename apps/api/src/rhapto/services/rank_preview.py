"""`rhapto rank-preview`: the top of every account's list, before and after, strictly read-only.

Runs on the server over SSH and never behind HTTP: it reads every account. Each account is read in
its own transaction whose FIRST statement is `SET TRANSACTION READ ONLY` (so any accidental flush
raises) and which is always rolled back. New scores are computed in memory with the same
`engine.score_job` the worker uses and ordered with the same `relevance_key` / `arrange` the API
uses, so what is evaluated is what ships. No email is selected, printed or written: testers are the
HMAC pseudonyms of `rhapto feedback report`.
"""

from __future__ import annotations

import json
import random
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Track as TrackRow
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.scoring import (
    best_track,
    location_preference_from_answers,
    location_tier,
    score_job,
    track_text,
)
from rhapto.models.profile.tracks import Track
from rhapto.services.feedback import pseudonym
from rhapto.services.profile_sync import track_row_to_model
from rhapto.services.ranking import arrange, relevance_key
from rhapto.services.scoring import role_titles_for

EXCERPT_CHARS = 300
TIERS = ("preferred", "remote", "country", "unknown", "abroad")
SYNTHETIC_LABEL = "SYNTH-MIXED"
LIST_NAMES = ("old_plain", "old_arranged", "new_plain", "new_arranged")
COVERAGE_ROWS = 30


class DatabaseMismatchError(RuntimeError):
    """The connected database is not the one the caller said it must be."""


@dataclass(frozen=True)
class PreviewJob:
    id: uuid.UUID
    company: str | None
    title: str | None
    location: str | None
    best_fit: int | None
    posted_at: datetime | None
    discovered_at: datetime
    excerpt: str
    tier: str
    #: `min_fit` of the track that produced `best_fit`; None when unscored or the track is gone.
    min_fit: int | None
    #: Role blend only: did the title match a `titles` phrase? None for the legacy blend / unscored.
    matched: bool | None = None


@dataclass(frozen=True)
class UserPreview:
    label: str
    track_names: tuple[str, ...]
    window_jobs: int
    old_plain: list[PreviewJob]
    old_arranged: list[PreviewJob]
    new_plain: list[PreviewJob]
    new_arranged: list[PreviewJob]
    #: Jobs at or above their track's min_fit, per location tier: (old, new). Reported, not gated.
    above_min_fit: dict[str, tuple[int, int]]
    #: The most frequent titles (title, jobs) in the window that matched / were capped under the new
    #: blend: what the owner reads to review the title lists against the real pool.
    matched_titles: list[tuple[str, int]]
    capped_titles: list[tuple[str, int]]


def excerpt_of(jd_text: str, limit: int = EXCERPT_CHARS) -> str:
    flat = " ".join(jd_text.split())
    return flat if len(flat) <= limit else flat[: limit - 3].rstrip() + "..."


@asynccontextmanager
async def read_only_session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A session whose transaction is READ ONLY from its first statement and always rolls back."""
    async with factory() as session:
        # With SQLAlchemy's autobegin this must be the first statement executed on the session.
        await session.execute(text("SET TRANSACTION READ ONLY"))
        try:
            yield session
        finally:
            await session.rollback()


async def accounts_with_tracks(session: AsyncSession) -> list[uuid.UUID]:
    return list(
        await session.scalars(select(TrackRow.user_id).distinct().order_by(TrackRow.user_id))
    )


def with_handwritten_track(tracks: list[Track]) -> list[Track]:
    """The synthetic mixed account: one role track beside one hand-written track.

    `best_track` takes the maximum, so the hand-written track (legacy blend, no title check) can
    lift a wrong-role job above the cap. No production account is mixed; this measures the effect.
    """
    base = next(t for t in tracks if t.role)
    handwritten = Track(
        id="synthetic-handwritten",
        name=f"{base.name} (hand-written)",
        resume_base=base.resume_base,
        min_fit=base.min_fit,
        keywords=list(base.keywords),
        description=base.description,
    )
    return [base, handwritten]


def _arranged(items: list[PreviewJob]) -> list[PreviewJob]:
    return [items[a.index] for a in arrange(items)]


def _above(jobs: list[PreviewJob]) -> dict[str, int]:
    counts = dict.fromkeys(TIERS, 0)
    for job in jobs:
        if job.best_fit is not None and job.min_fit is not None and job.best_fit >= job.min_fit:
            counts[job.tier] += 1
    return counts


async def preview_tracks(
    session: AsyncSession,
    user_id: uuid.UUID,
    tracks: list[Track],
    embedder: EmbeddingProvider,
    *,
    label: str,
    now: datetime,
    top_n: int = 15,
) -> UserPreview:
    preference = location_preference_from_answers(await profile_repo.get_answers(session, user_id))
    roles = role_titles_for(tracks)
    # Track embeddings in memory: nothing is cached on the track rows (that would be a write).
    vectors = await embedder.embed([track_text(t) for t in tracks])
    track_vectors = {t.id: v for t, v in zip(tracks, vectors, strict=True)}
    min_fit_new = {t.id: t.min_fit for t in tracks}
    min_fit_old = {r.track_id: r.min_fit for r in await profile_repo.list_tracks(session, user_id)}
    rows = await jobs_repo.list_jobs(
        session, jobs_repo.JobFilterParams(user_id=user_id, sort="relevance", posted_within="90d")
    )
    old: list[PreviewJob] = []
    new: list[PreviewJob] = []
    for job, _ in rows:
        tier = location_tier(job.location, preference)
        excerpt = excerpt_of(job.jd_text)
        old.append(
            PreviewJob(
                job.id,
                job.company,
                job.title,
                job.location,
                job.best_fit,
                job.posted_at,
                job.discovered_at,
                excerpt,
                tier,
                min_fit_old.get(job.best_track_id) if job.best_track_id else None,
            )
        )
        fit: int | None = None
        floor: int | None = None
        matched: bool | None = None
        if job.jd_embedding is not None:  # no embedding = unscored by design, as in the scorer
            scores = score_job(
                job.title,
                job.jd_text,
                list(job.jd_embedding),
                tracks,
                track_vectors,
                tier,
                has_location_preference=bool(preference.terms),
                role_titles=roles,
            )
            best = best_track(scores, tracks)
            if best is not None:
                fit, floor = best.fit_score, min_fit_new[best.track_id]
                matched = best.title_match is not None if best.blend == "role" else None
        new.append(
            PreviewJob(
                job.id,
                job.company,
                job.title,
                job.location,
                fit,
                job.posted_at,
                job.discovered_at,
                excerpt,
                tier,
                floor,
                matched,
            )
        )
    new_plain = sorted(new, key=lambda j: relevance_key(j, now))
    old_counts, new_counts = _above(old), _above(new)
    matched_titles = Counter(j.title or "-" for j in new if j.matched is True)
    capped_titles = Counter(j.title or "-" for j in new if j.matched is False)
    return UserPreview(
        label=label,
        track_names=tuple(t.name for t in tracks),
        window_jobs=len(rows),
        old_plain=old[:top_n],
        old_arranged=_arranged(old)[:top_n],
        new_plain=new_plain[:top_n],
        new_arranged=_arranged(new_plain)[:top_n],
        above_min_fit={tier: (old_counts[tier], new_counts[tier]) for tier in TIERS},
        matched_titles=matched_titles.most_common(COVERAGE_ROWS),
        capped_titles=capped_titles.most_common(COVERAGE_ROWS),
    )


async def run_rank_preview(
    factory: async_sessionmaker[AsyncSession],
    embedder: EmbeddingProvider,
    key: bytes,
    *,
    top_n: int = 15,
    synthetic_mixed: bool = False,
    now: datetime | None = None,
    expect_database: str | None = None,
) -> list[UserPreview]:
    async with read_only_session(factory) as session:
        if expect_database is not None:
            actual = str((await session.execute(text("SELECT current_database()"))).scalar())
            if actual != expect_database:
                raise DatabaseMismatchError(
                    f"connected to database {actual!r}, expected {expect_database!r}; refusing to run"
                )
        # The database's own clock, so "today" (ordered by SQL now()) and "new" (ordered by
        # relevance_key) see the same instant.
        moment = now or await session.scalar(select(func.now())) or datetime.now(UTC)
        user_ids = await accounts_with_tracks(session)
    previews: list[UserPreview] = []
    mixed_source: tuple[uuid.UUID, list[Track], int] | None = None
    for user_id in user_ids:
        async with read_only_session(factory) as session:
            tracks = [
                track_row_to_model(r) for r in await profile_repo.list_tracks(session, user_id)
            ]
            preview = await preview_tracks(
                session,
                user_id,
                tracks,
                embedder,
                label=pseudonym(user_id, key),
                now=moment,
                top_n=top_n,
            )
        previews.append(preview)
        if any(t.role for t in tracks) and (
            mixed_source is None or preview.window_jobs > mixed_source[2]
        ):
            mixed_source = (user_id, tracks, preview.window_jobs)
    if synthetic_mixed and mixed_source is not None:
        user_id, tracks, _ = mixed_source
        async with read_only_session(factory) as session:
            previews.append(
                await preview_tracks(
                    session,
                    user_id,
                    with_handwritten_track(tracks),
                    embedder,
                    label=SYNTHETIC_LABEL,
                    now=moment,
                    top_n=top_n,
                )
            )
    return previews


def _lines(jobs: list[PreviewJob]) -> list[str]:
    return [
        f"{rank:>2}. {'-' if j.best_fit is None else j.best_fit:>3}  "
        f"{j.company or '-'} | {j.title or '-'} | {j.location or '-'}"
        for rank, j in enumerate(jobs, start=1)
    ]


def render_report(previews: list[UserPreview]) -> str:
    out = [
        "# rank-preview",
        "",
        "Read-only: nothing was written. Today = stored scores ordered as users see them now.",
        "New = the role-first blend computed in memory. 'arrange' = duplicates collapsed and at",
        "most two per company (the code GET /jobs runs). Testers are pseudonyms; no emails.",
        "",
    ]
    for p in previews:
        out += [
            f"## {p.label}",
            f"tracks: {', '.join(p.track_names)}",
            f"jobs in the 90-day window: {p.window_jobs}",
            "",
        ]
        for heading, jobs in (
            ("Today (as users see it)", p.old_plain),
            ("Today + arrange", p.old_arranged),
            ("New scores", p.new_plain),
            ("New scores + arrange (what ships)", p.new_arranged),
        ):
            out += [f"### {heading}", *_lines(jobs), ""]
        out += [
            "### Jobs at or above min_fit by location tier (today -> new)",
            ", ".join(f"{tier} {old}->{new}" for tier, (old, new) in p.above_min_fit.items()),
            "",
            "### Title coverage under the new blend (read the title lists against this)",
            "matched (title, jobs): " + "; ".join(f"{t} x{n}" for t, n in p.matched_titles),
            "capped (title, jobs): " + "; ".join(f"{t} x{n}" for t, n in p.capped_titles),
            "",
        ]
    return "\n".join(out) + "\n"


def write_blind_files(previews: list[UserPreview], directory: Path, *, seed: str) -> None:
    """One `judge-<tester>.md` per tester and one `key.json`.

    The judge sees the de-duplicated UNION of the four lists (today / today + arrange / new /
    new + arrange), each job once, shuffled and numbered, with company, title, location and a JD
    excerpt, and nothing that says which list(s) it came from. `key.json` maps each number back to
    the lists it was in, so every list's relevant-count comes from the same marks
    (`score_judgements`). Never the title lists.
    """
    directory.mkdir(parents=True, exist_ok=True)
    key: dict[str, dict[str, list[str]]] = {}
    for p in previews:
        members: dict[uuid.UUID, tuple[PreviewJob, list[str]]] = {}
        four = (p.old_plain, p.old_arranged, p.new_plain, p.new_arranged)
        for name, jobs in zip(LIST_NAMES, four, strict=True):
            for job in jobs:
                members.setdefault(job.id, (job, []))[1].append(name)
        shuffled = sorted(members.values(), key=lambda pair: pair[0].id.bytes)
        random.Random(f"{seed}:{p.label}").shuffle(shuffled)
        key[p.label] = {str(n): lists for n, (_, lists) in enumerate(shuffled, start=1)}
        lines = [
            f"# Tester {p.label}",
            "",
            f"Target role(s): {', '.join(p.track_names)}",
            "",
            "For each numbered job mark R (a role this person would want) or N (not), judging only from",
            "what is shown. Reply as one line per job: `<number>: R` or `<number>: N`.",
            "",
        ]
        for n, (job, _) in enumerate(shuffled, start=1):
            lines += [
                f"{n}. {job.company or '-'} | {job.title or '-'} | {job.location or '-'}",
                f"   {job.excerpt}",
                "",
            ]
        (directory / f"judge-{p.label}.md").write_text("\n".join(lines), encoding="utf-8")
    (directory / "key.json").write_text(
        json.dumps(key, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def score_judgements(
    key: dict[str, list[str]], marks: dict[str, str]
) -> dict[str, tuple[int, int]]:
    """Per list: (jobs marked R, jobs in the list), from one tester's `key.json` entry and marks.

    Every numbered job must be marked R or N (case-insensitive); anything else raises, so a judge
    that skipped a job cannot silently lower a list's count.
    """
    missing = set(key) - set(marks)
    bad = {n: m for n, m in marks.items() if n in key and m.strip().upper() not in ("R", "N")}
    if missing or bad:
        raise ValueError(f"unmarked jobs {sorted(missing)}, invalid marks {bad}")
    totals: dict[str, list[int]] = {}
    for number, lists in key.items():
        relevant = marks[number].strip().upper() == "R"
        for name in lists:
            pair = totals.setdefault(name, [0, 0])
            pair[0] += int(relevant)
            pair[1] += 1
    return {name: (pair[0], pair[1]) for name, pair in totals.items()}
