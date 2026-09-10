import httpx

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3
STATUSES = ["discovered", "queued", "applied", "screen", "interview", "offer", "closed"]


async def _job(client: httpx.AsyncClient, company: str = "ExampleCo") -> str:
    response = await client.post(
        "/api/v1/jobs", json={"jd_text": JD + company, "company": company, "title": "PM"}
    )
    return str(response.json()["id"])


async def test_create_and_board(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    created = await client.post("/api/v1/applications", json={"job_id": job_id})
    assert created.status_code == 201, created.text
    app = created.json()
    assert app["status"] == "queued" and app["job"] == {
        "id": job_id,
        "company": "ExampleCo",
        "title": "PM",
    }
    assert [h["status"] for h in app["status_history"]] == ["queued"] and app["applied_at"] is None
    board = (await client.get("/api/v1/applications")).json()
    assert list(board["columns"]) == STATUSES
    assert [a["id"] for a in board["columns"]["queued"]] == [app["id"]]
    assert (await client.get(f"/api/v1/jobs/{job_id}")).json()["application_status"] == "queued"


async def test_one_application_per_job(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    first = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()
    second = await client.post("/api/v1/applications", json={"job_id": job_id})
    assert second.status_code == 409 and second.json()["existing_application_id"] == first["id"]


async def test_unknown_job_or_package_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post("/api/v1/applications", json={"job_id": missing})).status_code == 404
    job_id = await _job(client)
    assert (
        await client.post("/api/v1/applications", json={"job_id": job_id, "package_id": missing})
    ).status_code == 404


async def test_patch_status_and_notes_with_history(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    app_id = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()["id"]
    moved = (
        await client.patch(
            f"/api/v1/applications/{app_id}", json={"status": "applied", "notes": "Sent via portal"}
        )
    ).json()
    assert (
        moved["status"] == "applied"
        and moved["applied_at"] is not None
        and moved["notes"] == "Sent via portal"
    )
    assert [h["status"] for h in moved["status_history"]] == ["queued", "applied"]
    same = (await client.patch(f"/api/v1/applications/{app_id}", json={"status": "applied"})).json()
    assert len(same["status_history"]) == 2  # unchanged status does not append
    later = (
        await client.patch(f"/api/v1/applications/{app_id}", json={"status": "interview"})
    ).json()
    assert later["applied_at"] == moved["applied_at"]
    board = (await client.get("/api/v1/applications")).json()
    assert [a["id"] for a in board["columns"]["interview"]] == [app_id] and board["columns"][
        "queued"
    ] == []


async def test_patch_invalid_status_422(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    app_id = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()["id"]
    assert (
        await client.patch(f"/api/v1/applications/{app_id}", json={"status": "hired"})
    ).status_code == 422


async def test_delete(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    app_id = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()["id"]
    assert (await client.delete(f"/api/v1/applications/{app_id}")).status_code == 204
    assert (await client.get(f"/api/v1/applications/{app_id}")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{job_id}")).json()["application_status"] is None
