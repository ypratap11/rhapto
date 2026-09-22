from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import jobs as jobs_repo


async def test_overlong_source_fields_are_clamped_to_their_columns(
    session: AsyncSession, user: User
) -> None:
    """A source that returns a huge title must not abort the insert.

    `jobs.title` is varchar(300), `company` and `location` varchar(200), `external_id`
    varchar(200). Hacker News "Who's Hiring" posts are free text, so an over-long title is normal
    input, not a bug in the feed -- and the resulting StringDataRightTruncationError did not just
    lose that one posting. It poisoned the session mid-poll, and every source after it in the same
    run failed too, which is how one bad post cost three aggregators across two saved searches.
    """
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="hn-hiring",
        external_id="e" * 400,
        company="C" * 400,
        title="T" * 900,
        location="L" * 400,
        url="https://example.com/huge",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash="hash-huge",
        repost_of=None,
    )
    await session.flush()

    assert job.title is not None and len(job.title) == 300
    assert job.company is not None and len(job.company) == 200
    assert job.location is not None and len(job.location) == 200
    assert job.external_id is not None and len(job.external_id) == 200
    # The start of the value is what carries meaning, so clamping keeps the head.
    assert job.title.startswith("TTT")


async def test_values_within_the_limits_are_untouched(session: AsyncSession, user: User) -> None:
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="themuse",
        external_id="abc-123",
        company="ExampleCo",
        title="Technical Program Manager",
        location="Dublin, CA",
        url="https://example.com/ok",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash="hash-ok",
        repost_of=None,
    )
    await session.flush()

    assert job.title == "Technical Program Manager"
    assert job.company == "ExampleCo"
    assert job.location == "Dublin, CA"
    assert job.external_id == "abc-123"
