from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import (
    CursorResult,
    and_,
    delete,
    func,
    not_,
    nulls_last,
    or_,
    select,
    text,
    true,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.selectable import Subquery

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Application, Job, Package, SearchRow, Track

compute_dedupe_hash = dedupe_hash


async def create_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    jd_text: str,
    source: str = "manual",
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    url: str | None = None,
) -> Job:
    job = Job(
        user_id=user_id,
        source=source,
        company=company,
        title=title,
        location=location,
        url=url,
        jd_text=jd_text,
        dedupe_hash=compute_dedupe_hash(jd_text),
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


#: Matches `services.discovery.poller.INGEST_MAX_AGE_DAYS` -- a public posting older than this is
#: not worth seeding a first screen with, for the same reason the poller doesn't ingest it fresh.
PUBLIC_BACKFILL_MAX_AGE_DAYS = 90


async def backfill_public_jobs(
    session: AsyncSession, user_id: uuid.UUID, *, public_sources: Sequence[str]
) -> int:
    """Seed a brand-new account's first screen with every live public-source job already
    discovered on this instance, cached embedding included, at zero LLM/embedding cost.

    `public_sources` is supplied by the caller as `list(SOURCES.keys())` -- this module takes no
    import on `rhapto.services.discovery.sources`, whose `__init__.py` imports eleven concrete
    source modules purely for `@register` side effects (plan-review I10); the positive allowlist
    is still enforced, just constructed one layer up.

    Does not copy: extracted_json (another user's ungoverned LLM output), repost_of/search_id
    (foreign keys into another user's own rows), best_fit/best_track_id/location_tier/hidden_at/
    rescued (another user's opinions, meaningless for a new account).

    Idempotent three ways, none of them optional (plan-review C5 -- the reviewer's ruling was that
    these are not alternatives to each other):
    1. The inner `DISTINCT ON (source, COALESCE(external_id, dedupe_hash))` collapses by *source
       identity* first, not by text hash -- two rows for the same (source, external_id) whose JD
       text changed between polls (and therefore have different dedupe_hash values) collapse to
       one, rather than both surviving and violating `uq_jobs_user_source_external`
       (`(user_id, source, external_id) WHERE external_id IS NOT NULL`,
       `alembic/versions/0002_discovery.py:33-40`) the moment both are inserted for the new user.
    2. `NOT EXISTS` guards both `(user_id, dedupe_hash)` and `(user_id, source, external_id)`, so a
       retried call -- or a second call whose source data has since changed hash -- inserts nothing
       already present under either key.
    3. A bare `ON CONFLICT DO NOTHING` (no target needed) is the last-resort guard against two
       concurrent callers both passing the `NOT EXISTS` checks before either commits -- the
       classic idempotency race a `NOT EXISTS` clause alone cannot close.

    The age cutoff reads `COALESCE(posted_at, discovered_at)`, not `posted_at` alone (plan-review
    M4): a dateless posting has no evidence of its own age, and the copy stamps `discovered_at =
    now()` on the new row, so admitting it unconditionally would let a two-year-old dateless
    posting seed the first screen and then read as fresh under `posted_within=24h` -- the same
    coalesce `list_jobs` already judges recency by.
    """
    if not public_sources:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=PUBLIC_BACKFILL_MAX_AGE_DAYS)
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            text(
                """
                INSERT INTO jobs (
                    id, user_id, source, external_id, url, company, title, location,
                    posted_at, salary_text, jd_text, jd_embedding, dedupe_hash, identity_hash,
                    discovered_at, miss_count, created_at, updated_at
                )
                SELECT gen_random_uuid(), :user_id, j.source, j.external_id, j.url, j.company,
                       j.title, j.location, j.posted_at, j.salary_text, j.jd_text,
                       j.jd_embedding, j.dedupe_hash, j.identity_hash, now(), 0, now(), now()
                FROM (
                    SELECT DISTINCT ON (source, COALESCE(external_id, dedupe_hash)) *
                    FROM jobs
                    WHERE source = ANY(:public_sources)
                      AND unlisted_at IS NULL
                      AND COALESCE(posted_at, discovered_at) > :cutoff
                    ORDER BY source, COALESCE(external_id, dedupe_hash), discovered_at ASC
                ) j
                WHERE NOT EXISTS (
                    SELECT 1 FROM jobs existing
                    WHERE existing.user_id = :user_id AND existing.dedupe_hash = j.dedupe_hash
                )
                AND NOT EXISTS (
                    SELECT 1 FROM jobs existing2
                    WHERE existing2.user_id = :user_id AND existing2.source = j.source
                      AND j.external_id IS NOT NULL AND existing2.external_id = j.external_id
                )
                ON CONFLICT DO NOTHING
                """
            ),
            {"user_id": str(user_id), "public_sources": list(public_sources), "cutoff": cutoff},
        ),
    )
    return result.rowcount or 0


