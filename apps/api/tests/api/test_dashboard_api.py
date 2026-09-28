from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.models.profile.tracks import Track
from rhapto.services.discovery.sources.status import keyless_source_names
from rhapto.services.storage import PackageStorage


async def test_an_empty_account_reports_zeroes_and_an_empty_checklist(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["new_fit_count"] == 0 and body["needs_review_count"] == 0
    assert body["saved_searches"] == [] and body["due_followups"] == []
    assert body["checklist"] == {
        "resume_template": False,
        "contact_answers": False,
        "tracks": False,
        "blocks_verified": False,
        "guardrails": False,
        "location_preferences": False,
        "verified_blocks": 0,
        "total_blocks": 0,
        # The suite runs in token mode, which is the single-account self-hoster: the environment's
        # key IS theirs, so no cap applies and the source is "env", not "trial". A brand-new account
        # on a hosted instance (`access` mode) gets "trial" with a countdown instead --
        # `test_llm_setup_status.py` drives all eight states.
        "llm_key": True,
        "llm_key_source": "env",
        "trial_runs_left": None,
        # `ensure_account` seeds an enabled row for every keyless source, so a brand-new account can
        # actually poll something -- and the row the poller reads is the row Settings shows. Counted
        # from the registry rather than hard-coded, so adding a keyless source does not make this a
        # false expectation.
        "job_sources": True,
        "usable_sources": len(keyless_source_names()),
        "saved_searches": False,
        "active_searches": 0,
        "jobs_found": False,
        "dateless_blocks": 0,
    }


async def test_the_checklist_reads_the_imported_profile(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    checklist = (await client.get("/api/v1/dashboard")).json()["checklist"]
    assert checklist["contact_answers"] is True
    assert checklist["tracks"] is True
    assert checklist["guardrails"] is True
    assert checklist["location_preferences"] is True
    assert checklist["total_blocks"] > 0
    assert checklist["blocks_verified"] is (checklist["verified_blocks"] > 0)
    # No .docx was uploaded by the importer.
    assert checklist["resume_template"] is False


async def test_an_uploaded_document_completes_the_resume_step(
    client: httpx.AsyncClient,
) -> None:
    from helpers_docx import build_fixture_docx

    files = {
        "file": (
            "cv.docx",
            build_fixture_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    assert (await client.post("/api/v1/profile/resume-document", files=files)).status_code == 201
    checklist = (await client.get("/api/v1/dashboard")).json()["checklist"]
    assert checklist["resume_template"] is True


async def test_a_row_whose_file_has_vanished_does_not_count_as_uploaded(
    client: httpx.AsyncClient, storage: PackageStorage
) -> None:
    """The row and the file can disagree, and the row is the one that survives losing a volume.

    This happened in production: the `resume_documents` row outlived its file by three days, the
    checklist read the row alone and reported the step complete, and the owner only found out when
    he pressed Tailor -- the one moment the product had his attention for something else.
    `documents.load_source` already treats a vanished file as "no document"; the checklist has to
    agree with it, or the product contradicts itself.
    """
    from helpers_docx import build_fixture_docx

    files = {
        "file": (
            "cv.docx",
            build_fixture_docx(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    assert (await client.post("/api/v1/profile/resume-document", files=files)).status_code == 201
    assert (await client.get("/api/v1/dashboard")).json()["checklist"]["resume_template"] is True

    # Lose the file the way a volume migration loses it: the row stays, the bytes do not.
    shutil.rmtree(storage.root / "resume-document", ignore_errors=True)

    checklist = (await client.get("/api/v1/dashboard")).json()["checklist"]
    assert checklist["resume_template"] is False, (
        "the checklist still reports an uploaded template while the file is gone; tune mode will "
        "refuse to run and the user has been told they are ready"
    )


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
    # `ever_found` is False even though a job carries this `search_id`: there is no `poll_runs`
    # row, and the run history is the only honest record of what a poll ever returned. A job row
    # can arrive by backfill or be detached by a delete, which is why the job-row proxy was
    # rejected for this question.
    # `runs: 0` is the other half, and it is why the rail does not label this "Never matched": the
    # search has not been polled, which is a different state from polled-and-found-nothing.
    assert body["saved_searches"] == [
        {
            "id": created["id"],
            "name": "program manager",
            "new_count": 1,
            "ever_found": False,
            "runs": 0,
        }
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


#: The dashboard's statement budget. Ten, itemised, because a magic number that only ever goes up
#: is not a guard:
#:   1 checklist composite (now carrying four more scalar subqueries: the usable-jobs EXISTS, the
#:     dateless-blocks COUNT, the active-searches COUNT and `users.trial_runs_used`)
#:   2 answers read -- has to come back whole, two rows test different keys
#:   3 new_counts        4 list_searches        5 due_followups
#:   6 new_fit_count     7 needs_review_count
#:   8 llm_settings row -- must come back as a row; the ciphertext is decrypted in Python, and
#:     `llm_setup_status` takes `runs_used` from the checklist composite so it needs no second read
#:   9 aggregators LEFT JOIN source_credentials -- one statement for every source
#:  10 search_run_stats -- one grouped read of poll_runs for every saved search
#: None of the three new ones folds into another: 8 returns a row this process must decrypt, and 9
#: and 10 are aggregates over different tables at different grains.
MAX_DASHBOARD_SELECTS = 10


async def test_the_dashboard_is_at_most_ten_selects(
    client: httpx.AsyncClient, imported_profile: None, select_counter: list[str]
) -> None:
    select_counter.clear()
    assert (await client.get("/api/v1/dashboard")).status_code == 200
    assert len(select_counter) <= MAX_DASHBOARD_SELECTS, "\n".join(select_counter)


async def test_the_dashboard_issues_the_same_selects_with_one_and_five_searches(
    client: httpx.AsyncClient, imported_profile: None, select_counter: list[str]
) -> None:
    """The real guard, and the one raising a constant cannot satisfy.

    A count cap catches an N+1 only until someone raises the number. This asserts the request does
    not grow with the data, which is the property the cap was written to protect. Every value this
    branch added is either a scalar subquery on an existing statement or one grouped aggregate over
    the whole set -- never a read per row.
    """
    await client.post(
        "/api/v1/searches",
        json={"query": "search 0", "location": None, "remote": "include", "active": True},
    )
    select_counter.clear()
    assert (await client.get("/api/v1/dashboard")).status_code == 200
    with_one = len(select_counter)

    for i in range(1, 5):
        await client.post(
            "/api/v1/searches",
            json={"query": f"search {i}", "location": None, "remote": "include", "active": True},
        )
    assert len((await client.get("/api/v1/searches")).json()) == 5
    select_counter.clear()
    assert (await client.get("/api/v1/dashboard")).status_code == 200
    with_five = len(select_counter)

    assert with_one == with_five, (
        f"{with_one} SELECT(s) with 1 saved search, {with_five} with 5:\n"
        + "\n".join(select_counter)
    )
