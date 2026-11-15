from __future__ import annotations

import httpx
import pytest

from rhapto.services.discovery.errors import SourceError
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp

URL = "http://vendor.test/api"


def _real(handler: httpx.MockTransport) -> DiscoveryHttp:
    return DiscoveryHttp(
        user_agent="t",
        client=httpx.AsyncClient(transport=handler),
        base_override="http://x",
    )


async def test_real_client_429_raises_rate_limited_with_allowlisted_quota() -> None:
    from rhapto.services.discovery.errors import RateLimited

    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(
            429,
            headers={
                "x-ratelimit-requests-remaining": "0",
                "x-ratelimit-requests-reset": "120",
                "set-cookie": "a=b",
                "x-rapidapi-key": "SECRET",
            },
        )

    http = _real(httpx.MockTransport(handler))
    with pytest.raises(RateLimited) as info:
        await http.get_json(URL)
    exc = info.value
    assert exc.status == 429
    assert exc.quota is not None
    assert exc.quota.remaining == 0
    assert exc.quota.reset_seconds == 120
    assert "SECRET" not in str(exc) + repr(exc) + repr(exc.args)
    assert len(seen) == 1


async def test_real_client_other_errors_keep_wording_and_carry_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rhapto.services.discovery.errors import RateLimited

    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(403 if "forbid" in request.url.path else 500)

    http = _real(httpx.MockTransport(handler))
    with pytest.raises(SourceError) as info:
        await http.get_json("http://vendor.test/forbid")
    assert not isinstance(info.value, RateLimited)
    assert str(info.value) == "http://x/forbid returned HTTP 403"
    assert info.value.status == 403
    assert len(seen) == 1

    seen.clear()
    http._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))  # noqa: SLF001

    async def no_sleep(_s: float) -> None:
        return None

    monkeypatch.setattr("rhapto.services.discovery.http.asyncio.sleep", no_sleep)
    with pytest.raises(SourceError) as info2:
        await http.get_json("http://vendor.test/boom")
    assert info2.value.status == 500
    assert len(seen) == 2


async def test_get_json_response_returns_body_and_only_allowlisted_headers() -> None:
    from rhapto.services.discovery.http import JsonResponse

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"a": 1},
            headers={
                "X-RateLimit-Requests-Limit": "100",
                "x-ratelimit-requests-remaining": "7",
                "Retry-After": "3",
                "set-cookie": "a=b",
            },
        )

    resp = await _real(httpx.MockTransport(handler)).get_json_response(URL)
    assert isinstance(resp, JsonResponse)
    assert resp.body == {"a": 1}
    assert resp.headers == {
        "x-ratelimit-requests-limit": "100",
        "x-ratelimit-requests-remaining": "7",
        "retry-after": "3",
    }


async def test_fake_http_raises_same_types_as_real() -> None:
    from rhapto.services.discovery.errors import RateLimited
    from rhapto.services.discovery.http import FakeResponse

    fake = FakeDiscoveryHttp(
        {
            "/limited": FakeResponse(429, headers={"x-ratelimit-requests-remaining": "0"}),
            "/missing": FakeResponse(404),
            "/plain": {"p": 1},
            "/ok": FakeResponse(200, {"o": 1}, {"x-ratelimit-requests-limit": "5"}),
            "/post429": FakeResponse(429),
        }
    )
    with pytest.raises(RateLimited) as r:
        await fake.get_json("http://v/limited")
    assert r.value.quota is not None and r.value.quota.remaining == 0
    with pytest.raises(SourceError) as m:
        await fake.get_json("http://v/missing")
    assert not isinstance(m.value, RateLimited)
    assert m.value.status == 404
    assert (await fake.get_json_response("http://v/plain")).headers == {}
    ok = await fake.get_json_response("http://v/ok")
    assert ok.body == {"o": 1}
    assert ok.headers == {"x-ratelimit-requests-limit": "5"}
    with pytest.raises(RateLimited):
        await fake.post_json("http://v/post429", {})
    assert fake.calls == ["http://v/limited", "http://v/missing", "http://v/plain", "http://v/ok"]


async def test_fake_get_json_still_records_headers_and_raises_instances() -> None:
    from rhapto.services.discovery.errors import RateLimited

    boom = RateLimited("x", status=429)
    fake = FakeDiscoveryHttp({"/a": {"v": 1}, "/b": boom})
    assert await fake.get_json("http://v/a", headers={"k": "v"}) == {"v": 1}
    assert fake.headers == [{"k": "v"}]
    with pytest.raises(RateLimited):
        await fake.get_json_response("http://v/b")


def test_parse_quota_retry_after_only_when_reset_absent() -> None:
    from rhapto.services.discovery.http import parse_quota

    q = parse_quota({"retry-after": "30"})
    assert q is not None and q.reset_seconds == 30
    q2 = parse_quota({"retry-after": "30", "x-ratelimit-requests-reset": "90"})
    assert q2 is not None and q2.reset_seconds == 90
    assert parse_quota({}) is None
    q3 = parse_quota({"x-ratelimit-requests-limit": "100", "x-ratelimit-requests-remaining": "x"})
    assert q3 is not None and q3.limit == 100 and q3.remaining is None
