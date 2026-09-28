"""What a job source last did, whether it can run at all, and whether it is being refused.

Architecture §8 rows 4 and 5. Row 5 is the one that must not share the implementation's premise: it
runs the **poller** to establish that the fixture really is paused according to the production
predicate, not according to the read path being tested, and runs it again after Resume to prove the
resume really resumed it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Aggregator, PollRun
from rhapto.db.repositories import searches as searches_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.poller import PAUSED_MESSAGE, SourceSpec, poll_sources
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceInfo

STUB = "fake-pausable"
SOURCES_URL = "/api/v1/settings/sources"


class StubAggregator:
    """A source that always succeeds, and records whether it was actually called.

    "Was it called" is the assertion Row 5 turns on: a paused scope must not reach the source at
    all, and a resumed one must.
    """

    info = SourceInfo(STUB, "aggregator", "Fake pausable", False)
    calls: int = 0

    async def fetch_search(
        self, http: Any, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        type(self).calls += 1
        return [
            Posting(
                external_id="p1",
                company="ExampleCo",
                title="Program Manager",
                location="Remote",
                url="https://example.com/p1",
                jd_text="a program manager posting " * 10,
                posted_at=datetime.now(UTC),
            )
        ]


@pytest.fixture(autouse=True)
def stub_source() -> Iterator[None]:
    SOURCES[STUB] = StubAggregator  # type: ignore[assignment]
    StubAggregator.calls = 0
    yield
    SOURCES.pop(STUB, None)
    StubAggregator.calls = 0


async def _row(client: httpx.AsyncClient, source: str) -> dict[str, Any]:
    rows = (await client.get(SOURCES_URL)).json()
    return dict(next(r for r in rows if r["id"] == source))


async def _aggregator(session: AsyncSession, user_id: uuid.UUID, source: str) -> Aggregator:
    row = await session.scalar(
        select(Aggregator).where(Aggregator.user_id == user_id, Aggregator.source == source)
    )
    assert row is not None, f"no aggregators row for {source}"
    return row


# --- runnable: the poller's rule, not the display default -------------------------------------


async def test_a_user_with_no_aggregator_rows_has_no_runnable_source(
    client: httpx.AsyncClient,
) -> None:
    """The defect this pass found, pinned as the honest answer.

    `GET /settings/sources` reports the four keyless sources as `enabled = true` for an account with
    no `aggregators` rows, while `poller.build_specs` returns early with board specs only when the
    enabled list is empty -- so such an account polls no aggregators at all. `runnable` follows the
    poller, so `enabled = true` and `runnable = false` appear together, which is exactly the
    discrepancy made visible. The behaviour itself is unchanged: see
    docs/portal-backend-followups.md.
    """
    rows = (await client.get(SOURCES_URL)).json()
    keyless = [r for r in rows if not r["needs_key"]]
    assert keyless, "the registry should ship at least one keyless source"
    assert all(r["enabled"] is True for r in keyless)
    assert all(r["runnable"] is False for r in rows)


async def test_enabling_a_keyless_source_makes_it_runnable(client: httpx.AsyncClient) -> None:
    """The real condition: a row now exists and is enabled, which is what `build_specs` requires."""
    assert (await _row(client, "themuse"))["runnable"] is False
    assert (await client.put(f"{SOURCES_URL}/themuse", json={"enabled": True})).status_code == 200
    assert (await _row(client, "themuse"))["runnable"] is True


async def test_a_disabled_row_is_not_runnable(client: httpx.AsyncClient) -> None:
    await client.put(f"{SOURCES_URL}/themuse", json={"enabled": True})
    await client.put(f"{SOURCES_URL}/themuse", json={"enabled": False})
    assert (await _row(client, "themuse"))["runnable"] is False


async def test_a_keyed_source_is_not_runnable_until_its_credentials_are_stored(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """A row saying "enabled" describing something that cannot run is the `resume_template` defect.

    The row is written directly, because `PUT /settings/sources/adzuna {"enabled": true}` correctly
    422s without credentials -- so this state is only reachable by a hand-seeded or legacy row, which
    is precisely the case that must not read as ready.
    """
    async with session_factory() as session:
        session.add(Aggregator(user_id=user_id, source="adzuna", enabled=True, keywords=[]))
        await session.commit()

    row = await _row(client, "adzuna")
    assert row["enabled"] is True
    assert row["key_set"] is False
    assert row["runnable"] is False

    assert (
        await client.put(
            f"{SOURCES_URL}/adzuna",
            json={"enabled": True, "credentials": {"app_id": "a", "app_key": "b"}},
        )
    ).status_code == 200
    after = await _row(client, "adzuna")
    assert after["key_set"] is True and after["runnable"] is True


# --- Row 4: a source that returned zero for a location ----------------------------------------


async def test_a_zero_result_run_reports_what_the_source_was_asked_for(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The real condition: `found = 0` with `error = None` -- the source answered and had nothing.

    Without the join to `searches` the row can only say "returned 0", which is the silence spec §8
    row 4 exists to break.
    """
    async with session_factory() as session:
        search = await searches_repo.create_search(
            session,
            user_id,
            name="Bay Area PM",
            keywords=["program manager"],
            location="San Francisco Bay Area",
            remote="include",
        )
        await session.flush()
        started = datetime.now(UTC)
        session.add(
            PollRun(
                user_id=user_id,
                source="adzuna",
                board=None,
                search_id=search.id,
                started_at=started,
                finished_at=started,
                found=0,
                new=0,
                error=None,
            )
        )
        await session.commit()

    row = await _row(client, "adzuna")
    assert row["last_run"] is not None
    assert row["last_run"]["found"] == 0
    assert row["last_run"]["error"] is None
    assert row["last_run"]["search_name"] == "Bay Area PM"
    assert row["last_run"]["search_location"] == "San Francisco Bay Area"