async def find_duplicate(
    session: AsyncSession, user_id: uuid.UUID, dedupe_hash_value: str
) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(Job.user_id == user_id, Job.dedupe_hash == dedupe_hash_value)
    )
    return result


#: How far back each `posted_within` value reaches.
POSTED_WITHIN_DAYS = {"24h": 1, "7d": 7, "30d": 30, "90d": 90}

#: `sort="relevance"` subtracts this many fit points per day of age, capped. 0.2/day over a 90-day
#: cap costs an old posting at most 18 points -- enough that a fresh 60 outranks a stale 70, and
#: small enough that a genuinely strong old match is not buried by a weak new one. The cap matters:
#: without it the oldest rows sort below jobs with no score at all.
RECENCY_DECAY = 0.2
RECENCY_DECAY_CAP_DAYS = 90.0


@dataclass(frozen=True)
class JobFilterParams:
    """Every input `GET /api/v1/jobs` narrows its result by, as one object.

    One object rather than fourteen keyword arguments so that `GET /jobs` and
    `GET /jobs/empty-reason` cannot be given different inputs: both resolve the same
    `Depends(job_filters)`, so a parameter that exists on one exists on the other by construction.

    Defaults are the *repository's* historical defaults, not the router's -- `sort="fit"` and
    `posted_within="any"` -- because the live-search refetch (`routers/search.py`) relies on them.
    The router passes its own `Query(...)` defaults explicitly.

    `user_id`, `hidden` and `sort` are the three fields with no one-to-one registry entry, and
    `test_job_filter_registry.py` excludes exactly those three by name:
    `user_id` is the base tenancy predicate (never removable, see `list_jobs`), `hidden` is a mode
    switch whose registry entry is always active, and `sort` is not a filter at all.
    """

    user_id: uuid.UUID
    search: str | None = None
    track: str | None = None
    bucket: str | None = None
    region: str = "any"
    sort: str = "fit"
    ids: tuple[uuid.UUID, ...] | None = None
    hidden: bool = False
    search_id: uuid.UUID | None = None
    posted_within: str = "any"
    sources: tuple[str, ...] | None = None
    field: str | None = None
    recommended: bool = False


@dataclass(frozen=True)
class FilterCtx:
    """What a filter clause needs that is not a request parameter.

    `min_fit` is a column over whichever `tracks` subquery the enclosing statement joined, so a
    `FilterCtx` can only be built by the code that owns that statement -- see `filter_context`.
    """

    #: `params.field` resolved to this user's track ids. `None` when no field was requested; an
    #: EMPTY tuple means "the user has no track in that field", which is an empty result rather
    #: than "no filter" -- the distinction `GET /jobs/empty-reason` reports as
    #: `cause = "field_without_tracks"`.
    track_ids: tuple[str, ...] | None
    #: The per-track fit threshold, coalesced above any real min_fit (0-100). `best_track_id` has
    #: no FK, so a scored job whose track was deleted or renamed outer-joins to a NULL min_fit;
    #: coalescing keeps the comparison a definite boolean, so an orphaned track counts as low fit
    #: instead of silently vanishing from both buckets.
    min_fit: ColumnElement[int]


def _tracks_subquery(user_id: uuid.UUID) -> Subquery:
    return select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()


