from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import SourceCredentialRow, User, WatchlistEntry
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as repo
from rhapto.db.repositories import source_credentials as creds_repo


@pytest.fixture
def fernet() -> Fernet:
    return Fernet(Fernet.generate_key())


async def test_search_crud_and_ordering(session: AsyncSession, user: User) -> None:
    first = await repo.create_search(
        session,
        user.id,
        name="Data",
        keywords=["data platform"],
        location="Denver, CO",
        remote="include",
        derived_from_track_id="data-pm",
    )
    second = await repo.create_search(
        session,
        user.id,
        name="AI",
        keywords=["LLM"],
        location=None,
        remote="only",
    )
    await session.commit()
    rows = await repo.list_searches(session, user.id)
    assert [r.id for r in rows] == [first.id, second.id]
    assert rows[0].active is True and rows[0].derived_from_track_id == "data-pm"
    assert await repo.get_search(session, user.id, second.id) is not None
    assert await repo.delete_search(session, user.id, second.id) is True
    assert await repo.delete_search(session, user.id, second.id) is False


async def test_update_clears_the_derived_link_when_the_criteria_change(
    session: AsyncSession, user: User
) -> None:
    row = await repo.create_search(
        session,
        user.id,
        name="Data",
        keywords=["data platform"],
        location=None,
        remote="include",
        derived_from_track_id="data-pm",
    )
    await repo.update_search(session, row, name="Data platform")
    assert row.derived_from_track_id == "data-pm"
    await repo.update_search(session, row, keywords=["ETL"])
    assert row.derived_from_track_id is None


async def test_credentials_round_trip_and_never_store_plaintext(
    session: AsyncSession, user: User, fernet: Fernet
) -> None:
    await creds_repo.put_credentials(
        session, fernet, user.id, "adzuna", {"app_id": "id-1", "app_key": "s3cret"}
    )
    await session.commit()
    assert await creds_repo.get_credentials(session, fernet, user.id, "adzuna") == {
        "app_id": "id-1",
        "app_key": "s3cret",
    }
    row = await session.scalar(
        select(SourceCredentialRow).where(SourceCredentialRow.user_id == user.id)
    )
    assert row is not None and "s3cret" not in row.credentials_encrypted
    await creds_repo.put_credentials(session, fernet, user.id, "adzuna", {"app_key": "new"})
    assert await creds_repo.get_credentials(session, fernet, user.id, "adzuna") == {
        "app_id": "id-1",
        "app_key": "new",
    }
    assert await creds_repo.credentialled_sources(session, user.id) == {"adzuna"}
    assert await creds_repo.get_credentials(session, fernet, user.id, "jooble") == {}


async def test_watchlist_discovered_defaults_false(session: AsyncSession, user: User) -> None:
    session.add(
        WatchlistEntry(user_id=user.id, company="ExampleCo", source="lever", board="exampleco")
    )
    await session.flush()
    row = await session.scalar(select(WatchlistEntry).where(WatchlistEntry.user_id == user.id))
    assert row is not None and row.discovered is False


async def test_deleting_a_search_nulls_the_job_link(session: AsyncSession, user: User) -> None:
    search = await repo.create_search(
        session, user.id, name="Data", keywords=["data"], location=None, remote="include"
    )
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="themuse",
        external_id="1",
        company="ExampleCo",
        title="TPM",
        location=None,
        url="https://example.com/1",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash="h",
        repost_of=None,
        search_id=search.id,
    )
    await session.commit()
    assert job.search_id == search.id
    await repo.delete_search(session, user.id, search.id)
    await session.commit()
    # `session.get()` on an object already resident in the identity map, after
    # `expire_all()`, hits a known SQLAlchemy async-ORM limitation (reload-on-expired-get
    # raises MissingGreenlet: https://github.com/sqlalchemy/sqlalchemy/discussions/6190) —
    # reproducible here with any model, unrelated to this repo. `refresh()` reloads the
    # same expired instance without hitting that path.
    await session.refresh(job)
    assert job.search_id is None
