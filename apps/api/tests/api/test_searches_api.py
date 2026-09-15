from __future__ import annotations

import httpx


async def test_search_crud(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/searches",
        json={
            "name": "Data",
            "keywords": ["data platform"],
            "location": "Denver, CO",
            "remote": "include",
        },
    )
    assert created.status_code == 201
    body = created.json()
    assert body["keywords"] == ["data platform"] and body["active"] is True
    listed = await client.get("/api/v1/searches")
    assert [s["id"] for s in listed.json()] == [body["id"]]
    updated = await client.put(
        f"/api/v1/searches/{body['id']}",
        json={
            "name": "Data",
            "keywords": ["ETL"],
            "location": None,
            "remote": "only",
            "active": False,
        },
    )
    assert updated.status_code == 200 and updated.json()["remote"] == "only"
    assert (await client.delete(f"/api/v1/searches/{body['id']}")).status_code == 204
    assert (await client.delete(f"/api/v1/searches/{body['id']}")).status_code == 404


async def test_empty_keywords_are_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/searches", json={"name": "x", "keywords": []})
    assert response.status_code == 422


async def test_derive_creates_one_search_per_track_then_nothing(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    first = await client.post("/api/v1/searches/derive")
    assert first.status_code == 200 and len(first.json()) >= 1
    assert (await client.post("/api/v1/searches/derive")).json() == []


async def test_an_unknown_search_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get("/api/v1/searches")).status_code == 200
    assert (
        await client.put(f"/api/v1/searches/{missing}", json={"name": "x", "keywords": ["y"]})
    ).status_code == 404