def filter_context(
    user_id: uuid.UUID, track_ids: tuple[str, ...] | None
) -> tuple[Subquery, FilterCtx]:
    """The `tracks` subquery a statement must join, and the `FilterCtx` built over it.

    Returned as a pair because the caller has to join the subquery itself; handing back a
    `FilterCtx` whose `min_fit` referenced a subquery the statement never joined would compile to
    a cartesian product.
    """
    tracks = _tracks_subquery(user_id)
    return tracks, FilterCtx(track_ids=track_ids, min_fit=func.coalesce(tracks.c.min_fit, 101))


@dataclass(frozen=True)
class TrackFields:
    """One read of this user's tracks, answering both questions the Field filter raises."""

    #: Track ids in the requested field. `None` when no field was requested; an EMPTY tuple means
    #: the user has no track in that field, which is an empty result rather than "no filter".
    track_ids: tuple[str, ...] | None
    #: Every taxonomy field this user actually has a track in, in a stable order. What the
    #: field-without-tracks explanation names instead of the field the user asked for.
    user_fields: tuple[str, ...]


async def field_tracks(session: AsyncSession, user_id: uuid.UUID, field: str | None) -> TrackFields:
    """Resolve `field` against this user's tracks, and list the fields they do have.

    One function rather than one per caller so `list_jobs` and the empty-reason diagnosis decide
    "the user has no track in that field" the same way. A second resolution is a second place that
    verdict could differ, and the disagreement would be invisible -- the listing would return
    nothing while the explanation said the filter was fine.
    """
    rows = list(await session.scalars(select(Track).where(Track.user_id == user_id)))
    return TrackFields(
        track_ids=None if field is None else tuple(t.track_id for t in rows if t.field == field),
        user_fields=tuple(sorted({t.field for t in rows if t.field})),
    )


def _fit_condition(ctx: FilterCtx) -> ColumnElement[bool]:
    return or_(Job.rescued.is_(True), and_(Job.best_fit.is_not(None), Job.best_fit >= ctx.min_fit))


def _posted_cutoff(posted_within: str) -> datetime | None:
    days = POSTED_WITHIN_DAYS.get(posted_within)
    return None if days is None else datetime.now(UTC) - timedelta(days=days)


def _search_clause(term: str) -> ColumnElement[bool]:
    # Escape LIKE metacharacters so a search for "100%" is a literal, not a wildcard.
    escaped = term.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return or_(
        Job.company.ilike(pattern, escape="\\"),
        Job.title.ilike(pattern, escape="\\"),
        Job.jd_text.ilike(pattern, escape="\\"),
    )


#: `recommended=true` drops scored jobs at or below this fit: with the role-first blend a job whose
#: title is not the user's role is capped at 45 (`engine.scoring.TITLE_MISS_CAP`). `db/` may not
#: import `engine/` (import-linter), so the value is repeated here; `tests/unit/test_ranking.py::
#: test_recommended_floor_matches_the_title_miss_cap` fails if the two drift. Unscored jobs stay.
RECOMMENDED_FIT_FLOOR = 45


def _recommended_clause(user_id: uuid.UUID) -> ColumnElement[bool]:
    has_package = select(Package.id).where(Package.user_id == user_id, Package.job_id == Job.id)
    has_application = select(Application.id).where(
        Application.user_id == user_id, Application.job_id == Job.id
    )
    return and_(
        Job.unlisted_at.is_(None),
        ~has_package.exists(),
        ~has_application.exists(),
        or_(Job.best_fit.is_(None), Job.best_fit > RECOMMENDED_FIT_FLOOR),
    )


#: `location_tier` is NULL on rows scored before location priority shipped and on rows the scorer
#: has not reached; those read as "unknown", so they stay visible under "us" and only the
#: deliberately narrow "preferred" filter hides them.
def _tier() -> ColumnElement[str]:
    return func.coalesce(Job.location_tier, "unknown")


US_TIERS = ("preferred", "remote", "country", "unknown")


