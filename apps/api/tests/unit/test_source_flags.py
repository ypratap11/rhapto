"""T4: SourceInfo flags (unavailable, live_only), poller guards, and 429 vs API-key wording."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Aggregator, User
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.discovery.errors import RateLimited, SourceError
from rhapto.services.discovery.http import FakeDiscoveryHttp, FakeResponse
from rhapto.services.discovery.poller import SourceSpec, build_specs, poll_sources
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import aggregator_sources, get_aggregator
from rhapto.services.discovery.sources.status import keyless_source_names, usable_source_ids

JOOBLE_KEY = "jk-7f3a9d41"
ADZUNA_ID = "aid-5b2c8e17"
ADZUNA_KEY = "akey-91d4f0a6"
SPEC = SearchSpec(keywords=("program manager",), location="Denver, CO")


class _Row:
    enabled = True


def test_keyless_names_exclude_themuse() -> None:
    names = keyless_source_names()
    assert "themuse" not in names
    assert "remotive" in names


def test_usable_source_ids_excludes_unavailable_includes_live_only() -> None:
    rows = {"themuse": _Row(), "jsearch": _Row(), "remotive": _Row()}
    usable = usable_source_ids(rows, {"jsearch"}, aggregator_sources())
    assert "themuse" not in usable
    assert "jsearch" in usable
    assert "remotive" in usable


async def _seed_searches(session: AsyncSession, user: User, n: int) -> None:
    await profile_repo.upsert_track(
        session,
        user.id,
        Track(
            id="data-pm",
            name="Data",
            resume_base="b",
            min_fit=60,
            keywords=[f"kw{i}" for i in range(n)],
            description="d",
        ),
    )
    await session.flush()


async def test_build_specs_skips_unavailable_source(session: AsyncSession, user: User) -> None:
    await _seed_searches(session, user, 3)
    session.add(Aggregator(user_id=user.id, source="themuse", enabled=True, keywords=["pm"]))
    session.add(Aggregator(user_id=user.id, source="remotive", enabled=True, keywords=["pm"]))
    await session.flush()
    specs = await build_specs(session, user.id)
    assert specs
    assert {s.source for s in specs} == {"remotive"}


async def test_build_specs_skips_live_only_source_saved_search_path(
    session: AsyncSession, user: User
) -> None:
    fernet = Fernet(Fernet.generate_key())
    await _seed_searches(session, user, 3)
    session.add(Aggregator(user_id=user.id, source="jsearch", enabled=True, keywords=[]))
    session.add(Aggregator(user_id=user.id, source="remotive", enabled=True, keywords=[]))
    await creds_repo.put_credentials(session, fernet, user.id, "jsearch", {"rapidapi_key": "rk"})
    await session.flush()
    specs = await build_specs(session, user.id, fernet=fernet)
    assert any(s.search_id is not None for s in specs)
    assert "jsearch" not in {s.source for s in specs}


async def test_build_specs_skips_live_only_source_legacy_path(
    session: AsyncSession, user: User
) -> None:
    fernet = Fernet(Fernet.generate_key())
    session.add(Aggregator(user_id=user.id, source="jsearch", enabled=True, keywords=["pm"]))
    session.add(Aggregator(user_id=user.id, source="remotive", enabled=True, keywords=["pm"]))
    await creds_repo.put_credentials(session, fernet, user.id, "jsearch", {"rapidapi_key": "rk"})
    await session.flush()
    assert await profile_repo.list_tracks(session, user.id) == []
    specs = await build_specs(session, user.id, fernet=fernet)
    assert {s.source for s in specs} == {"remotive"}


async def test_poll_makes_zero_jsearch_requests(session: AsyncSession, user: User) -> None:
    fernet = Fernet(Fernet.generate_key())
    await _seed_searches(session, user, 18)
    session.add(Aggregator(user_id=user.id, source="jsearch", enabled=True, keywords=[]))
    await creds_repo.put_credentials(session, fernet, user.id, "jsearch", {"rapidapi_key": "rk"})
    await session.flush()
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": {"data": []}})
    await poll_sources(
        session,
        user.id,
        http=http,
        embedder=FakeEmbeddingProvider(dimensions=384),
        fernet=fernet,
    )
    assert not [c for c in http.calls if "jsearch.p.rapidapi.com" in c]
    assert not [p for p in http.posts if "jsearch.p.rapidapi.com" in str(p)]
    assert await disc_repo.latest_runs(session, user.id) == []


async def test_poll_sources_refuses_explicit_live_only_spec(
    session: AsyncSession, user: User
) -> None:
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": {"data": []}})
    spec = SourceSpec(
        source="jsearch",
        board=None,
        company=None,
        keywords=["pm"],
        search=SearchSpec(keywords=("pm",)),
        credentials={"rapidapi_key": "rk"},
    )
    summary = await poll_sources(
        session,
        user.id,
        http=http,
        embedder=FakeEmbeddingProvider(dimensions=384),
        specs=[spec],
    )
    assert http.calls == []
    assert summary.results == []
    assert await disc_repo.latest_runs(session, user.id) == []


async def test_poll_sources_skips_unavailable_spec_without_call_or_run_row(
    session: AsyncSession, user: User
) -> None:
    http = FakeDiscoveryHttp({"themuse.com": {"results": [], "page_count": 1}})
    spec = SourceSpec(
        source="themuse",
        board=None,
        company=None,
        keywords=["pm"],
        search=SearchSpec(keywords=("pm",)),
    )
    summary = await poll_sources(
        session,
        user.id,
        http=http,
        embedder=FakeEmbeddingProvider(dimensions=384),
        specs=[spec],
    )
    assert http.calls == []
    assert summary.results == []
    assert await disc_repo.latest_runs(session, user.id) == []


@pytest.mark.parametrize("status", [429, 401, 403, 500])
@pytest.mark.parametrize("source", ["jooble", "adzuna"])
async def test_rate_limit_vs_api_key_vs_server_error(source: str, status: int) -> None:
    if source == "jooble":
        http = FakeDiscoveryHttp({"jooble.org": FakeResponse(status=status)})
        creds = {"api_key": JOOBLE_KEY}
        label = "Jooble"
        secrets = [JOOBLE_KEY]
    else:
        http = FakeDiscoveryHttp({"api.adzuna.com": FakeResponse(status=status)})
        creds = {"app_id": ADZUNA_ID, "app_key": ADZUNA_KEY}
        label = "Adzuna"
        secrets = [ADZUNA_ID, ADZUNA_KEY]
    with pytest.raises(SourceError) as caught:
        await get_aggregator(source).fetch_search(http, SPEC, creds)  # type: ignore[arg-type]
    exc = caught.value
    if status == 429:
        assert isinstance(exc, RateLimited)
        assert str(exc) == f"{label} rate-limited (quota used up, try again later)"
    else:
        assert not isinstance(exc, RateLimited)
        if status in (401, 403):
            assert "check the API key" in str(exc)
    for secret in secrets:
        assert secret not in str(exc)
        assert secret not in repr(exc)
        assert all(secret not in str(a) for a in exc.args)


@pytest.mark.parametrize("source", ["jooble", "adzuna"])
async def test_server_error_does_not_blame_the_api_key(source: str) -> None:
    if source == "jooble":
        http = FakeDiscoveryHttp({"jooble.org": FakeResponse(status=500)})
        creds = {"api_key": JOOBLE_KEY}
        secrets = [JOOBLE_KEY]
    else:
        http = FakeDiscoveryHttp({"api.adzuna.com": FakeResponse(status=500)})
        creds = {"app_id": ADZUNA_ID, "app_key": ADZUNA_KEY}
        secrets = [ADZUNA_ID, ADZUNA_KEY]
    with pytest.raises(SourceError) as caught:
        await get_aggregator(source).fetch_search(http, SPEC, creds)  # type: ignore[arg-type]
    message = str(caught.value)
    assert "API key" not in message and "HTTP 500" in message
    assert not isinstance(caught.value, RateLimited)
    assert caught.value.status == 500
    for secret in secrets:
        assert secret not in message and secret not in repr(caught.value)
