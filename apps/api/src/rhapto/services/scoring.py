from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import EMBEDDING_DIMENSIONS, Job
from rhapto.db.models import Track as TrackRow
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.scoring import (
    LocationTier,
    best_track,
    location_preference_from_answers,
    location_tier,
    rationale,
    score_job,
    track_text,
)
from rhapto.models.profile.tracks import Track
from rhapto.services.profile_sync import track_row_to_model

logger = logging.getLogger(__name__)

# Jobs embedded and scored per round trip. One `embed` call over a whole queue is what pushed
# `rescore_jobs` past the worker's 600s job timeout; 50 keeps each call short enough that a
# timeout costs one chunk, not the run.
SCORE_CHUNK = 50


def _fit_dimensions(vector: list[float]) -> list[float] | None:
    return list(vector) if len(vector) == EMBEDDING_DIMENSIONS else None


async def ensure_track_embeddings(
    session: AsyncSession, user_id: uuid.UUID, embedder: EmbeddingProvider
) -> tuple[list[Track], dict[str, list[float]]]:
    rows: list[TrackRow] = await profile_repo.list_tracks(session, user_id)
    missing = [r for r in rows if r.embedding is None]
    if missing:
        vectors = await embedder.embed([track_text(track_row_to_model(r)) for r in missing])
        for row, vector in zip(missing, vectors, strict=True):
            fitted = _fit_dimensions(vector)
            if fitted is None:
                logger.error(
                    "embedding width %d != %d; not caching track %r",
                    len(vector),
                    EMBEDDING_DIMENSIONS,
                    row.track_id,
                )
                continue
            profile_repo.set_track_embedding(row, fitted)
        await session.flush()
    tracks = [track_row_to_model(r) for r in rows]
    vectors_by_id = {r.track_id: list(r.embedding) for r in rows if r.embedding is not None}
    return tracks, vectors_by_id


async def _score_chunk(
    session: AsyncSession,
    user_id: uuid.UUID,
    chunk: list[tuple[Job, LocationTier]],
    tracks: list[Track],
    track_vectors: dict[str, list[float]],
    embedder: EmbeddingProvider,
) -> None:
    unembedded = [job for job, _ in chunk if job.jd_embedding is None]
    if unembedded:
        vectors = await embedder.embed([f"{j.title or ''}\n{j.jd_text}" for j in unembedded])
        for job, vector in zip(unembedded, vectors, strict=True):
            job.jd_embedding = _fit_dimensions(vector)
    for job, tier in chunk:
        if job.jd_embedding is None or not tracks:
            job.best_track_id, job.best_fit = None, None
            continue
        scores = score_job(
            job.title, job.jd_text, list(job.jd_embedding), tracks, track_vectors, tier
        )
        best = best_track(scores, tracks)
        job.best_track_id = best.track_id if best else None
        job.best_fit = best.fit_score if best else None
        await disc_repo.upsert_scores(
            session, user_id, job, [(s.track_id, s.fit_score, rationale(s)) for s in scores]
        )


async def score_and_store(
    session: AsyncSession,
    user_id: uuid.UUID,
    jobs: list[Job],
    embedder: EmbeddingProvider,
    *,
    commit_each_chunk: bool = False,
) -> None:
    """Tier, embed and score `jobs`, in chunks of `SCORE_CHUNK`.

    The chunking is what keeps a whole-queue rescore inside the worker's job timeout: one
    `embed` call over 800 unembedded descriptions runs for minutes and, on timeout, throws all
    of it away. `commit_each_chunk` makes that progress durable and is set by `rescore_user`;
    the poller and `score_jobs` leave it off, because their callers own the transaction.
    """
    if not jobs:
        return
    tracks, track_vectors = await ensure_track_embeddings(session, user_id, embedder)
    # One read of answers.yaml for the whole batch; `rescore_jobs` runs this again whenever the
    # user edits a location answer, so the stored tiers follow the preference.
    preference = location_preference_from_answers(await profile_repo.get_answers(session, user_id))
    # Tiering needs no embedding, so every row gets its tier before the slow part starts: an
    # embedding provider that falls over must not leave the queue with no location data at all.
    tiered = [(job, location_tier(job.location, preference)) for job in jobs]
    for job, tier in tiered:
        job.location_tier = tier
    await session.flush()
    if commit_each_chunk:
        await session.commit()

    total = len(tiered)
    for index, start in enumerate(range(0, total, SCORE_CHUNK), start=1):
        chunk = tiered[start : start + SCORE_CHUNK]
        try:
            await _score_chunk(session, user_id, chunk, tracks, track_vectors, embedder)
        except Exception:
            if not commit_each_chunk:
                # All-or-nothing callers (the poller, score_jobs) own the transaction: let the
                # failure propagate so nothing half-scored is committed by accident.
                raise
            # Incremental mode: one bad chunk costs its own scores, not the whole rescore. Roll
            # back the partial in-memory updates so they cannot ride along with the next chunk's
            # commit; the tiers were committed above and survive.
            await session.rollback()
            logger.exception(
                "scoring chunk %d failed for user %s; %d job(s) keep their previous scores",
                index,
                user_id,
                len(chunk),
            )
            continue
        await session.flush()
        if commit_each_chunk:
            await session.commit()
        logger.info(
            "scored %d/%d job(s) for user %s", min(start + SCORE_CHUNK, total), total, user_id
        )


async def users_needing_location_backfill(session: AsyncSession) -> list[uuid.UUID]:
    """Users with at least one job scored before location priority existed.

    Their `best_fit` was never multiplied, so they out-rank every newly scored job until
    something happens to enqueue a rescore — and a user who edits nothing never gets one.
    """
    rows = await session.scalars(
        select(Job.user_id).where(Job.location_tier.is_(None)).distinct().order_by(Job.user_id)
    )
    return list(rows)


async def rescore_user(
    session: AsyncSession, user_id: uuid.UUID, embedder: EmbeddingProvider
) -> int:
    for row in await profile_repo.list_tracks(session, user_id):
        row.embedding = None  # descriptions may have changed; recompute every track
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user_id)))
    # A whole queue can be hundreds of jobs; commit per chunk so a timeout leaves the work done
    # so far on disk instead of starting over on the next attempt.
    await score_and_store(session, user_id, jobs, embedder, commit_each_chunk=True)
    return len(jobs)