@dataclass(frozen=True)
class JobFilter:
    """One predicate `GET /jobs` narrows by, defined once and consumed twice.

    `list_jobs` builds its WHERE clause from this registry and `GET /jobs/empty-reason` blames one
    of these entries by re-running the same `clause` with one entry left out. There is therefore
    exactly one definition of "which jobs does this filter exclude", which is the whole point: two
    implementations of it would disagree, and the disagreement would be invisible.
    """

    #: Also the wire value of `JobsEmptyReasonOut.filter_id` for every blamable entry.
    id: str
    #: Is this filter narrowing anything right now? An inactive filter is neither applied nor blamed.
    active: Callable[[JobFilterParams], bool]
    clause: Callable[[JobFilterParams, FilterCtx], ColumnElement[bool]]
    #: False for `ids`, which is a refetch-by-id mechanism, not a filter a user chose: it is applied
    #: like any other entry but never blamed, and so is deliberately absent from `JobFilterId`.
    blamable: bool = True
    #: The filter's current value, rendered for the explanation sentence.
    value: Callable[[JobFilterParams], str | None] = dataclass_field(
        default=lambda _p: None, repr=False
    )


JOB_FILTERS: tuple[JobFilter, ...] = (
    JobFilter(
        id="ids",
        active=lambda p: p.ids is not None,
        clause=lambda p, _c: Job.id.in_(p.ids or ()),
        blamable=False,
    ),
    # `hidden` is a switch, not a filter that can be off: the grid's default view must not show
    # jobs the user said no to, and "Show hidden" wants exactly those and nothing else. It is
    # therefore ALWAYS active -- which is also why the registry-coverage test excludes it.
    JobFilter(
        id="hidden",
        active=lambda _p: True,
        clause=lambda p, _c: Job.hidden_at.is_not(None) if p.hidden else Job.hidden_at.is_(None),
        value=lambda p: "true" if p.hidden else "false",
    ),
    JobFilter(
        id="search_id",
        active=lambda p: p.search_id is not None,
        clause=lambda p, _c: Job.search_id == p.search_id,
        value=lambda p: str(p.search_id) if p.search_id else None,
    ),
    JobFilter(
        id="sources",
        active=lambda p: bool(p.sources),
        clause=lambda p, _c: Job.source.in_(p.sources or ()),
        value=lambda p: ", ".join(p.sources) if p.sources else None,
    ),
    JobFilter(
        id="field",
        active=lambda p: p.field is not None,
        # `ctx.track_ids` may be empty, which compiles to `best_track_id IN ()` -- an empty result.
        clause=lambda _p, c: Job.best_track_id.in_(c.track_ids or ()),
        value=lambda p: p.field,
    ),
    # A posting with no date from the source is judged by when Rhapto first saw it, which is the
    # only honest answer available.
    JobFilter(
        id="posted_within",
        active=lambda p: p.posted_within in POSTED_WITHIN_DAYS,
        clause=lambda p, _c: (
            func.coalesce(Job.posted_at, Job.discovered_at) >= _posted_cutoff(p.posted_within)
        ),
        value=lambda p: p.posted_within,
    ),
    JobFilter(
        id="recommended",
        active=lambda p: p.recommended,
        clause=lambda p, _c: _recommended_clause(p.user_id),
        value=lambda p: "true" if p.recommended else None,
    ),
    JobFilter(
        id="search",
        active=lambda p: bool(p.search),
        clause=lambda p, _c: _search_clause(p.search or ""),
        value=lambda p: p.search,
    ),
    JobFilter(
        id="track",
        active=lambda p: bool(p.track),
        clause=lambda p, _c: Job.best_track_id == p.track,
        value=lambda p: p.track,
    ),
    JobFilter(
        id="region",
        active=lambda p: p.region in ("preferred", "us"),
        clause=lambda p, _c: (
            _tier() == "preferred" if p.region == "preferred" else _tier().in_(US_TIERS)
        ),
        value=lambda p: p.region,
    ),
    JobFilter(
        id="bucket",
        # unscored jobs stay visible in the "fit" bucket
        active=lambda p: p.bucket in ("fit", "low"),
        clause=lambda p, c: (
            or_(Job.best_fit.is_(None), _fit_condition(c))
            if p.bucket == "fit"
            else and_(Job.best_fit.is_not(None), not_(_fit_condition(c)))
        ),
        value=lambda p: p.bucket,
    ),
)

#: By id, for the diagnosis's leave-one-out pass.
JOB_FILTERS_BY_ID = {f.id: f for f in JOB_FILTERS}


