from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo


async def _add(
    factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    *,
    company: str | None,
    title: str,
    fit: int | None,
) -> str:
    async with factory() as session:
        job = await jobs_repo.create_job(
            session,
            user_id,
            jd_text=f"{company} {title} " + "describes the work in detail. " * 4,
            company=company,
            title=title,
        )
        job.best_fit = fit
        job.best_track_id = "t" if fit is not None else None
        await session.commit()
        return str(job.id)


async def _seed_six_copies(
    factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> tuple[list[str], str]:
    copies = [
        await _add(factory, user_id, company="Acme", title=f"Senior Engineer (R{5800 + n})", fit=70)
        for n in range(6)
    ]
    other = await _add(factory, user_id, company="Other Co", title="Designer", fit=60)
    return copies, other


async def test_six_copies_collapse_to_one_row_carrying_the_other_five_ids(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    copies, other = await _seed_six_copies(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs")).json()  # default sort=relevance
    assert len(rows) == 2
    acme = next(r for r in rows if r["company"] == "Acme")
    assert len(acme["also_ids"]) == 5
    assert {acme["id"], *acme["also_ids"]} == set(copies)
    assert next(r for r in rows if r["id"] == other)["also_ids"] == []


async def test_ids_request_is_never_arranged(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """Live search re-fetches exactly the rows it just returned, by id, with the user's sort."""
    copies, _ = await _seed_six_copies(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs", params={"ids": ",".join(copies)})).json()
    assert sorted(r["id"] for r in rows) == sorted(copies)
    assert all(r["also_ids"] == [] for r in rows)


async def test_other_sorts_are_untouched(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    await _seed_six_copies(session_factory, user_id)
    for sort in ("newest", "fit"):
        rows = (await client.get("/api/v1/jobs", params={"sort": sort})).json()
        assert len(rows) == 7 and all(r["also_ids"] == [] for r in rows), sort


async def test_a_third_row_of_a_company_sorts_after_the_others_first_two(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    s = [
        await _add(session_factory, user_id, company="Shield AI", title=f"Role {n}", fit=90 - n)
        for n in range(4)
    ]  # fits 90, 89, 88, 87
    o = [
        await _add(session_factory, user_id, company="Other Co", title=f"Job {n}", fit=50 - n)
        for n in range(2)
    ]  # fits 50, 49
    rows = (await client.get("/api/v1/jobs")).json()
    assert [r["id"] for r in rows] == [s[0], s[1], o[0], o[1], s[2], s[3]]


async def test_dashboard_recommended_sorted_by_fit_is_arranged_and_floored(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    """The dashboard asks for sort=fit (not relevance), so keying arrange on relevance alone would
    leave it flooded. It also drops scored jobs at or below the title-miss cap. Company 'Shield AI' has three rows above the cap: the third (fit 70) is deferred behind the other above-cap rows but still precedes the unscored one (owner decision, plan review I-1)."""
    s = [
        await _add(session_factory, user_id, company="Shield AI", title=f"Role {n}", fit=fit)
        for n, fit in enumerate((90, 80, 70))
    ]
    other = await _add(session_factory, user_id, company="Other Co", title="Job", fit=50)
    await _add(session_factory, user_id, company="Low Co", title="Capped", fit=45)  # excluded
    edge = await _add(session_factory, user_id, company="Edge Co", title="Edge", fit=46)
    unscored = await _add(session_factory, user_id, company="New Co", title="Fresh", fit=None)
    rows = (await client.get("/api/v1/jobs", params={"recommended": "true", "sort": "fit"})).json()
    assert [r["id"] for r in rows] == [s[0], s[1], other, edge, s[2], unscored]


async def test_missing_company_is_never_collapsed_or_capped(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ids = [
        await _add(session_factory, user_id, company=company, title="Engineer", fit=80 - n)
        for n, company in enumerate((None, None, None, None, "  ", ""))
    ]
    rows = (await client.get("/api/v1/jobs")).json()
    assert [r["id"] for r in rows] == ids  # all six, in fit order, none collapsed, none moved
    assert all(r["also_ids"] == [] for r in rows)
