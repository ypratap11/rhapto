from __future__ import annotations

import logging
import uuid
from collections.abc import Mapping

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import EMBEDDING_DIMENSIONS, Job, JobScore
from rhapto.db.models import Track as TrackRow
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.scoring import (
    LocationTier,
    RoleTitles,
    best_track,
    location_preference_from_answers,
    location_tier,
    rationale,
    score_job,
    track_text,
)
from rhapto.models.profile.tracks import Track
from rhapto.services.profile_sync import track_row_to_model
from rhapto.services.taxonomy import TaxonomyError, find_role

logger = logging.getLogger(__name__)

# Jobs embedded and scored per round trip. One `embed` call over a whole queue is what pushed
# `rescore_jobs` past the worker's 600s job timeout; 50 keeps each call short enough that a
# timeout costs one chunk, not the run.
SCORE_CHUNK = 50


def _fit_dimensions(vector: list[float]) -> list[float] | None:
    return list(vector) if len(vector) == EMBEDDING_DIMENSIONS else None


def role_titles_for(tracks: list[Track]) -> dict[str, RoleTitles]:
    """The title phrases for each track that can use the role-first blend, keyed by track id.

    A track is included only when it has a `field` and a `role`, `find_role` still finds that role
    (a role id removed from the taxonomy after the row was written falls back), and the role has
    non-empty `titles`. A `TaxonomyError` (missing or invalid file, or a custom taxonomy that
    cannot load) is logged ONCE for the run and every track falls back to today's blend -- it never
    stops scoring. Called once per `score_and_store`, so "once" is once per run.
    """
    resolved: dict[str, RoleTitles] = {}
    try:
        for track in tracks:
            if not track.field or not track.role:
                continue
            role = find_role(track.field, track.role)
            if role is None or not role.titles:
                continue
            resolved[track.id] = RoleTitles(
                titles=tuple(role.titles), exclude=tuple(role.exclude_titles)
            )
    except TaxonomyError:
        logger.exception(
            "taxonomy unavailable; every track falls back to the legacy blend for this run"
        )
        return {}
    return resolved


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
    *,
    has_location_preference: bool,
    role_titles: Mapping[str, RoleTitles],
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
            job.title,
            job.jd_text,
            list(job.jd_embedding),
            tracks,
            track_vectors,
            tier,
            has_location_preference=has_location_preference,
            role_titles=role_titles,
        )
        best = best_track(scores, tracks)
        job.best_track_id = best.track_id if best else None
        job.best_fit = best.fit_score if best else None
        await disc_repo.upsert_scores(
            session, user_id, job, [(s.track_id, s.fit_score, rationale(s)) for s in scores]
        )


async def _reload_jobs(session: AsyncSession, job_ids: list[uuid.UUID]) -> None:
    """Refresh `job_ids` from the database into the session's identity map.

    `session.rollback()` expires every loaded instance. Reading even a plain column of an expired
    `Job` is an implicit lazy load, which raises `MissingGreenlet` in an `AsyncSession`, so after a
    failed chunk the next chunk's `job.jd_embedding` read failed too -- and so did every chunk
    after it. `populate_existing` reloads the rows the chunk is about to use; `scalars(...)` is
    consumed so the instances really are populated before the chunk runs.
    """
    if not job_ids:
        return
    stmt = select(Job).where(Job.id.in_(job_ids)).execution_options(populate_existing=True)
    list(await session.scalars(stmt))


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
    role_titles = role_titles_for(tracks)
    # Tiering needs no embedding, so every row gets its tier before the slow part starts: an
    # embedding provider that falls over must not leave the queue with no location data at all.
    tiered = [(job, location_tier(job.location, preference)) for job in jobs]
    for job, tier in tiered:
        job.location_tier = tier
    await session.flush()
    if commit_each_chunk:
        await session.commit()

    total = len(tiered)
    # Primary keys captured NOW, before any rollback can expire the instances: after one, even
    # `job.id` would be a lazy load.
    job_ids = [job.id for job, _ in tiered]
    rolled_back = False
    for index, start in enumerate(range(0, total, SCORE_CHUNK), start=1):
        chunk = tiered[start : start + SCORE_CHUNK]
        if rolled_back:
            # An earlier chunk failed and rolled back, which expired every instance in the session,
            # this chunk's included. Reload them before reading any attribute.
            await _reload_jobs(session, job_ids[start : start + SCORE_CHUNK])
        try:
            await _score_chunk(
                session,
                user_id,
                chunk,
                tracks,
                track_vectors,
                embedder,
                has_location_preference=bool(preference.terms),
                role_titles=role_titles,
            )
        except Exception:
            if not commit_each_chunk:
                # All-or-nothing callers (the poller, score_jobs) own the transaction: let the
                # failure propagate so nothing half-scored is committed by accident.
                raise
            # Incremental mode: one bad chunk costs its own scores, not the whole rescore. Roll
            # back the partial in-memory updates so they cannot ride along with the next chunk's
            # commit; the tiers were committed above and survive.
            await session.rollback()
            rolled_back = True
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


async def rescore_user(
    session: AsyncSession, user_id: uuid.UUID, embedder: EmbeddingProvider
) -> int:
    # Database time, read BEFORE the tracks are loaded and from the same clock as
    # `tracks.score_requested_at`: a track saved after this instant is never marked by this run.
    started = (await session.execute(select(func.now()))).scalar_one()
    rows = await profile_repo.list_tracks(session, user_id)
    loaded_ids = [r.track_id for r in rows]  # exactly the set this run scores
    # Scores of tracks that no longer exist are never rewritten by an upsert; drop them here so a
    # deleted track (or a rescore that raced its delete) cannot leave rows behind. With no tracks
    # left `not_in([])` matches every row of the user, which is what is wanted.
    await session.execute(
        delete(JobScore).where(
            JobScore.user_id == user_id, JobScore.track_id.not_in([r.track_id for r in rows])
        )
    )
    for row in rows:
        row.embedding = None  # descriptions may have changed; recompute every track
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user_id)))
    # A whole queue can be hundreds of jobs; commit per chunk so a timeout leaves the work done
    # so far on disk instead of starting over on the next attempt.
    await score_and_store(session, user_id, jobs, embedder, commit_each_chunk=True)
    # Only reached if score_and_store returned: a run that raised marks nothing. A chunk that
    # failed inside it was logged and skipped, so the run still counts as finished. The caller
    # (`rescore_jobs`) commits this UPDATE.
    await profile_repo.mark_tracks_scored(session, user_id, loaded_ids, started)
    return len(jobs)
