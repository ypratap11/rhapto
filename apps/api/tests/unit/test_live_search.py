from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.live import LIVE_CAP, LiveTarget, live_search
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo

SPEC = SearchSpec(keywords=("program manager",))


def _posting(n: int, **kwargs: object) -> Posting:
    data = {
        "external_id": f"e{n}",
        "company": "ExampleCo",
        "title": f"Program Manager {n}",
        "location": "Denver, CO",
        "url": f"https://example.com/{n}",
        "jd_text": f"Program {n}. " * 20,
    }
    data.update(kwargs)
    return Posting(**data)  # type: ignore[arg-type]


class Alpha:
    info = SourceInfo("live-alpha", "aggregator", "Alpha", False)
    result: object = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        value = type(self).result
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return await value()
        return list(value)  # type: ignore[arg-type]


class Beta(Alpha):
    info = SourceInfo("live-beta", "aggregator", "Beta", False)
    result: object = []


@pytest.fixture(autouse=True)
def live_sources():  # type: ignore[no-untyped-def]
    SOURCES["live-alpha"] = Alpha  # type: ignore[assignment]
    SOURCES["live-beta"] = Beta  # type: ignore[assignment]
    yield
    SOURCES.pop("live-alpha", None)
    SOURCES.pop("live-beta", None)
    Alpha.result = []
    Beta.result = []


TARGETS = [LiveTarget(source="live-alpha"), LiveTarget(source="live-beta")]


async def test_new_postings_are_stored_unscored_with_no_search_id(
    session: AsyncSession, user: User
) -> None:
    Alpha.result = [_posting(1, salary_text="$150k")]
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    assert {j.external_id for j in result.jobs} == {"e1", "e2"}
    assert all(j.search_id is None and j.best_fit is None for j in result.jobs)
    assert {j.salary_text for j in result.jobs} == {"$150k", None}
    assert result.per_source["live-alpha"].found == 1 and result.per_source["live-alpha"].new == 1
    assert result.per_source["live-beta"].found == 1 and result.per_source["live-beta"].new == 1
    assert len(result.new_job_ids) == 2


async def test_an_identity_match_returns_the_existing_scored_job(
    session: AsyncSession, user: User
) -> None:
    existing = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="greenhouse",
        external_id="old",
        company="ExampleCo",
        title="Program Manager 1",
        location="Denver, CO",
        url="https://gh.example/old",
        jd_text="different text " * 20,
        posted_at=None,
        identity_hash=identity_hash("ExampleCo", "Program Manager 1", "Denver, CO"),
        repost_of=None,
    )
    existing.best_fit = 82
    await session.flush()
    Alpha.result = [_posting(1)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    # Opposite of the poller: a live search shows the job the user already has (with its score)
    # rather than inserting a repost row the moment they type a query.
    assert [j.id for j in result.jobs] == [existing.id]
    assert result.jobs[0].best_fit == 82
    assert result.new_job_ids == []
    assert result.per_source["live-alpha"].new == 0


async def test_a_timeout_is_reported_not_raised(session: AsyncSession, user: User) -> None:
    async def never() -> list[Posting]:
        await asyncio.sleep(30)
        return []

    Alpha.result = never
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS, timeout=0.05
    )
    assert result.per_source["live-alpha"].error is not None
    assert "timed out" in result.per_source["live-alpha"].error
    assert result.per_source["live-beta"].new == 1
    assert [j.external_id for j in result.jobs] == ["e2"]


async def test_a_source_error_is_reported_not_raised(session: AsyncSession, user: User) -> None:
    Alpha.result = SourceError("Alpha: check the API key")
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    assert result.per_source["live-alpha"].error == "Alpha: check the API key"
    assert len(result.jobs) == 1


