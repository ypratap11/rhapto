import io
import uuid
import zipfile
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, JobScore


async def test_blocks_crud_and_embedding_enqueued(client: httpx.AsyncClient, enqueuer) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/v1/profile/blocks")).json() == []
    body = {
        "id": "acme-x",
        "type": "achievement",
        "content": "Did X.",
        "verified": True,
        "metric": "12 things",
        "tags": ["x"],
    }
    created = await client.put("/api/v1/profile/blocks/acme-x", json=body)
    assert created.status_code == 201 and created.json()["metric"] == "12 things"
    updated = await client.put(
        "/api/v1/profile/blocks/acme-x", json={**body, "content": "Did X better."}
    )
    assert updated.status_code == 200 and updated.json()["content"] == "Did X better."
    assert [b["id"] for b in (await client.get("/api/v1/profile/blocks")).json()] == ["acme-x"]
    assert (
        "embed_blocks",
        {"user_id": enqueuer.calls[0][1]["user_id"], "block_ids": ["acme-x"]},
    ) == enqueuer.calls[0]
    assert (await client.delete("/api/v1/profile/blocks/acme-x")).status_code == 204
    assert (await client.delete("/api/v1/profile/blocks/acme-x")).status_code == 404


async def test_block_id_mismatch_is_422(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/profile/blocks/one", json={"id": "two", "type": "role", "content": "c"}
    )
    assert response.status_code == 422 and "id" in response.json()["detail"]


async def test_block_rejects_unknown_field(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/profile/blocks/a", json={"id": "a", "type": "role", "content": "c", "bogus": 1}
    )
    assert response.status_code == 422 and response.json()["title"] == "Unprocessable Entity"


@pytest.mark.parametrize(
    ("path", "key", "body"),
    [
        ("bases", "b1", {"id": "b1", "name": "Base", "block_ids": []}),
        ("tracks", "t1", {"id": "t1", "name": "Track", "resume_base": "b1"}),
        ("guardrails", "attribution", {"rule": "attribution", "active": False}),
    ],
)
async def test_generic_crud(
    client: httpx.AsyncClient, path: str, key: str, body: dict[str, object]
) -> None:
    assert (await client.put(f"/api/v1/profile/{path}/{key}", json=body)).status_code == 201
    assert len((await client.get(f"/api/v1/profile/{path}")).json()) == 1
    assert (await client.delete(f"/api/v1/profile/{path}/{key}")).status_code == 204


async def test_answers_and_watchlist(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/profile/answers")).json() == {}
    put = await client.put(
        "/api/v1/profile/answers", json={"name": "Maya Chen", "notice_period": "2 weeks"}
    )
    assert put.status_code == 200 and put.json()["name"] == "Maya Chen"
    entries = [{"company": "ExampleCo", "source": "greenhouse", "board": "exampleco"}]
    expected = [{**entries[0], "keywords": [], "discovered": False}]
    assert (await client.put("/api/v1/profile/watchlist", json=entries)).json() == expected
    assert (await client.get("/api/v1/profile/watchlist")).json() == expected


async def test_answers_rescore_only_when_a_location_answer_changes(
    client: httpx.AsyncClient, enqueuer
) -> None:  # type: ignore[no-untyped-def]
    body = {"name": "Maya Chen", "location_preferred": "Denver, Boulder", "remote_ok": "yes"}
    await client.put("/api/v1/profile/answers", json=body)
    assert [c[0] for c in enqueuer.calls] == ["rescore_jobs"]  # first write introduces them

    await client.put("/api/v1/profile/answers", json={**body, "name": "M. Chen"})
    assert [c[0] for c in enqueuer.calls] == ["rescore_jobs"]  # unrelated answer, no rescore

    await client.put(
        "/api/v1/profile/answers", json={**body, "location_preferred": "Santa Clara, San Jose"}
    )
    assert [c[0] for c in enqueuer.calls] == ["rescore_jobs", "rescore_jobs"]
    assert enqueuer.calls[-1][1].keys() == {"user_id"}

    await client.put("/api/v1/profile/answers", json={"name": "Maya Chen"})  # dropped entirely
    assert [c[0] for c in enqueuer.calls] == ["rescore_jobs"] * 3


async def test_aggregators_put_and_get(client: httpx.AsyncClient) -> None:
    body = [
        {"source": "remoteok", "enabled": True, "keywords": ["pm"]},
        {"source": "hn-hiring", "enabled": False, "keywords": []},
    ]
    put = await client.put("/api/v1/profile/aggregators", json=body)
    assert put.status_code == 200 and put.json() == body
    got = await client.get("/api/v1/profile/aggregators")
    assert got.json() == body
    bad = await client.put("/api/v1/profile/aggregators", json=[{"source": "linkedin"}])
    assert bad.status_code == 422


async def test_import_and_export_round_trip(
    client: httpx.AsyncClient, demo_profile_dir: Path, enqueuer
) -> None:  # type: ignore[no-untyped-def]
    files = [
        ("files", (p.name, p.read_bytes(), "application/yaml"))
        for p in sorted(demo_profile_dir.glob("*.yaml"))
    ]
    response = await client.post("/api/v1/profile/import", files=files)
    assert response.status_code == 200, response.text
    assert response.json() == {"blocks": 4, "tracks": 2, "bases": 2, "guardrails": 5}
    assert enqueuer.calls[-2][0] == "embed_blocks" and sorted(
        enqueuer.calls[-2][1]["block_ids"]
    ) == ["acme-data-pm", "acme-migration", "cred-pmp", "side-llm-tool"]
    assert enqueuer.calls[-1][0] == "rescore_jobs"
    blocks = (await client.get("/api/v1/profile/blocks")).json()
    assert {b["id"] for b in blocks} == {
        "acme-data-pm",
        "acme-migration",
        "cred-pmp",
        "side-llm-tool",
    }

    export = await client.get("/api/v1/profile/export")
    assert export.status_code == 200 and export.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(export.content)) as zf:
        assert set(zf.namelist()) == {
            "blocks.yaml",
            "tracks.yaml",
            "bases.yaml",
            "guardrails.yaml",
            "answers.yaml",
            "watchlist.yaml",
        }
        assert b"Maya Chen" in zf.read("answers.yaml")


