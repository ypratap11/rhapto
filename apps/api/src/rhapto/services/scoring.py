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
from rhapto.engine.scoring import best_track, rationale, score_job, track_text
from rhapto.models.profile.tracks import Track
from rhapto.services.profile_sync import track_row_to_model

logger = logging.getLogger(__name__)


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


async def score_and_store(
    session: AsyncSession, user_id: uuid.UUID, jobs: list[Job], embedder: EmbeddingProvider
) -> None:
    if not jobs:
        return
    tracks, track_vectors = await ensure_track_embeddings(session, user_id, embedder)
    unembedded = [j for j in jobs if j.jd_embedding is None]
    if unembedded:
        vectors = await embedder.embed([f"{j.title or ''}\n{j.jd_text}" for j in unembedded])
        for job, vector in zip(unembedded, vectors, strict=True):
            job.jd_embedding = _fit_dimensions(vector)
    for job in jobs:
        if job.jd_embedding is None or not tracks:
            job.best_track_id, job.best_fit = None, None
            continue
        scores = score_job(job.title, job.jd_text, list(job.jd_embedding), tracks, track_vectors)
        best = best_track(scores, tracks)
        job.best_track_id = best.track_id if best else None
        job.best_fit = best.fit_score if best else None
        await disc_repo.upsert_scores(
            session, user_id, job, [(s.track_id, s.fit_score, rationale(s)) for s in scores]
        )
    await session.flush()


async def rescore_user(
    session: AsyncSession, user_id: uuid.UUID, embedder: EmbeddingProvider
) -> int:
    for row in await profile_repo.list_tracks(session, user_id):
        row.embedding = None  # descriptions may have changed; recompute every track
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user_id)))
    await score_and_store(session, user_id, jobs, embedder)
    return len(jobs)