async def test_each_source_is_capped(session: AsyncSession, user: User) -> None:
    Alpha.result = [_posting(n) for n in range(LIVE_CAP + 20)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert len(result.jobs) == LIVE_CAP
    assert result.per_source["live-alpha"].found == LIVE_CAP


async def test_posted_within_drops_old_postings_but_keeps_undated_ones(
    session: AsyncSession, user: User
) -> None:
    from datetime import UTC, datetime, timedelta

    old = _posting(1, posted_at=datetime.now(UTC) - timedelta(days=40))
    fresh = _posting(2, posted_at=datetime.now(UTC))
    undated = _posting(3)
    Alpha.result = [old, fresh, undated]
    spec = SearchSpec(keywords=("program manager",), posted_within="30d")
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=spec, targets=[TARGETS[0]]
    )
    assert {j.external_id for j in result.jobs} == {"e2", "e3"}


async def test_posted_within_90d_drops_old_postings_but_keeps_undated_ones(
    session: AsyncSession, user: User
) -> None:
    from datetime import UTC, datetime, timedelta

    old = _posting(1, posted_at=datetime.now(UTC) - timedelta(days=120))
    fresh = _posting(2, posted_at=datetime.now(UTC) - timedelta(days=80))
    undated = _posting(3)
    Alpha.result = [old, fresh, undated]
    spec = SearchSpec(keywords=("program manager",), posted_within="90d")
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=spec, targets=[TARGETS[0]]
    )
    assert {j.external_id for j in result.jobs} == {"e2", "e3"}


async def test_results_are_ordered_scored_first(session: AsyncSession, user: User) -> None:
    scored = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="greenhouse",
        external_id="old",
        company="ExampleCo",
        title="Program Manager 1",
        location="Denver, CO",
        url="https://gh.example/old",
        jd_text="different " * 20,
        posted_at=None,
        identity_hash=identity_hash("ExampleCo", "Program Manager 1", "Denver, CO"),
        repost_of=None,
    )
    scored.best_fit = 70
    await session.flush()
    Alpha.result = [_posting(2), _posting(1)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert result.jobs[0].id == scored.id
    assert result.jobs[1].best_fit is None


# --- T6: outcome kinds, board budget, mixed boards, quota guard --------------------------------
class BoardSrc:
    """A board source whose behaviour is chosen per board slug."""

    info = SourceInfo("live-board", "board", "Live board", True)
    behaviours: dict[str, object] = {}

    async def fetch(self, http, *, board, keywords):  # type: ignore[no-untyped-def]
        value = type(self).behaviours.get(board, [])
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return await value()
        return list(value)  # type: ignore[arg-type]


class Blocked:
    info = SourceInfo(
        "live-blocked",
        "aggregator",
        "Blocked",
        False,
        unavailable="blocked by the vendor (bot protection), not available right now",
    )
    calls = 0

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        type(self).calls += 1
        return [_posting(99)]


@pytest.fixture(autouse=True)
def t6_sources():  # type: ignore[no-untyped-def]
    SOURCES["live-board"] = BoardSrc  # type: ignore[assignment]
    SOURCES["live-blocked"] = Blocked  # type: ignore[assignment]
    BoardSrc.behaviours = {}
    Blocked.calls = 0
    yield
    SOURCES.pop("live-board", None)
    SOURCES.pop("live-blocked", None)


def _boards(*names: str) -> list[LiveTarget]:
    return [LiveTarget(source="live-board", board=n, company=f"Co {n}") for n in names]


async def test_first_board_errors_later_boards_succeed_reports_partial_with_counts(
    session: AsyncSession, user: User
) -> None:
    """[BR] The exact regression: board 1's error used to label the whole source failed."""
    BoardSrc.behaviours = {
        "b1": SourceError("b1 returned HTTP 500"),
        "b2": [_posting(1), _posting(2)],
        "b3": [_posting(3)],
    }
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1", "b2", "b3")
    )
    outcome = result.per_source["live-board"]
    assert outcome.found == 3 and outcome.new == 3
    assert outcome.state == "partial"
    assert outcome.error is None
    assert outcome.boards_ok == 2
    assert [f.name for f in outcome.failures] == ["Co b1"]
    assert outcome.failures[0].kind == "failed"


async def test_all_boards_fail_generic_failed_with_n_boards_message(
    session: AsyncSession, user: User
) -> None:
    BoardSrc.behaviours = {"b1": SourceError("one broke"), "b2": SourceError("two broke")}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1", "b2")
    )
    outcome = result.per_source["live-board"]
    assert outcome.state == "failed"
    assert outcome.error == "2 boards failed: Co b1 one broke; Co b2 two broke"
    assert outcome.found == 0


