"""The five numbers the Dashboard reports, one aggregate query each.

Everything here is deliberately a single statement per answer. The dashboard is the first screen
a user sees on every visit; doing it with per-row follow-ups would make the landing page the
slowest thing in the product.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import (
    APPLIED_STATUSES,
    Aggregator,
    Answers,
    Application,
    Guardrail,
    Job,
    Package,
    ResumeBlock,
    ResumeDocumentRow,
    SearchRow,
    SourceCredentialRow,
    Track,
    User,
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
    # --- the setup checks, all computed; no migration ---
    #: At least one job that is neither hidden nor retired. `EXISTS`, not `COUNT`: see `checklist`.
    jobs_found: bool = False
    #: Blocks with no usable period. Counted, because the row's job is "N need a period".
    dateless_blocks: int = 0
    #: Saved searches with `active = true` -- the only ones `poller.build_specs` runs.
    active_searches: int = 0
    #: This user's consumed trial runs, selected here so `llm_setup_status` does not need its own
    #: statement on the dashboard's hot path.
    trial_runs_used: int = 0


@dataclass(frozen=True)
class SourceSetup:
    """One `aggregators` row plus whether credentials exist for it."""

    source: str
    enabled: bool
    key_set: bool


async def source_setup(session: AsyncSession, user_id: uuid.UUID) -> dict[str, SourceSetup]:
    """This user's configured sources and whether each has stored credentials, in one statement.

    A LEFT JOIN from `aggregators`, so a `source_credentials` row with no `aggregators` row behind it
    is absent -- which is correct rather than lossy: `usable_source_ids` requires the `aggregators`
    row to exist before it looks at credentials at all, because the poller does.
    """
    rows = await session.execute(
        select(Aggregator.source, Aggregator.enabled, SourceCredentialRow.id)
        .outerjoin(
            SourceCredentialRow,
            and_(
                SourceCredentialRow.user_id == Aggregator.user_id,
                SourceCredentialRow.source == Aggregator.source,
            ),
        )
        .where(Aggregator.user_id == user_id)
    )
    return {
        source: SourceSetup(source=source, enabled=bool(enabled), key_set=credential_id is not None)
        for source, enabled, credential_id in rows.all()
    }


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
        .outerjoin(
            Application,
            and_(Application.job_id == Package.job_id, Application.user_id == user_id),
        )
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
    """The six profile-setup tests from spec §7, the verified-block tally, and the setup counts.

    Still two statements: one row of counts and existence flags, and one read of the answers JSON,
    which has to come back whole because the two answer rows test different keys. The four setup
    values added here are scalar subqueries on the existing composite, not new statements.

    `jobs_found` is `EXISTS`, not `COUNT`, and that is why no job count is exposed on the checklist:
    a `COUNT(*)` over a user's jobs is fine at a couple of thousand rows and is a per-user scan at a
    million. `EXISTS` stops at the first row forever. The number the user wants lives on the Jobs
    page, which is the surface that can also explain it.

    `jobs_found` deliberately ignores the grid's default 90-day window. A corpus entirely older than
    90 days reads `jobs_found = true` while the default grid is empty -- and that case is answered
    correctly and specifically by `GET /jobs/empty-reason`, which names `posted_within` and offers a
    one-click widen. Folding a UI default into a setup check would give two mechanisms one concern.
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
                # A job the user hid or a source retired is not a job that "arrived": the default
                # grid shows neither, so counting them would report the step done over an empty grid.
                select(
                    exists().where(
                        Job.user_id == user_id,
                        Job.hidden_at.is_(None),
                        Job.unlisted_at.is_(None),
                    )
                ).scalar_subquery(),
                # `btrim(period) = ''` as well as NULL: `resume_blocks.period` is nullable free text
                # (String(50)), and while the `Block.period` regex cannot admit "" through
                # `PUT /profile/blocks/{id}`, nothing constrains a row written by an older import or
                # by hand. A blank period is as dateless as a missing one.
                select(func.count(ResumeBlock.id))
                .where(
                    ResumeBlock.user_id == user_id,
                    or_(
                        ResumeBlock.period.is_(None),
                        func.btrim(ResumeBlock.period) == "",
                    ),
                )
                .scalar_subquery(),
                # Only `active` searches: `build_specs` filters on exactly this flag, so an
                # all-inactive set polls nothing while a bare `count(searches) > 0` would read done.
                select(func.count(SearchRow.id))
                .where(SearchRow.user_id == user_id, SearchRow.active.is_(True))
                .scalar_subquery(),
                select(User.trial_runs_used).where(User.id == user_id).scalar_subquery(),
            )
        )
    ).one()
    (
        documents,
        tracks,
        guardrails,
        total_blocks,
        verified_blocks,
        has_usable_jobs,
        dateless_blocks,
        active_searches,
        trial_runs_used_count,
    ) = row
    answers_row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    answers = dict(answers_row.answers_json) if answers_row is not None else {}
    return Checklist(
        resume_template=int(documents or 0) > 0,
        contact_answers=all((answers.get(k) or "").strip() for k in CONTACT_KEYS),
        tracks=int(tracks or 0) > 0,
        blocks_verified=int(verified_blocks or 0) > 0,
        guardrails=int(guardrails or 0) > 0,
        location_preferences=all((answers.get(k) or "").strip() for k in LOCATION_KEYS),
        verified_blocks=int(verified_blocks or 0),
        total_blocks=int(total_blocks or 0),
        jobs_found=bool(has_usable_jobs),
        dateless_blocks=int(dateless_blocks or 0),
        active_searches=int(active_searches or 0),
        trial_runs_used=int(trial_runs_used_count or 0),
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