async def test_the_last_run_never_offers_an_alternative_location(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Condition C7. There is no location normaliser, gazetteer, alias table or per-source location
    vocabulary anywhere in this repo, and no source exposes one, so any "Try X" would be a
    hard-coded string or an invention. No field may exist to hold one."""
    async with session_factory() as session:
        search = await searches_repo.create_search(
            session,
            user_id,
            name="Bay Area PM",
            keywords=["pm"],
            location="San Francisco Bay Area",
            remote="include",
        )
        await session.flush()
        started = datetime.now(UTC)
        session.add(
            PollRun(
                user_id=user_id,
                source="adzuna",
                board=None,
                search_id=search.id,
                started_at=started,
                finished_at=started,
                found=0,
                new=0,
                error=None,
            )
        )
        await session.commit()

    last_run = (await _row(client, "adzuna"))["last_run"]
    forbidden = {
        "suggestion",
        "suggested_location",
        "location_suggestion",
        "try_location",
        "alternative_location",
        "alternatives",
    }
    assert forbidden.isdisjoint(last_run.keys()), sorted(forbidden & set(last_run.keys()))


async def test_a_board_run_has_no_search_to_name(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The contrasting fixture for the same field: `search_id IS NULL` must LEFT-join to None rather
    than drop the row."""
    async with session_factory() as session:
        started = datetime.now(UTC)
        session.add(
            PollRun(
                user_id=user_id,
                source="themuse",
                board=None,
                search_id=None,
                started_at=started,
                finished_at=started,
                found=7,
                new=2,
                error=None,
            )
        )
        await session.commit()

    last_run = (await _row(client, "themuse"))["last_run"]
    assert last_run is not None
    assert last_run["found"] == 7
    assert last_run["search_id"] is None
    assert last_run["search_name"] is None and last_run["search_location"] is None


async def test_a_source_that_has_never_run_has_no_last_run(client: httpx.AsyncClient) -> None:
    assert (await _row(client, "themuse"))["last_run"] is None
    assert (await _row(client, "themuse"))["paused"] is False


async def test_another_users_runs_do_not_appear_on_this_users_source_rows(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as session:
        other = await get_or_create_user(session, "other-source-status@example.com")
        started = datetime.now(UTC)
        session.add(
            PollRun(
                user_id=other.id,
                source="themuse",
                board=None,
                search_id=None,
                started_at=started,
                finished_at=started,
                found=42,
                new=42,
                error=None,
            )
        )
        await session.commit()

    assert (await _row(client, "themuse"))["last_run"] is None


# --- Row 5: a paused source, verified against the poller itself --------------------------------


async def _pause_fixture(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> tuple[uuid.UUID, datetime]:
    """Enable the stub source, give it a saved search, and record three failures after the row was
    last saved. Returns the search id and the row's (back-dated) `updated_at`."""
    assert (await client.put(f"{SOURCES_URL}/{STUB}", json={"enabled": True})).status_code == 200
    async with session_factory() as session:
        search = await searches_repo.create_search(
            session,
            user_id,
            name="Stub search",
            keywords=["pm"],
            location="Remote",
            remote="include",
        )
        await session.flush()
        row = await _aggregator(session, user_id, STUB)
        entry_updated_at = datetime.now(UTC) - timedelta(hours=1)
        row.updated_at = entry_updated_at
        for i in range(3):
            started = entry_updated_at + timedelta(minutes=10 * (i + 1))
            session.add(
                PollRun(
                    user_id=user_id,
                    source=STUB,
                    board=None,
                    search_id=search.id,
                    started_at=started,
                    finished_at=started,
                    found=0,
                    new=0,
                    error="HTTP 500",
                )
            )
        await session.commit()
        return search.id, entry_updated_at


def _spec(search_id: uuid.UUID, entry_updated_at: datetime) -> SourceSpec:
    return SourceSpec(
        source=STUB,
        board=None,
        company=None,
        keywords=["pm"],
        entry_updated_at=entry_updated_at,
        search=SearchSpec(
            keywords=("pm",), location="Remote", remote="include", name="Stub search"
        ),
        search_id=search_id,
    )


async def _poll(session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec) -> str | None:
    summary = await poll_sources(
        session,
        user_id,
        http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384),
        specs=[spec],
    )
    return summary.results[0].error


async def test_paused_then_resumed_verified_by_running_the_poller_both_times(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Steps 1 and 4 are the whole point of this test.

    The pause rule lives in `poller._is_paused` (a failure streak plus `entry_updated_at <=
    last.started_at`) and the read path under test does NOT reimplement it -- it reads the
    `PAUSED_MESSAGE` run the poller writes when it refuses a spec. A check built from the read path's
    own assumption about the streak rule would confirm that assumption whether or not it matched the
    poller. So the fixture is validated by running the poller: if `poll_sources` does not refuse it,
    the fixture is not paused and this test is meaningless.
    """
    search_id, entry_updated_at = await _pause_fixture(client, session_factory, user_id)

    # 1. The production predicate agrees the fixture is paused, and nothing reached the source.
    async with session_factory() as session:
        assert await _poll(session, user_id, _spec(search_id, entry_updated_at)) == PAUSED_MESSAGE
    assert StubAggregator.calls == 0, "a paused spec must not reach the source at all"

    # 2. The read path reports it.
    row = await _row(client, STUB)
    assert row["paused"] is True
    assert row["last_run"]["error"] == PAUSED_MESSAGE
    # `runnable` deliberately EXCLUDES pause: it answers "is setup done", and pause is scoped per
    # (source, board, search_id) so one boolean per source cannot carry it. The row is still
    # configured and credentialled, so it is runnable AND currently paused -- two different
    # questions, which is why there are two fields.
    assert row["runnable"] is True

    # 3. Resume.
    resumed = await client.post(f"{SOURCES_URL}/{STUB}/resume")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["paused"] is False
    assert (await _row(client, STUB))["paused"] is False

    # 4. The poller now actually calls the source -- the resume really resumed it.
    async with session_factory() as session:
        fresh = (await _aggregator(session, user_id, STUB)).updated_at
        assert await _poll(session, user_id, _spec(search_id, fresh)) is None
    assert StubAggregator.calls == 1


async def test_a_pause_older_than_the_last_save_does_not_read_as_paused(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The stale-pause case, as its own fixture: a PAUSED_MESSAGE run that started BEFORE the row
    was last saved is history, not current state. This is the clause `_is_paused` uses too."""
    assert (await client.put(f"{SOURCES_URL}/{STUB}", json={"enabled": True})).status_code == 200
    async with session_factory() as session:
        row = await _aggregator(session, user_id, STUB)
        started = row.updated_at - timedelta(hours=2)
        session.add(
            PollRun(
                user_id=user_id,
                source=STUB,
                board=None,
                search_id=None,
                started_at=started,
                finished_at=started,
                found=0,
                new=0,
                error=PAUSED_MESSAGE,
            )
        )
        await session.commit()

    row_out = await _row(client, STUB)
    assert row_out["last_run"]["error"] == PAUSED_MESSAGE
    assert row_out["paused"] is False, "a pause from before the last save is not current"


async def test_a_failing_but_not_yet_paused_source_shows_the_error_and_is_not_paused(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The documented one-cycle lag, asserted rather than assumed: after failures but before the
    poller has written a PAUSED_MESSAGE run, the row reads not-paused and still shows the error."""
    assert (await client.put(f"{SOURCES_URL}/{STUB}", json={"enabled": True})).status_code == 200
    async with session_factory() as session:
        row = await _aggregator(session, user_id, STUB)
        started = row.updated_at + timedelta(minutes=5)
        session.add(
            PollRun(
                user_id=user_id,
                source=STUB,
                board=None,
                search_id=None,
                started_at=started,
                finished_at=started,
                found=0,
                new=0,
                error="HTTP 500",
            )
        )
        await session.commit()

    row_out = await _row(client, STUB)
    assert row_out["paused"] is False
    assert row_out["last_run"]["error"] == "HTTP 500"


# --- the Resume endpoint's own contract -------------------------------------------------------


async def test_resume_is_404_for_an_unknown_source(client: httpx.AsyncClient) -> None:
    assert (await client.post(f"{SOURCES_URL}/not-a-source/resume")).status_code == 404


async def test_resume_is_404_when_the_user_has_no_row_for_that_source(
    client: httpx.AsyncClient,
) -> None:
    """There is no pause to lift on a source that was never configured, and answering 200 would be a
    lie about state -- the UI would show a Resume button that silently did nothing."""
    assert (await client.post(f"{SOURCES_URL}/themuse/resume")).status_code == 404


async def test_resume_only_touches_updated_at(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """It must not enable a source the user disabled: resume means "try again", not "turn on"."""
    await client.put(f"{SOURCES_URL}/{STUB}", json={"enabled": True})
    await client.put(f"{SOURCES_URL}/{STUB}", json={"enabled": False})
    async with session_factory() as session:
        before = (await _aggregator(session, user_id, STUB)).updated_at

    body = (await client.post(f"{SOURCES_URL}/{STUB}/resume")).json()
    assert body["enabled"] is False

    async with session_factory() as session:
        row = await _aggregator(session, user_id, STUB)
        assert row.enabled is False
        assert row.updated_at > before