async def test_import_invalid_yaml_is_422(client: httpx.AsyncClient) -> None:
    files = [
        (
            "files",
            ("blocks.yaml", b"blocks: [{id: a, type: hobby, content: x}]\n", "application/yaml"),
        ),
        ("files", ("tracks.yaml", b"tracks: []\n", "application/yaml")),
    ]
    response = await client.post("/api/v1/profile/import", files=files)
    assert response.status_code == 422 and "blocks.yaml" in response.json()["detail"]


async def test_export_without_profile_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/profile/export")).status_code == 422


TRACK_A = {
    "id": "a",
    "name": "A",
    "resume_base": "b",
    "keywords": ["data platform"],
    "description": "Data platform program leadership",
}
TRACK_B = {**TRACK_A, "id": "b", "name": "B", "keywords": ["LLM"], "description": "LLM work"}


async def _job_state(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> tuple[set[str], str | None, int | None]:
    async with session_factory() as session:
        tracks = set(
            await session.scalars(select(JobScore.track_id).where(JobScore.user_id == user_id))
        )
        job = await session.scalar(select(Job).where(Job.user_id == user_id))
        assert job is not None
        return tracks, job.best_track_id, job.best_fit


async def test_deleting_a_track_deletes_its_scores_and_rescores(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    enqueuer,  # type: ignore[no-untyped-def]
) -> None:
    for body in (TRACK_A, TRACK_B):
        assert (
            await client.put(f"/api/v1/profile/tracks/{body['id']}", json=body)
        ).status_code == 201
    created = await client.post(
        "/api/v1/jobs",
        json={"jd_text": "Own the data platform roadmap for analytics. " * 4, "title": "Data PM"},
    )
    assert created.status_code == 201, created.text
    tracks, _, _ = await _job_state(session_factory, user_id)
    assert tracks == {"a", "b"}

    enqueuer.calls.clear()
    assert (await client.delete("/api/v1/profile/tracks/a")).status_code == 204
    assert [c[0] for c in enqueuer.calls] == ["rescore_jobs"]
    assert enqueuer.calls[0][1] == {"user_id": str(user_id)}
    tracks, best_track, best_fit = await _job_state(session_factory, user_id)
    assert tracks == {"b"}  # a's rows are gone; b was rescored
    assert best_track == "b" and best_fit is not None


async def test_deleting_the_last_track_clears_the_stale_ordering(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    assert (
        await client.put(f"/api/v1/profile/tracks/{TRACK_A['id']}", json=TRACK_A)
    ).status_code == 201
    await client.post(
        "/api/v1/jobs",
        json={"jd_text": "Own the data platform roadmap for analytics. " * 4, "title": "Data PM"},
    )
    _, best_track, best_fit = await _job_state(session_factory, user_id)
    assert best_track == "a" and best_fit is not None

    assert (await client.delete("/api/v1/profile/tracks/a")).status_code == 204
    tracks, best_track, best_fit = await _job_state(session_factory, user_id)
    assert tracks == set() and best_track is None and best_fit is None  # A2 can now say "unranked"