async def test_single_failure_error_is_the_message(session: AsyncSession, user: User) -> None:
    BoardSrc.behaviours = {"b1": SourceError("one broke")}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1")
    )
    assert result.per_source["live-board"].error == "one broke"
    assert result.per_source["live-board"].state == "failed"


async def test_all_boards_rate_limited_state(session: AsyncSession, user: User) -> None:
    from rhapto.services.discovery.errors import RateLimited

    BoardSrc.behaviours = {"b1": RateLimited("x"), "b2": RateLimited("y")}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1", "b2")
    )
    assert result.per_source["live-board"].state == "rate_limited"


async def test_rate_limited_and_failed_mix_is_failed(session: AsyncSession, user: User) -> None:
    from rhapto.services.discovery.errors import RateLimited

    BoardSrc.behaviours = {"b1": RateLimited("x"), "b2": SourceError("y")}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1", "b2")
    )
    assert result.per_source["live-board"].state == "failed"


async def test_all_ok_has_no_failure_text(session: AsyncSession, user: User) -> None:
    BoardSrc.behaviours = {"b1": [_posting(1)], "b2": [_posting(2)]}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1", "b2")
    )
    outcome = result.per_source["live-board"]
    assert outcome.state == "ok" and outcome.error is None and outcome.failures == []
    assert outcome.boards_ok == 2


async def test_message_capped_at_300_chars(session: AsyncSession, user: User) -> None:
    names = [f"board{n}" for n in range(12)]
    BoardSrc.behaviours = {n: SourceError("boom " * 20) for n in names}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards(*names)
    )
    error = result.per_source["live-board"].error
    assert error is not None and len(error) <= 300 and error.startswith("12 boards failed:")


async def test_rate_limited_aggregator_reports_rate_limited_state_and_wording(
    session: AsyncSession, user: User
) -> None:
    from rhapto.services.discovery.errors import RateLimited

    Alpha.result = RateLimited("http://x returned HTTP 429")
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    alpha = result.per_source["live-alpha"]
    assert alpha.state == "rate_limited"
    assert alpha.error == "rate-limited (quota used up, try again later)"
    assert "429" not in (alpha.error or "")
    assert result.per_source["live-beta"].state == "ok"


async def test_other_http_error_keeps_failure_wording(session: AsyncSession, user: User) -> None:
    Alpha.result = SourceError("Alpha: HTTP 500", status=500)
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert result.per_source["live-alpha"].state == "failed"
    assert result.per_source["live-alpha"].error == "Alpha: HTTP 500"


async def test_board_gets_board_budget_aggregator_gets_short_one(
    session: AsyncSession, user: User
) -> None:
    async def slow(delay: float):  # type: ignore[no-untyped-def]
        await asyncio.sleep(delay)
        return [_posting(int(delay * 1000))]

    BoardSrc.behaviours = {
        "fast": lambda: slow(0.15),
        "slow": lambda: slow(0.5),
    }
    Alpha.result = lambda: slow(0.15)
    result = await live_search(
        session,
        user.id,
        http=FakeDiscoveryHttp({}),
        spec=SPEC,
        targets=[*_boards("fast", "slow"), LiveTarget(source="live-alpha")],
        timeout=0.05,
        board_timeout=0.3,
    )
    assert result.per_source["live-alpha"].error == "timed out after 0.05s"
    board = result.per_source["live-board"]
    assert board.state == "partial" and board.boards_ok == 1
    assert [(f.name, f.message) for f in board.failures] == [("Co slow", "timed out after 0.3s")]


async def test_board_outlives_the_aggregator_timeout_by_default(
    session: AsyncSession, user: User
) -> None:
    """[BR] Behavioural twin: only `timeout` is passed; a board slower than it must still succeed."""

    async def slow():  # type: ignore[no-untyped-def]
        await asyncio.sleep(0.15)
        return [_posting(1)]

    BoardSrc.behaviours = {"b1": slow}
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=_boards("b1"), timeout=0.05
    )
    assert result.per_source["live-board"].found == 1
    assert result.per_source["live-board"].error is None


