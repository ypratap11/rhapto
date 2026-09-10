import uuid
from datetime import UTC, datetime

import httpx
from helpers import demo_extract, demo_resume

from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.package import ApplicationPackage, JobSnapshot

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


async def test_create_from_text_and_get(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/v1/jobs", json={"jd_text": JD, "company": "ExampleCo", "title": "Data Platform PM"}
    )
    assert response.status_code == 201, response.text
    job = response.json()
    assert (
        job["company"] == "ExampleCo"
        and job["source"] == "manual"
        and job["latest_package"] is None
    )
    assert job["application_status"] is None and job["extracted"] is None
    fetched = await client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.status_code == 200 and fetched.json()["jd_text"] == JD


async def test_duplicate_text_is_409_with_existing_id(client: httpx.AsyncClient) -> None:
    first = await client.post("/api/v1/jobs", json={"jd_text": JD})
    second = await client.post("/api/v1/jobs", json={"jd_text": "  " + JD.upper() + "\n"})
    assert second.status_code == 409
    assert second.json()["existing_job_id"] == first.json()["id"]


async def test_create_from_url_uses_fetcher(
    client: httpx.AsyncClient, fetched_text: dict[str, str]
) -> None:
    fetched_text["text"] = JD
    response = await client.post("/api/v1/jobs", json={"url": "https://example.com/jobs/1"})
    assert response.status_code == 201 and response.json()["url"] == "https://example.com/jobs/1"
    assert response.json()["jd_text"] == JD


async def test_url_fetch_failure_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/jobs", json={"url": "https://example.com/missing"})
    assert response.status_code == 422 and "404" in response.json()["detail"]


async def test_requires_exactly_one_of_text_or_url(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/jobs", json={})).status_code == 422
    assert (
        await client.post("/api/v1/jobs", json={"jd_text": JD, "url": "https://x.example"})
    ).status_code == 422
    assert (await client.post("/api/v1/jobs", json={"jd_text": "short"})).status_code == 422


async def test_list_and_search_newest_first(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/jobs", json={"jd_text": JD, "company": "ExampleCo", "title": "Data PM"}
    )
    await client.post(
        "/api/v1/jobs",
        json={
            "jd_text": "Beta Labs wants an AI Product Manager who has shipped LLM features. " * 3,
            "company": "Beta Labs",
            "title": "AI PM",
        },
    )
    listed = (await client.get("/api/v1/jobs")).json()
    assert [j["company"] for j in listed] == ["Beta Labs", "ExampleCo"]
    assert [
        j["company"]
        for j in (await client.get("/api/v1/jobs", params={"search": "snowflake"})).json()
    ] == ["ExampleCo"]


async def test_delete(client: httpx.AsyncClient) -> None:
    job_id = (await client.post("/api/v1/jobs", json={"jd_text": JD})).json()["id"]
    assert (await client.delete(f"/api/v1/jobs/{job_id}")).status_code == 204
    assert (await client.get(f"/api/v1/jobs/{job_id}")).status_code == 404
    assert (await client.delete(f"/api/v1/jobs/{job_id}")).status_code == 404


def _other_package(jd_text: str) -> ApplicationPackage:
    return ApplicationPackage(
        job=JobSnapshot(company="Other Co", title="Other Role", jd_text=jd_text),
        track_id="data-pm",
        jd_extract=demo_extract(),
        resume=demo_resume(),
        cover_note="Dear team.",
        change_log="none",
        answers={},
        guardrail_report=GuardrailReport(passed=True, rules_run=[], violations=[]),
        version=1,
        status="draft",
        llm_calls=0,
        created_at=datetime.now(UTC),
    )


async def test_jobs_are_user_scoped(client: httpx.AsyncClient, session_factory, user_id) -> None:  # type: ignore[no-untyped-def]
    from rhapto.db.repositories.applications import create_application
    from rhapto.db.repositories.jobs import create_job
    from rhapto.db.repositories.packages import create_package
    from rhapto.db.repositories.users import get_or_create_user

    mine = (await client.post("/api/v1/jobs", json={"jd_text": JD})).json()
    other_text = "Someone else's job description text that is long enough. " * 2
    async with session_factory() as session:
        other = await get_or_create_user(session, "other@example.com")
        their_job = await create_job(session, other.id, jd_text=other_text)
        # Their package and application, on their own job.
        await create_package(
            session,
            other.id,
            their_job.id,
            _other_package(other_text),
            selection_block_ids=[],
            parent_package_id=None,
            docx_path=None,
            pdf_path=None,
        )
        await create_application(session, other.id, their_job.id, None)
        # And the same rows mis-stitched onto *my* job: only the user_id filter keeps these out.
        await create_package(
            session,
            other.id,
            uuid.UUID(mine["id"]),
            _other_package(JD),
            selection_block_ids=[],
            parent_package_id=None,
            docx_path=None,
            pdf_path=None,
        )
        await create_application(session, other.id, uuid.UUID(mine["id"]), None)
        await session.commit()

    listed = (await client.get("/api/v1/jobs")).json()
    assert [j["id"] for j in listed] == [mine["id"]]
    assert listed[0]["latest_package"] is None and listed[0]["application_status"] is None
    fetched = (await client.get(f"/api/v1/jobs/{mine['id']}")).json()
    assert fetched["latest_package"] is None and fetched["application_status"] is None


async def test_search_does_not_treat_percent_as_a_wildcard(client: httpx.AsyncClient) -> None:
    await client.post(
        "/api/v1/jobs",
        json={
            "jd_text": "PercentCo migrated 100% of its pipelines to Snowflake last year. " * 3,
            "company": "PercentCo",
        },
    )
    await client.post(
        "/api/v1/jobs",
        json={
            "jd_text": "PlainCo runs 100 pipelines and wants a program manager to own them. " * 3,
            "company": "PlainCo",
        },
    )
    literal = (await client.get("/api/v1/jobs", params={"search": "100%"})).json()
    assert [j["company"] for j in literal] == ["PercentCo"]
    both = (await client.get("/api/v1/jobs", params={"search": "100"})).json()
    assert {j["company"] for j in both} == {"PercentCo", "PlainCo"}
