from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Aggregator, Job, User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo


async def _job(session: AsyncSession, user: User, external_id: str, **kwargs: object) -> Job:
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source=str(kwargs.pop("source", "greenhouse")),
        external_id=external_id,
        company=str(kwargs.pop("company", "ExampleCo")),
        title="Technical Program Manager",
        location=None,
        url=f"https://example.com/{external_id}",
        jd_text="x" * 80,
        posted_at=None,
        identity_hash=f"h-{external_id}",
        repost_of=None,
        **kwargs,  # type: ignore[arg-type]
    )
    await session.flush()
    return job


async def test_two_consecutive_misses_mark_a_job_unlisted(
    session: AsyncSession, user: User
) -> None:
    gone = await _job(session, user, "gone")
    still = await _job(session, user, "still")
    args = {"source": "greenhouse", "company": "ExampleCo", "search_id": None}
    assert (
        await jobs_repo.reconcile_listing(session, user.id, seen_external_ids={"still"}, **args)
        == 0
    )
    assert gone.miss_count == 1 and gone.unlisted_at is None
    assert (
        await jobs_repo.reconcile_listing(session, user.id, seen_external_ids={"still"}, **args)
        == 1
    )
    assert gone.miss_count == 2 and gone.unlisted_at is not None
    assert still.miss_count == 0 and still.unlisted_at is None
    # Already marked: it is not counted a second time.
    assert (
        await jobs_repo.reconcile_listing(session, user.id, seen_external_ids={"still"}, **args)
        == 0
    )


async def test_a_sighting_resets_both_fields(session: AsyncSession, user: User) -> None:
    job = await _job(session, user, "back")
    args = {"source": "greenhouse", "company": "ExampleCo", "search_id": None}
    await jobs_repo.reconcile_listing(session, user.id, seen_external_ids=set(), **args)
    await jobs_repo.reconcile_listing(session, user.id, seen_external_ids=set(), **args)
    assert job.unlisted_at is not None
    await jobs_repo.reconcile_listing(session, user.id, seen_external_ids={"back"}, **args)
    assert job.miss_count == 0 and job.unlisted_at is None


async def test_the_scope_is_the_search_or_the_company_not_the_whole_source(
    session: AsyncSession, user: User
) -> None:
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["a"], location=None, remote="include"
    )
    other = await searches_repo.create_search(
        session, user.id, name="B", keywords=["b"], location=None, remote="include"
    )
    mine = await _job(session, user, "mine", source="themuse", search_id=search.id)
    theirs = await _job(session, user, "theirs", source="themuse", search_id=other.id)
    other_company = await _job(session, user, "elsewhere", company="OtherCo")
    for _ in range(2):
        await jobs_repo.reconcile_listing(
            session,
            user.id,
            source="themuse",
            company=None,
            search_id=search.id,
            seen_external_ids=set(),
        )
    assert mine.unlisted_at is not None
    assert theirs.unlisted_at is None and theirs.miss_count == 0
    assert other_company.miss_count == 0


async def test_manual_jobs_are_never_touched(session: AsyncSession, user: User) -> None:
    manual = await jobs_repo.create_job(session, user.id, jd_text="y" * 80, company="ExampleCo")
    await session.flush()
    for _ in range(3):
        await jobs_repo.reconcile_listing(
            session,
            user.id,
            source="manual",
            company="ExampleCo",
            search_id=None,
            seen_external_ids=set(),
        )
    assert manual.miss_count == 0 and manual.unlisted_at is None


async def test_the_poller_reconciles_only_on_a_successful_non_empty_fetch(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    """A source that errors, or returns nothing, must not empty the user's queue."""
    from test_poller import FakeAggregator  # registered by the fixture

    from rhapto.engine.providers.fake import FakeEmbeddingProvider
    from rhapto.services.discovery.http import FakeDiscoveryHttp
    from rhapto.services.discovery.poller import poll_sources

    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["a"], location=None, remote="include"
    )
    stale = await _job(session, user, "stale", source="fake-agg", search_id=search.id)
    # The pydantic AggregatorEntry model restricts `source` to the real, registered aggregator
    # ids, so a throwaway test id is inserted straight through the ORM row instead (as
    # test_poller.py's own tests do).
    session.add(Aggregator(user_id=user.id, source="fake-agg", enabled=True, keywords=[]))
    await session.flush()
    FakeAggregator.postings = []
    await poll_sources(
        session, user.id, http=FakeDiscoveryHttp({}), embedder=FakeEmbeddingProvider(dimensions=384)
    )
    assert stale.miss_count == 0, "an empty fetch says nothing about what is still listed"


async def test_a_capped_search_result_skips_reconciliation(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    """A search-driven fetch that hit SEARCH_CAP is truncated, not exhaustive; it must not be
    read as proof that everything else in the scope is gone. A board fetch has no such cap and
    always reconciles (covered by the other tests above)."""
    from rhapto.engine.providers.fake import FakeEmbeddingProvider
    from rhapto.services.discovery.http import FakeDiscoveryHttp
    from rhapto.services.discovery.poller import SourceSpec, poll_sources
    from rhapto.services.discovery.posting import Posting
    from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec

    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["alpha"], location=None, remote="include"
    )
    stale = await _job(session, user, "stale", source="fake-agg", search_id=search.id)
    session.add(Aggregator(user_id=user.id, source="fake-agg", enabled=True, keywords=[]))
    await session.flush()
    from test_poller import FakeAggregator  # registered by the fixture

    FakeAggregator.postings = [
        Posting(
            external_id=str(i),
            company="ExampleCo",
            title="Role",
            location=None,
            url=f"https://example.com/{i}",
            jd_text="x" * 80,
        )
        for i in range(SEARCH_CAP)
    ]
    spec = SourceSpec(
        source="fake-agg",
        board=None,
        company=None,
        keywords=["alpha"],
        search=SearchSpec(keywords=("alpha",), location=None, remote="include", name="A"),
        search_id=search.id,
    )
    await poll_sources(
        session,
        user.id,
        http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384),
        specs=[spec],
    )
    assert stale.miss_count == 0, "a capped page cannot prove the rest of the scope is gone"
