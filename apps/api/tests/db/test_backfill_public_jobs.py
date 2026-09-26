from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job
from rhapto.db.repositories.jobs import backfill_public_jobs
from rhapto.db.repositories.users import get_or_create_user


async def _seed_job(session: AsyncSession, owner_id: uuid.UUID, **overrides) -> Job:
    defaults = dict(
        user_id=owner_id,
        source="greenhouse",
        external_id="ext-1",
        url="https://boards.example.com/1",
        company="Acme",
        title="Engineer",
        location="Remote",
        posted_at=datetime.now(UTC),
        jd_text="A real job description, long enough to pass validation. " * 3,
        jd_embedding=[0.1] * 384,
        dedupe_hash=f"hash-{uuid.uuid4()}",
        identity_hash=f"identity-{uuid.uuid4()}",
        discovered_at=datetime.now(UTC),
        miss_count=0,
    )
    defaults.update(overrides)
    job = Job(**defaults)
    session.add(job)
    await session.flush()
    return job


PUBLIC_SOURCES = ["greenhouse", "lever"]  # real SOURCES keys used only as test fixtures here (I10:
# the repository function itself never imports SOURCES)


async def test_copies_a_public_job_into_the_new_account(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id)
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 1
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1
    assert rows[0].jd_embedding is not None  # the cached vector rides along


async def test_never_copies_a_manual_job(session: AsyncSession) -> None:
    """The highest-consequence line of SQL in Phase A: a hand-pasted recruiter email must never
    reach a second account."""
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="manual", external_id=None, url=None)
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 0
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert rows == []


async def test_never_copies_a_source_that_is_not_in_the_allowlist_even_though_it_is_not_manual(
    session: AsyncSession,
) -> None:
    """A negative filter (`source <> 'manual'`) would pass `test_never_copies_a_manual_job` above
    just as well as the required positive allowlist does, since both exclude 'manual' -- that test
    alone cannot tell the two implementations apart. This test plants a job under a source that is
    neither 'manual' nor in `public_sources` (standing in for a source registered after this code
    was written, or a source under active development that should not be exposed to new accounts
    yet) and is the one that actually fails if the filter is ever loosened to a negative check."""
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="not-yet-allowlisted", external_id="ext-future")
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 0
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert rows == []


