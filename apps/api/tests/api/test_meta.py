import httpx


async def test_health_is_public(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


async def test_me_requires_bearer(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 401 and body["title"] == "Unauthorized"


async def test_me_rejects_wrong_token(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/me", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_me_returns_user(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_openapi_served(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/openapi.json")
    assert response.status_code == 200 and response.json()["info"]["title"] == "Rhapto API"
