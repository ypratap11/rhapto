from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.models.profile.tracks import Track


async def test_an_empty_account_reports_zeroes_and_an_empty_checklist(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["new_fit_count"] == 0 and body["needs_review_count"] == 0
    assert body["saved_searches"] == [] and body["due_followups"] == []
    assert body["checklist"] == {
        "resume_template": False,
        "contact": False,
        "tracks": False,
        "blocks_verified": False,
        "guardrails": False,
        "location": False,
        "verified_blocks": 0,
        "total_blocks": 0,
    }


async def test_the_checklist_reads_the_imported_profile(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    checklist = (await client.get("/api/v1/dashboard")).json()["checklist"]
    assert checklist["contact"] is True
    assert checklist["tracks"] is True
    assert checklist["guardrails"] is True
    assert checklist["location"] is True
    assert checklist["total_blocks"] > 0
    assert checklist["blocks_verified"] is (checklist["verified_blocks"] > 0)
    # No .docx was uploaded by the importer.
    assert checklist["resume_template"] is False


async def test_new_fit_count_respects_the_track_threshold_and_the_window(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await profile_repo.upsert_track(
            session,
            user_id,
            Track(id="tpm", name="TPM", resume_base="b", min_fit=60, keywords=["tpm"]),
        )
        now = datetime.now(UTC)
        for key, fit, age, extra in [
            ("good", 80, 1, {}),
            ("weak", 40, 1, {}),
            ("stale", 90, 30, {}),
            ("hidden", 90, 1, {"hidden_at": now}),
            ("gone", 90, 1, {"unlisted_at": now}),
        ]:
            job = await jobs_repo.create_discovered_job(
                session,
                user_id,
                source="themuse",
                external_id=key,
                company="ExampleCo",
                title=key,
                location=None,
                url=f"https://example.com/{key}",
                jd_text="x" * 80,
                posted_at=None,
                identity_hash=f"h-{key}",
                repost_of=None,
            )
            job.best_track_id, job.best_fit = "tpm", fit
            job.discovered_at = now - timedelta(days=age)
            for attr, value in extra.items():
                setattr(job, attr, value)
        await session.commit()
    assert (await client.get("/api/v1/dashboard")).json()["new_fit_count"] == 1


async def test_needs_review_counts_unarchived_drafts_on_visible_jobs(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    assert (await client.get("/api/v1/dashboard")).json()["needs_review_count"] == 1
    await client.post(f"/api/v1/packages/{tailored_package['id']}/archive")
    assert (await client.get("/api/v1/dashboard")).json()["needs_review_count"] == 0


async def test_saved_searches_carry_their_new_counts(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    created = (await client.post("/api/v1/searches", json={"query": "program manager"})).json()
    async with session_factory() as session:
        await jobs_repo.create_discovered_job(
            session,
            user_id,
            source="themuse",
            external_id="s1",
            company="ExampleCo",
            title="PM",
            location=None,
            url="https://example.com/s1",
            jd_text="x" * 80,
            posted_at=None,
            identity_hash="h-s1",
            repost_of=None,
            search_id=uuid.UUID(created["id"]),
        )
        await session.commit()
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["saved_searches"] == [
        {"id": created["id"], "name": "program manager", "new_count": 1}
    ]


async def test_due_followups_are_today_or_earlier_soonest_first(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ids = []
    for key, offset in [("overdue", -3), ("today", 0), ("later", 5)]:
        job = (
            await client.post(
                "/api/v1/jobs",
                json={
                    "jd_text": f"Technical program manager {key}. " * 5,
                    "company": "ExampleCo",
                    "title": key,
                },
            )
        ).json()
        application = (await client.post("/api/v1/applications", json={"job_id": job["id"]})).json()
        await client.patch(
            f"/api/v1/applications/{application['id']}",
            json={"follow_up_at": (datetime.now(UTC) + timedelta(days=offset)).isoformat()},
        )
        ids.append((key, application["id"]))
    due = (await client.get("/api/v1/dashboard")).json()["due_followups"]
    assert [d["application_id"] for d in due] == [ids[0][1], ids[1][1]]
    assert due[0]["job"]["title"] == "overdue"


async def test_the_dashboard_is_at_most_eight_selects(
    client: httpx.AsyncClient, imported_profile: None, select_counter: list[str]
) -> None:
    select_counter.clear()
    assert (await client.get("/api/v1/dashboard")).status_code == 200
    assert len(select_counter) <= 8, "\n".join(select_counter)