async def test_excluded_columns_are_never_copied(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    other_owner_job = await _seed_job(session, owner.id, source="greenhouse")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(
        session,
        owner.id,
        source="lever",
        external_id="ext-2",
        dedupe_hash=f"hash-{uuid.uuid4()}",
        best_fit=88,
        best_track_id="pm",
        location_tier="preferred",
        hidden_at=datetime.now(UTC),
        rescued=True,
        extracted_json={"company": "Acme", "title": "Engineer", "context_tags": []},
        repost_of=other_owner_job.id,
    )
    await session.commit()

    await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    for row in rows:
        assert row.extracted_json is None
        assert row.repost_of is None
        assert row.best_fit is None
        assert row.best_track_id is None
        assert row.location_tier is None
        assert row.hidden_at is None
        assert row.rescued is False
        assert row.search_id is None


async def test_excludes_unlisted_and_stale_jobs(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse", unlisted_at=datetime.now(UTC))
    await _seed_job(
        session,
        owner.id,
        source="lever",
        external_id="ext-old",
        dedupe_hash=f"hash-{uuid.uuid4()}",
        posted_at=datetime.now(UTC) - timedelta(days=91),
    )
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()
    assert count == 0


async def test_is_idempotent(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse")
    await session.commit()

    first = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()
    second = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert first == 1
    assert second == 0
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1


async def test_two_rows_sharing_source_and_external_id_with_different_dedupe_hash_do_not_collide(
    session: AsyncSession,
) -> None:
    """Fixes plan-review C5: a JD whose text (and therefore dedupe_hash) changed between two polls
    used to survive `DISTINCT ON (dedupe_hash)` as two rows, both sharing (source, external_id) --
    violating uq_jobs_user_source_external the moment both were inserted for one new account and
    500ing the request that was supposed to create it.

    `uq_jobs_user_source_external` is scoped per user_id, so the two "duplicate" rows can only
    coexist under two *different* existing accounts (each with its own independent per-user poll
    history, per Task 4's fan-out) -- the same account could never hold both rows simultaneously,
    since the second insert would itself violate that constraint. This is exactly the real-world
    shape backfill_public_jobs's unscoped `FROM jobs` has to collapse across.
    """
    owner = await get_or_create_user(session, "owner@example.com")
    another_existing_account = await get_or_create_user(session, "another-existing@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(
        session,
        owner.id,
        source="greenhouse",
        external_id="shared-ext",
        dedupe_hash=f"hash-old-{uuid.uuid4()}",
        discovered_at=datetime.now(UTC) - timedelta(days=2),
    )
    await _seed_job(
        session,
        another_existing_account.id,
        source="greenhouse",
        external_id="shared-ext",
        dedupe_hash=f"hash-new-{uuid.uuid4()}",
        discovered_at=datetime.now(UTC),
    )
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 1  # never raises, and collapses to exactly one row for the shared external_id
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1


async def test_unscored_backfilled_rows_stay_in_the_default_fit_bucket(
    session: AsyncSession,
) -> None:
    """Pins the existing (pre-A5) behaviour this task relies on rather than reimplementing:
    best_fit IS NULL rows are not filtered out of the default grid view. Fixes plan-review I2:
    list_jobs returns list[tuple[Job, str | None]] (job, search name), verified against
    db/repositories/jobs.py:63 -- the earlier draft of this test indexed it as if it returned bare
    Job rows."""
    from rhapto.db.repositories.jobs import list_jobs

    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse")
    await session.commit()
    await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    rows = await list_jobs(session, newcomer.id, bucket="fit")
    assert len(rows) == 1
    job, _search_name = rows[0]
    assert job.best_fit is None


async def test_already_seeded_account_is_not_reseeded_by_the_atomic_claim(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Migration 0011 already ran `UPDATE users SET seeded_at = now() WHERE seeded_at IS NULL`, so
    the owner's live account -- the only one holding real data -- is already marked seeded before
    this endpoint ever ran. Proves the claim statement itself (not just the endpoint) refuses to
    re-claim a row whose seeded_at is already set, which is what protects that account from ever
    being backfilled by mistake."""
    async with session_factory() as session:
        owner = await get_or_create_user(session, "owner@example.com")
        await session.execute(
            text("UPDATE users SET seeded_at = now() WHERE id = :uid"), {"uid": str(owner.id)}
        )
        await session.commit()
        owner_id = owner.id

    async with session_factory() as session:
        claim = await session.execute(
            text(
                "UPDATE users SET seeded_at = now() WHERE id = :uid AND seeded_at IS NULL "
                "RETURNING id"
            ),
            {"uid": str(owner_id)},
        )
        row = claim.first()
        await session.commit()

    assert row is None  # already-seeded account claims nothing, so no backfill would ever run


async def test_concurrent_seed_claims_result_in_exactly_one_claim(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """This is the statement Task 5 Step 5's POST /me/bootstrap runs to decide whether to seed.
    Proves it directly, at the SQL level, under a real race: two concurrent transactions racing on
    the same row's `seeded_at IS NULL` claim must not both succeed. Postgres's row lock makes the
    loser's UPDATE block until the winner commits, then re-evaluate WHERE against the now-non-NULL
    value and match zero rows -- this is what makes first sign-in race-safe rather than merely
    idempotent.
    """
    import asyncio

    async with session_factory() as setup:
        user = await get_or_create_user(setup, "racer@example.com")
        await setup.commit()
        user_id = user.id

    async def claim() -> bool:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "UPDATE users SET seeded_at = now() WHERE id = :uid AND seeded_at IS NULL "
                    "RETURNING id"
                ),
                {"uid": str(user_id)},
            )
            got = result.first() is not None
            await session.commit()
            return got

    results = await asyncio.gather(claim(), claim())
    assert sorted(results) == [False, True]