def active_filters(params: JobFilterParams) -> tuple[JobFilter, ...]:
    """Every registry entry that is narrowing the result right now, in registry order."""
    return tuple(f for f in JOB_FILTERS if f.active(params))


def active_clauses(
    params: JobFilterParams, ctx: FilterCtx, *, without: str | None = None
) -> list[ColumnElement[bool]]:
    """The WHERE terms for the active filters, optionally leaving one out by id.

    `without` is what makes the diagnosis a leave-one-out over the *same* predicates the listing
    applies, rather than a second implementation of them.
    """
    return [f.clause(params, ctx) for f in active_filters(params) if f.id != without]


async def list_jobs(session: AsyncSession, params: JobFilterParams) -> list[tuple[Job, str | None]]:
    resolved = await field_tracks(session, params.user_id, params.field)
    tracks, ctx = filter_context(params.user_id, resolved.track_ids)
    query = (
        select(Job, SearchRow.name)
        .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
        .outerjoin(SearchRow, SearchRow.id == Job.search_id)
        # Tenancy is a base predicate, applied here and not as a registry entry, so no
        # leave-one-out in `empty-reason` can ever remove it.
        .where(Job.user_id == params.user_id)
    )
    # The one and only place this function narrows by a user-chosen filter. Every predicate comes
    # from JOB_FILTERS; adding an `if x: query = query.where(...)` back here is what condition C2
    # forbids, because the diagnosis would not know about it.
    query = query.where(*active_clauses(params, ctx))
    if params.sort == "relevance":
        # Fit and recency together, because either alone is wrong: sorting by fit buries a strong
        # match posted today under one from three months ago, and sorting by date buries the job
        # worth applying to under fifty that are not. Fit decays with age rather than being
        # bucketed, so a great older posting can still outrank a mediocre new one instead of being
        # cut off at an arbitrary boundary.
        age_days = (
            func.extract("epoch", func.now() - func.coalesce(Job.posted_at, Job.discovered_at))
            / 86400.0
        )
        decayed = Job.best_fit - func.least(age_days, RECENCY_DECAY_CAP_DAYS) * RECENCY_DECAY
        # Recency breaks ties AND orders the unscored. A job with no `best_fit` yet decays to NULL
        # and sorts last; without this second key those rows would fall through to `Job.id`, which
        # is a random UUID -- so a freshly added job could land anywhere among its peers.
        query = query.order_by(
            nulls_last(decayed.desc()),
            func.coalesce(Job.posted_at, Job.discovered_at).desc(),
            Job.id,
        )
    elif params.sort == "newest":
        # A posting with its own date sorts by that; a manual or dateless one falls back to when
        # Rhapto discovered it -- the same coalesce `posted_within` judges recency by above.
        query = query.order_by(
            func.coalesce(Job.posted_at, Job.discovered_at).desc(),
            Job.created_at.desc(),
            Job.id,
        )
    else:
        query = query.order_by(nulls_last(Job.best_fit.desc()), Job.discovered_at.desc(), Job.id)
    return [(job, name) for job, name in (await session.execute(query)).all()]


@dataclass(frozen=True)
class EmptyReason:
    """Why exactly these filters matched nothing, decided from the registry that filtered."""

    #: Every job this user owns, ignoring every filter. 0 means the corpus itself is empty.
    total: int
    #: One of the `JobsEmptyReasonOut.cause` values; the schema holds the closed set.
    cause: str
    #: The blamed registry id, only when `cause == "filter"`.
    filter_id: str | None = None
    #: That filter's current value, rendered by its own registry entry -- never restated here.
    filter_value: str | None = None
    #: Rows that appear if that one filter is widened and nothing else changes.
    would_match: int | None = None
    #: Per blamable ACTIVE filter, how many rows appear if that one filter is widened and nothing else
    #: changes -- the same leave-one-out counts the blame is chosen from, so this costs nothing extra.
    #:
    #: Exposed because a client offering a widen has no other way to know the widen would reveal
    #: nothing: under `cause = "combination"` every entry here is 0 by definition, and an inactive
    #: filter is simply absent. It is a count, not a suggestion, so C7 is untouched -- nothing here
    #: asserts a cause or proposes a value the user did not already choose.
    would_match_without: dict[str, int] = dataclass_field(default_factory=dict)


