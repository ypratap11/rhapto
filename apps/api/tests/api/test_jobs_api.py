import httpx

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


async def test_jobs_are_user_scoped(client: httpx.AsyncClient, session_factory, user_id) -> None:  # type: ignore[no-untyped-def]
    from rhapto.db.repositories.jobs import create_job
    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as session:
        other = await get_or_create_user(session, "other@example.com")
        await create_job(
            session,
            other.id,
            jd_text="Someone else's job description text that is long enough. " * 2,
        )
        await session.commit()
    assert (await client.get("/api/v1/jobs")).json() == []
