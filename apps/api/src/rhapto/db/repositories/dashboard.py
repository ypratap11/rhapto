"""The five numbers the Dashboard reports, one aggregate query each.

Everything here is deliberately a single statement per answer. The dashboard is the first screen
a user sees on every visit; doing it with per-row follow-ups would make the landing page the
slowest thing in the product.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import (
    APPLIED_STATUSES,
    Answers,
    Application,
    Guardrail,
    Job,
    Package,
    ResumeBlock,
    ResumeDocumentRow,
    Track,
)

#: How long a job counts as "new" on the dashboard.
NEW_WINDOW_DAYS = 7

#: answers.yaml keys the checklist's two rows require, per spec §7.
CONTACT_KEYS = ("name", "email", "phone", "location", "links")
LOCATION_KEYS = ("location_home", "location_preferred", "remote_ok")


@dataclass(frozen=True)
class Checklist:
    resume_template: bool
    contact_answers: bool
    tracks: bool
    blocks_verified: bool
    guardrails: bool
    location_preferences: bool
    verified_blocks: int
    total_blocks: int


async def new_fit_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Jobs found in the last week that clear their own track's threshold and are still live."""
    cutoff = datetime.now(UTC) - timedelta(days=NEW_WINDOW_DAYS)
    tracks = select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()
    # A job whose track was renamed or deleted outer-joins to NULL; coalescing above any real
    # threshold (0-100) keeps the comparison a definite boolean instead of NULL, so such a job
    # counts as not-a-fit rather than silently counting as one.
    threshold = func.coalesce(tracks.c.min_fit, 101)
    count = await session.scalar(
        select(func.count(Job.id))
        .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
        .where(
            Job.user_id == user_id,
            Job.hidden_at.is_(None),
            Job.unlisted_at.is_(None),
            Job.discovered_at >= cutoff,
            Job.best_fit.is_not(None),
            Job.best_fit >= threshold,
        )
    )
    return int(count or 0)


async def needs_review_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Latest drafts waiting for a human, on jobs that are still in the flow."""
    latest = (
        select(Package.job_id, func.max(Package.version).label("version"))
        .where(Package.user_id == user_id)
        .group_by(Package.job_id)
        .subquery()
    )
    count = await session.scalar(
        select(func.count(Package.id))
        .join(latest, and_(Package.job_id == latest.c.job_id, Package.version == latest.c.version))
        .join(Job, Job.id == Package.job_id)
        .outerjoin(Application, Application.job_id == Package.job_id)
        .where(
            Package.user_id == user_id,
            # Exactly "draft": a ready package has been reviewed (the human pressed Mark ready)
            # and a blocked one cannot be reviewed into shape without a regenerate.
            Package.status == "draft",
            Package.archived_at.is_(None),
            Job.hidden_at.is_(None),
            Job.unlisted_at.is_(None),
            or_(Application.id.is_(None), Application.status.not_in(APPLIED_STATUSES)),
        )
    )
    return int(count or 0)


async def checklist(session: AsyncSession, user_id: uuid.UUID) -> Checklist:
    """The six profile-setup tests from spec §7, plus the verified-block tally.

    Two statements: one row of counts and existence flags, and one read of the answers JSON,
    which has to come back whole because the two answer rows test different keys.
    """
    row = (
        await session.execute(
            select(
                select(func.count(ResumeDocumentRow.id))
                .where(ResumeDocumentRow.user_id == user_id)
                .scalar_subquery(),
                select(func.count(Track.id)).where(Track.user_id == user_id).scalar_subquery(),
                select(func.count(Guardrail.id))
                .where(Guardrail.user_id == user_id, Guardrail.active.is_(True))
                .scalar_subquery(),
                select(func.count(ResumeBlock.id))
                .where(ResumeBlock.user_id == user_id)
                .scalar_subquery(),
                select(func.count(ResumeBlock.id))
                .where(ResumeBlock.user_id == user_id, ResumeBlock.verified.is_(True))
                .scalar_subquery(),
            )
        )
    ).one()
    documents, tracks, guardrails, total_blocks, verified_blocks = (int(v or 0) for v in row)
    answers_row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    answers = dict(answers_row.answers_json) if answers_row is not None else {}
    return Checklist(
        resume_template=documents > 0,
        contact_answers=all((answers.get(k) or "").strip() for k in CONTACT_KEYS),
        tracks=tracks > 0,
        blocks_verified=verified_blocks > 0,
        guardrails=guardrails > 0,
        location_preferences=all((answers.get(k) or "").strip() for k in LOCATION_KEYS),
        verified_blocks=verified_blocks,
        total_blocks=total_blocks,
    )


async def due_followups(session: AsyncSession, user_id: uuid.UUID) -> list[tuple[Application, Job]]:
    """Follow-ups dated today or earlier, soonest first, on applications still open."""
    now = datetime.now(UTC)
    rows = await session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.user_id == user_id,
            Application.follow_up_at.is_not(None),
            Application.follow_up_at <= now,
            Application.status != "closed",
        )
        .order_by(Application.follow_up_at, Application.id)
    )
    return [(application, job) for application, job in rows.all()]