async def empty_reason(
    session: AsyncSession, params: JobFilterParams, resolved: TrackFields
) -> EmptyReason:
    """Diagnose an empty `GET /jobs` result, using the same clauses that produced it.

    One statement: the user's total, the count for the full active clause set, and one
    leave-one-out count per blamable active filter, as `count(*) FILTER (WHERE ...)` aggregates
    over a single scan of this user's jobs.

    The blame goes to the filter whose removal reveals the MOST rows, not the first one that
    reveals any. That is deliberate and deterministic: it names the most restrictive filter, which
    is the one a user wants widened. Ties break by registry order.

    When no single removal reveals anything, the honest answer is `"combination"` -- two filters
    together excluded everything and no one of them is responsible. Inventing a culprit there would
    be the same class of fabrication as inventing a city name.
    """
    tracks, ctx = filter_context(params.user_id, resolved.track_ids)
    active = active_filters(params)
    blamable = [f for f in active if f.blamable]
    columns: list[Any] = [
        # Tenancy only, nothing else: this is the "is the corpus empty at all" answer.
        func.count().label("total"),
        func.count().filter(and_(true(), *active_clauses(params, ctx))).label("matched"),
    ]
    for entry in blamable:
        columns.append(
            func.count()
            .filter(and_(true(), *active_clauses(params, ctx, without=entry.id)))
            .label(f"without_{entry.id}")
        )
    row = (
        await session.execute(
            select(*columns)
            .select_from(Job)
            # `bucket` compares against this subquery's min_fit, so the statement must join it for
            # the same reason `list_jobs` does.
            .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
            # The one predicate no leave-one-out can remove.
            .where(Job.user_id == params.user_id)
        )
    ).one()
    total = int(row.total or 0)
    matched = int(row.matched or 0)
    if total == 0:
        return EmptyReason(total=total, cause="no_jobs")
    # Checked before the counts because it is categorically different: not "a filter excluded
    # everything" but "this filter can never match", which is the distinction the empty states
    # exist to make.
    if params.field is not None and not resolved.track_ids:
        return EmptyReason(total=total, cause="field_without_tracks")
    if matched != 0:
        # The client asked for a diagnosis of a result that is not empty. Not an error: the honest
        # answer is "there are rows for these filters".
        return EmptyReason(total=total, cause="nothing_matched")
    # Every active blamable filter's leave-one-out count, kept rather than reduced to the maximum:
    # the blame needs only the largest, but a client deciding whether a widen is worth offering needs
    # each one. Same statement, same numbers.
    without = {entry.id: int(getattr(row, f"without_{entry.id}") or 0) for entry in blamable}
    best: JobFilter | None = None
    best_count = 0
    for entry in blamable:
        if without[entry.id] > best_count:
            best, best_count = entry, without[entry.id]
    if best is None:
        return EmptyReason(total=total, cause="combination", would_match_without=without)
    return EmptyReason(
        total=total,
        cause="filter",
        filter_id=best.id,
        filter_value=best.value(params),
        would_match=best_count,
        would_match_without=without,
    )


async def search_name_for(
    session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID | None
) -> str | None:
    if search_id is None:
        return None
    result: str | None = await session.scalar(
        select(SearchRow.name).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
    )
    return result


async def find_by_external_id(
    session: AsyncSession, user_id: uuid.UUID, source: str, external_id: str
) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(
            Job.user_id == user_id, Job.source == source, Job.external_id == external_id
        )
    )
    return result


async def find_by_identity(
    session: AsyncSession, user_id: uuid.UUID, identity_hash: str
) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job)
        .where(Job.user_id == user_id, Job.identity_hash == identity_hash)
        .order_by(Job.discovered_at)
        .limit(1)
    )
    return result


def _clamp(value: str | None, limit: int) -> str | None:
    """Cut a source-supplied string to what its column holds, keeping the head.

    A feed is free to return a title of any length -- Hacker News "Who's Hiring" posts are whole
    paragraphs -- and Postgres answers an over-long value with StringDataRightTruncationError.
    That does not merely lose the posting: it fails the transaction mid-poll, and in `poll_sources`
    every source after it in the same run failed too. Clamping keeps the informative start of the
    value and lets the run continue.
    """
    if value is None:
        return None
    return value[:limit]