def test_board_timeout_constant() -> None:
    from rhapto.services.discovery.live import BOARD_TIMEOUT_SECONDS, LIVE_TIMEOUT_SECONDS

    assert BOARD_TIMEOUT_SECONDS == 30.0 and LIVE_TIMEOUT_SECONDS == 8.0


async def test_unavailable_source_makes_no_http_call(session: AsyncSession, user: User) -> None:
    http = FakeDiscoveryHttp({})
    result = await live_search(
        session,
        user.id,
        http=http,
        spec=SPEC,
        targets=[LiveTarget(source="live-blocked"), LiveTarget(source="live-alpha")],
    )
    outcome = result.per_source["live-blocked"]
    assert Blocked.calls == 0 and http.calls == []
    assert outcome.state == "unavailable"
    assert outcome.error == "blocked by the vendor (bot protection), not available right now"
    assert outcome.found == 0


JSEARCH_CREDS = {"rapidapi_key": "rk-test-key-123"}


def _jsearch_http(**headers: str):  # type: ignore[no-untyped-def]
    import json
    from pathlib import Path

    from rhapto.services.discovery.http import FakeResponse

    body = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "jsearch_v2_response.json").read_text(
            encoding="utf-8"
        )
    )
    return FakeDiscoveryHttp(
        {"jsearch.p.rapidapi.com": FakeResponse(status=200, body=body, headers=headers)}
    )


async def test_jsearch_exhausted_makes_no_http_call_in_live_search(
    session: AsyncSession, user: User
) -> None:
    from datetime import UTC, datetime, timedelta

    from rhapto.services.discovery.quota import InMemoryQuotaStore, QuotaState

    store = InMemoryQuotaStore()
    reset = datetime.now(UTC) + timedelta(hours=2)
    await store.put("jsearch", JSEARCH_CREDS["rapidapi_key"], QuotaState(200, 0, reset))
    http = _jsearch_http()
    result = await live_search(
        session,
        user.id,
        http=http,
        spec=SPEC,
        targets=[LiveTarget(source="jsearch", credentials=JSEARCH_CREDS)],
        quota_store=store,
    )
    outcome = result.per_source["jsearch"]
    assert http.calls == []
    assert outcome.state == "quota_exhausted"
    assert outcome.error is not None and outcome.error.startswith("quota used up until ")
    assert outcome.quota is not None and outcome.quota.remaining == 0


async def test_jsearch_success_surfaces_remaining_quota(session: AsyncSession, user: User) -> None:
    from rhapto.services.discovery.quota import InMemoryQuotaStore

    http = _jsearch_http(
        **{
            "x-ratelimit-requests-remaining": "187",
            "x-ratelimit-requests-limit": "200",
            "x-ratelimit-requests-reset": "3600",
        }
    )
    result = await live_search(
        session,
        user.id,
        http=http,
        spec=SPEC,
        targets=[LiveTarget(source="jsearch", credentials=JSEARCH_CREDS)],
        quota_store=InMemoryQuotaStore(),
    )
    outcome = result.per_source["jsearch"]
    assert outcome.state == "ok" and outcome.found > 0
    assert outcome.quota is not None
    assert (outcome.quota.limit, outcome.quota.remaining) == (200, 187)


async def test_jsearch_429_without_reset_is_rate_limited_generic(
    session: AsyncSession, user: User
) -> None:
    from rhapto.services.discovery.http import FakeResponse
    from rhapto.services.discovery.quota import InMemoryQuotaStore

    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": FakeResponse(status=429)})
    result = await live_search(
        session,
        user.id,
        http=http,
        spec=SPEC,
        targets=[LiveTarget(source="jsearch", credentials=JSEARCH_CREDS)],
        quota_store=InMemoryQuotaStore(),
    )
    outcome = result.per_source["jsearch"]
    assert outcome.state == "rate_limited"
    assert outcome.error == "rate-limited (quota used up, try again later)"
