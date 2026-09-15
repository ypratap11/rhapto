import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_discovery_sources import fake_http_for

from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.services.discovery.http import FakeDiscoveryHttp


@pytest.fixture
def discovery_http(worker_ctx: dict[str, Any]) -> FakeDiscoveryHttp:
    http = FakeDiscoveryHttp(
        {**fake_http_for("greenhouse").routes, **fake_http_for("remoteok").routes}
    )
    worker_ctx["discovery_http"] = http
    return http


async def test_sources_lists_registry(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/discovery/sources")
    assert response.status_code == 200
    names = {s["name"]: s for s in response.json()}
    assert names["greenhouse"]["kind"] == "board" and names["greenhouse"]["needs_board"] is True
    assert names["hn-hiring"]["kind"] == "aggregator"


async def test_runs_reports_distinct_search_ids_for_one_keyless_aggregator(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """A keyless aggregator fanned out across several saved searches now produces one PollRun
    per (source, board, search_id) (see services.discovery.poller / db.repositories.discovery),
    so /discovery/runs must surface each one with its own search_id rather than collapsing them
    -- and a board run (which never has a search) must still report search_id: null."""
    async with session_factory() as session:
        search_a = await searches_repo.create_search(
            session, user_id, name="A", keywords=["alpha"], location=None, remote="include"
        )
        search_b = await searches_repo.create_search(
            session, user_id, name="B", keywords=["beta"], location=None, remote="include"
        )
        run_a = await disc_repo.start_run(session, user_id, "remoteok", None)
        run_a.search_id = search_a.id
        disc_repo.finish_run(run_a, found=1, new=1, error=None)
        run_b = await disc_repo.start_run(session, user_id, "remoteok", None)
        run_b.search_id = search_b.id
        disc_repo.finish_run(run_b, found=2, new=0, error=None)
        board_run = await disc_repo.start_run(session, user_id, "greenhouse", "exampleco")
        disc_repo.finish_run(board_run, found=0, new=0, error=None)
        await session.commit()

    response = await client.get("/api/v1/discovery/runs")
    assert response.status_code == 200
    rows = response.json()
    remoteok_rows = [r for r in rows if r["source"] == "remoteok"]
    assert len(remoteok_rows) == 2
    assert {r["search_id"] for r in remoteok_rows} == {str(search_a.id), str(search_b.id)}
    board_rows = [r for r in rows if r["source"] == "greenhouse"]
    assert board_rows and all(r["search_id"] is None for r in board_rows)


async def test_poll_creates_jobs_runs_and_scored_queue(
    client: httpx.AsyncClient, imported_profile: None, discovery_http: FakeDiscoveryHttp
) -> None:
    started = await client.post("/api/v1/discovery/poll")
    assert started.status_code == 202
    task = await client.get(f"/api/v1/tasks/{started.json()['id']}")
    assert task.json()["status"] == "succeeded" and task.json()["result_ref"].startswith("new:")
    runs = await client.get("/api/v1/discovery/runs")
    assert {r["source"] for r in runs.json()} == {"greenhouse", "remoteok"}
    jobs = await client.get("/api/v1/jobs", params={"sort": "fit"})
    body = jobs.json()
    assert body and all(j["best_fit"] is not None and j["bucket"] in ("fit", "low") for j in body)
    assert [j["best_fit"] for j in body] == sorted((j["best_fit"] for j in body), reverse=True)
    assert body[0]["scores"] and {"track_id", "fit_score", "rationale"} <= set(body[0]["scores"][0])
    only_low = await client.get("/api/v1/jobs", params={"bucket": "low"})
    assert all(j["bucket"] == "low" for j in only_low.json())
    by_track = await client.get("/api/v1/jobs", params={"track": "data-pm"})
    assert all(j["best_track_id"] == "data-pm" for j in by_track.json())


async def test_rescue_moves_job_into_fit_bucket(
    client: httpx.AsyncClient, imported_profile: None, discovery_http: FakeDiscoveryHttp
) -> None:
    # A manual job with no track keywords scores low against every track, so the low bucket is
    # guaranteed non-empty regardless of what the polled fixtures produce.
    barista = (
        "CafeCo hires a barista to prepare espresso drinks, keep the counter clean, and greet customers. "
        * 2
    )
    created = await client.post("/api/v1/jobs", json={"jd_text": barista, "title": "Barista"})
    assert created.status_code == 201 and created.json()["bucket"] == "low"
    await client.post("/api/v1/discovery/poll")
    low = (await client.get("/api/v1/jobs", params={"bucket": "low"})).json()
    assert created.json()["id"] in {j["id"] for j in low}
    rescued = await client.post(f"/api/v1/jobs/{created.json()['id']}/rescue")
    assert (
        rescued.status_code == 200
        and rescued.json()["rescued"] is True
        and rescued.json()["bucket"] == "fit"
    )


async def test_manual_job_is_scored_on_create(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    jd = (
        "ExampleCo seeks a Data Program Manager to lead our data platform, analytics, and ETL modernisation. "
        * 2
    )
    created = await client.post(
        "/api/v1/jobs", json={"jd_text": jd, "title": "Data Program Manager"}
    )
    assert created.status_code == 201
    fetched = await client.get(f"/api/v1/jobs/{created.json()['id']}")
    assert fetched.json()["best_track_id"] == "data-pm" and fetched.json()["best_fit"] is not None
    assert fetched.json()["bucket"] in (
        "fit",
        "low",
    )  # the fake embedder's absolute level is not asserted


async def test_track_put_rescores(client: httpx.AsyncClient, imported_profile: None) -> None:
    jd = (
        "ExampleCo seeks a Data Program Manager to lead our data platform, analytics, and ETL modernisation. "
        * 2
    )
    job = (
        await client.post("/api/v1/jobs", json={"jd_text": jd, "title": "Data Program Manager"})
    ).json()
    track = (await client.get("/api/v1/profile/tracks")).json()[0]
    track["min_fit"] = 100
    put = await client.put(f"/api/v1/profile/tracks/{track['id']}", json=track)
    assert put.status_code == 200
    fetched = await client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.json()["bucket"] == "low"
