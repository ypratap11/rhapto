import httpx
import pytest

from rhapto.services.discovery.dedupe import identity_hash, normalize_title
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.sources.base import SourceError, matches_keywords
from rhapto.services.jobtext import html_to_text


def test_html_to_text_strips_markup_and_entities() -> None:
    text = html_to_text("<p>Lead the <b>data platform</b> &amp; ETL.</p><ul><li>Remote</li></ul>")
    assert "data platform & ETL" in text and "<" not in text and "Remote" in text


def test_normalize_title_and_identity_hash() -> None:
    assert normalize_title("Senior Data PM (Remote) - Platform") == "senior data pm"
    assert normalize_title("  Data   Program Manager ") == "data program manager"
    a = identity_hash("ExampleCo", "Data Program Manager (Remote)", "Denver, CO")
    b = identity_hash("exampleco", "data program manager", "denver, co")
    assert a == b and len(a) == 64
    assert identity_hash("ExampleCo", "Data Program Manager", None) != a


def test_matches_keywords_whole_word_any_text() -> None:
    assert matches_keywords(["ETL"], "Data lead", "we run ETL nightly")
    assert not matches_keywords(["ETL"], "we settle accounts", None)
    assert matches_keywords([], None, None)


async def test_discovery_http_rejects_private_hosts_and_large_bodies() -> None:
    http = DiscoveryHttp(user_agent="t", max_bytes=10)
    with pytest.raises(SourceError):
        await http.get_json("http://127.0.0.1/jobs")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 11, headers={"content-type": "application/json"})

    big = DiscoveryHttp(
        user_agent="t",
        max_bytes=10,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    with pytest.raises(SourceError, match="25|too large|exceeds"):
        await big.get_text("https://example.com/big")


async def test_discovery_http_retries_once_on_5xx_and_sends_user_agent() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        if len(seen) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    http = DiscoveryHttp(
        user_agent="rhapto-test/1", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await http.get_json("https://example.com/api") == {"ok": True}
    assert seen == ["rhapto-test/1", "rhapto-test/1"]


async def test_fake_http_routes_by_substring_and_records_calls() -> None:
    fake = FakeDiscoveryHttp({"/boards/acme/": {"jobs": []}, "/bad": SourceError("down")})
    assert await fake.get_json(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    ) == {"jobs": []}
    with pytest.raises(SourceError):
        await fake.get_json("https://x/bad")
    assert len(fake.calls) == 2
