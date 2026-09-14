import json

import httpx
import pytest

import rhapto.services.jobtext as jobtext
from rhapto.services.discovery.dedupe import identity_hash, normalize_title
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.sources.base import SourceError, matches_keywords
from rhapto.services.jobtext import html_to_text


def test_html_to_text_strips_markup_and_entities() -> None:
    text = html_to_text("<p>Lead the <b>data platform</b> &amp; ETL.</p><ul><li>Remote</li></ul>")
    assert "data platform & ETL" in text and "<" not in text and "Remote" in text


def test_html_to_text_turns_p_and_br_into_newlines() -> None:
    text = html_to_text("Company | Role | Remote<p>Body text<br>more")
    lines = text.splitlines()
    assert lines[0] == "Company | Role | Remote"
    assert len(lines) > 1
    assert "Body text" in text and "more" in text


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


async def test_discovery_http_base_override_rewrites_scheme_and_host() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json={"jobs": []})

    http = DiscoveryHttp(
        user_agent="t",
        base_override="http://127.0.0.1:8089",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await http.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs")
    assert result == {"jobs": []}
    assert seen == ["http://127.0.0.1:8089/v1/boards/x/jobs"]


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


async def test_discovery_http_rejects_redirect_to_private_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A vendor that 302s to a private/loopback address must not have that hop followed."""
    hops = {"example.com": ["93.184.216.34"], "127.0.0.1": ["127.0.0.1"]}
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: hops[host])
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/x"})

    http = DiscoveryHttp(
        user_agent="t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SourceError):
        await http.get_text("https://example.com/start")
    assert requested == ["https://example.com/start"]


async def test_discovery_http_follows_one_redirect_to_public_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["93.184.216.34"])

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new"})
        return httpx.Response(200, text="final body")

    http = DiscoveryHttp(
        user_agent="t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await http.get_text("https://example.com/old") == "final body"


async def test_discovery_http_too_many_redirects_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["93.184.216.34"])

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    http = DiscoveryHttp(
        user_agent="t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SourceError, match="too many redirects"):
        await http.get_text("https://example.com/loop")


async def test_fake_http_routes_by_substring_and_records_calls() -> None:
    fake = FakeDiscoveryHttp({"/boards/acme/": {"jobs": []}, "/bad": SourceError("down")})
    assert await fake.get_json(
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    ) == {"jobs": []}
    with pytest.raises(SourceError):
        await fake.get_json("https://x/bad")
    assert len(fake.calls) == 2


async def test_discovery_http_handles_gzip_responses() -> None:
    """Vendors gzip their JSON; the decoded body must not be inflated a second time."""
    import gzip

    payload = gzip.compress(b'{"jobs": [1, 2]}')

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=payload,
            headers={"content-type": "application/json", "content-encoding": "gzip"},
        )

    http = DiscoveryHttp(
        user_agent="t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    assert await http.get_json("https://example.com/api") == {"jobs": [1, 2]}


async def test_post_json_sends_body_and_returns_json() -> None:
    seen: list[tuple[str, bytes, str]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.content, request.headers["user-agent"]))
        return httpx.Response(200, json={"total": 1, "jobPostings": []})

    http = DiscoveryHttp(
        user_agent="rhapto-test/1", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    body = {"appliedFacets": {}, "limit": 20, "offset": 0, "searchText": "ETL"}
    assert await http.post_json("https://example.com/wday/cxs/t/s/jobs", body) == {
        "total": 1,
        "jobPostings": [],
    }
    assert seen[0][0] == "POST" and seen[0][2] == "rhapto-test/1"
    assert json.loads(seen[0][1]) == body


async def test_post_json_raises_on_4xx_redirect_and_private_hosts() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/moved":
            return httpx.Response(302, headers={"location": "https://example.com/elsewhere"})
        return httpx.Response(404)

    http = DiscoveryHttp(
        user_agent="t", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(SourceError, match="HTTP 404"):
        await http.post_json("https://example.com/jobs", {})
    with pytest.raises(SourceError, match="redirected"):
        await http.post_json("https://example.com/moved", {})

    guarded = DiscoveryHttp(user_agent="t")
    with pytest.raises(SourceError, match="refusing to fetch"):
        await guarded.post_json("http://127.0.0.1/jobs", {})


async def test_fake_http_records_posts_separately_from_gets() -> None:
    fake = FakeDiscoveryHttp({"/jobs": {"total": 0, "jobPostings": []}})
    await fake.post_json("https://x.myworkdayjobs.com/wday/cxs/t/s/jobs", {"offset": 0})
    assert fake.posts == [("POST", "https://x.myworkdayjobs.com/wday/cxs/t/s/jobs", {"offset": 0})]
    assert fake.calls == []
