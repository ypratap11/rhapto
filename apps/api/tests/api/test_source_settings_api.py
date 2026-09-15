from __future__ import annotations

import httpx
import pytest

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo


class ProbeSource:
    info = SourceInfo("fake-probe", "aggregator", "Fake probe", False)
    result: list[Posting] | Exception = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        if isinstance(type(self).result, Exception):
            raise type(self).result
        return list(type(self).result)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def probe_source():  # type: ignore[no-untyped-def]
    SOURCES["fake-probe"] = ProbeSource  # type: ignore[assignment]
    yield
    SOURCES.pop("fake-probe", None)
    ProbeSource.result = []


async def test_sources_list_reports_key_requirements(client: httpx.AsyncClient) -> None:
    rows = (await client.get("/api/v1/settings/sources")).json()
    by_id = {r["id"]: r for r in rows}
    assert by_id["themuse"]["needs_key"] is False and by_id["themuse"]["enabled"] is True
    assert by_id["adzuna"]["needs_key"] is True and by_id["adzuna"]["fields"] == [
        "app_id",
        "app_key",
    ]
    assert by_id["adzuna"]["enabled"] is False and by_id["adzuna"]["key_set"] is False


async def test_enabling_a_keyed_source_without_keys_is_422(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/v1/settings/sources/adzuna", json={"enabled": True})
    assert response.status_code == 422 and "app_id" in response.text


async def test_keys_are_stored_and_never_echoed(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/settings/sources/adzuna",
        json={"enabled": True, "credentials": {"app_id": "id-1", "app_key": "s3cret"}},
    )
    assert response.status_code == 200
    assert "s3cret" not in response.text
    assert response.json()["key_set"] is True and response.json()["enabled"] is True


async def test_test_endpoint_reports_both_outcomes(client: httpx.AsyncClient) -> None:
    ProbeSource.result = [
        Posting(external_id="1", company="C", title="T", url="https://e.com/1", jd_text="x" * 60)
    ]
    ok = await client.post("/api/v1/settings/sources/fake-probe/test")
    assert ok.json() == {"ok": True, "found": 1, "error": None}
    ProbeSource.result = SourceError("Fake probe: check the API key")
    bad = await client.post("/api/v1/settings/sources/fake-probe/test")
    assert bad.status_code == 200 and bad.json()["ok"] is False
    assert "check the API key" in bad.json()["error"]