async def create_discovered_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source: str,
    external_id: str,
    company: str,
    title: str,
    location: str | None,
    url: str,
    jd_text: str,
    posted_at: datetime | None,
    identity_hash: str,
    repost_of: uuid.UUID | None,
    search_id: uuid.UUID | None = None,
    salary_text: str | None = None,
) -> Job:
    job = Job(
        user_id=user_id,
        source=source,
        external_id=_clamp(external_id, 200),
        company=_clamp(company, 200),
        title=_clamp(title, 300),
        location=_clamp(location, 200),
        url=url,
        jd_text=jd_text,
        dedupe_hash=compute_dedupe_hash(jd_text),
        discovered_at=datetime.now(UTC),
        posted_at=posted_at,
        identity_hash=identity_hash,
        repost_of=repost_of,
        search_id=search_id,
        salary_text=salary_text,
    )
    session.add(job)
    await session.flush()
    return job


def set_rescued(job: Job, value: bool) -> None:
    job.rescued = value


def set_hidden(job: Job, hidden: bool) -> None:
    """Idempotent: hiding an already-hidden job keeps its original timestamp."""
    if hidden:
        job.hidden_at = job.hidden_at or datetime.now(UTC)
    else:
        job.hidden_at = None


async def get_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(Job.user_id == user_id, Job.id == job_id)
    )
    return result


async def delete_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(delete(Job).where(Job.user_id == user_id, Job.id == job_id)),
    )
    return bool(result.rowcount)


async def package_ids_for_job(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> list[uuid.UUID]:
    return list(
        await session.scalars(
            select(Package.id).where(Package.user_id == user_id, Package.job_id == job_id)
        )
    )


async def latest_package(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> Package | None:
    result: Package | None = await session.scalar(
        select(Package)
        .where(Package.user_id == user_id, Package.job_id == job_id)
        .order_by(Package.version.desc())
        .limit(1)
    )
    return result


async def application_for_job(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> Application | None:
    result: Application | None = await session.scalar(
        select(Application)
        .where(Application.user_id == user_id, Application.job_id == job_id)
        .order_by(Application.created_at.desc())
        .limit(1)
    )
    return result


#: Consecutive polls that must miss a posting before it counts as gone. Two, not one: a source
#: paginating differently, or a transient partial page, routinely drops a posting for one run.
UNLISTED_AFTER = 2


async def reconcile_listing(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source: str,
    company: str | None,
    search_id: uuid.UUID | None,
    seen_external_ids: set[str],
) -> int:
    """Update miss counts for one poll of one source, and return how many jobs it just retired.

    The scope is what this particular fetch could have returned -- the saved search's own
    `search_id`, or the company for a board -- never the whole source. Scoping wider would mark
    every job from a search the user just paused as unlisted the first time another search ran.
    A job that is seen again has both fields cleared: postings come back.

    When neither narrows the scope (a keyless aggregator spec with no saved search behind it),
    there is no way to know what this fetch could and could not have returned, so reconciliation
    is skipped entirely rather than falling back to the whole source -- which would eventually
    mark every other search's and board's jobs on that source as unlisted.
    """
    if search_id is None and company is None:
        return 0
    scope = [Job.user_id == user_id, Job.source == source, Job.external_id.is_not(None)]
    if search_id is not None:
        scope.append(Job.search_id == search_id)
    elif company is not None:
        scope.append(Job.company == company)
    rows = list(await session.scalars(select(Job).where(*scope)))
    now = datetime.now(UTC)
    retired = 0
    for job in rows:
        if job.external_id in seen_external_ids:
            job.miss_count = 0
            job.unlisted_at = None
            continue
        if job.unlisted_at is not None:
            continue
        job.miss_count = min(job.miss_count + 1, UNLISTED_AFTER)
        if job.miss_count >= UNLISTED_AFTER:
            job.unlisted_at = now
            retired += 1
    await session.flush()
    return retired
