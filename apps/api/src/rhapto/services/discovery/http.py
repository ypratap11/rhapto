from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from rhapto.services.discovery.errors import SourceError
from rhapto.services.jobtext import assert_public_host

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5
_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)

logger = logging.getLogger(__name__)


class DiscoveryHttp:
    """Vendor fetches: public hosts only, size cap, timeout, one retry on 5xx, explicit user agent.

    Redirects are followed manually (never by httpx) so every hop's host is re-validated by
    `assert_public_host` before it is requested; otherwise a 3xx to a private or loopback
    address would be followed transparently and defeat the SSRF guard.
    """

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 20.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        client: httpx.AsyncClient | None = None,
        base_override: str = "",
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)
        self.base_override = base_override
        if base_override:
            logger.warning(
                "DiscoveryHttp base_override is set to %s: every request's scheme and host are "
                "rewritten and the public-host (SSRF) check is skipped. Smoke/testing only — "
                "never set this in production.",
                base_override,
            )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _rewrite(self, url: str) -> str:
        """When `base_override` is set, rewrite the URL's scheme and host to it, keeping the
        path and query untouched. Smoke/testing only: it lets `rhapto discover` be pointed at a
        loopback fixture server without the vendor's real host ever being contacted."""
        if not self.base_override:
            return url
        override = urlparse(self.base_override)
        parsed = urlparse(url)
        return urlunparse(parsed._replace(scheme=override.scheme, netloc=override.netloc))

    async def _assert_public(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise SourceError(f"refusing to fetch {url}: unsupported scheme {parsed.scheme!r}")
        if self.base_override:
            return
        host = parsed.hostname or ""
        try:
            await assert_public_host(host)
        except Exception as exc:  # JobTextError or resolution failure
            raise SourceError(f"refusing to fetch {url}: {exc}") from exc

    async def _send_once(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """One hop, no redirect handling: at most one retry on a 5xx or transport error.

        A `while True` with no `break` is used (rather than `for attempt in range(2)`) so every
        exit is a `return` or `raise` inside the loop; mypy can then see the function never
        falls off the end, with no unreachable trailing statement needed to satisfy it.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._client.stream(
                    method, url, headers=headers, json=json_body
                ) as response:
                    if response.status_code >= 500 and attempt == 1:
                        await asyncio.sleep(0.5)
                        continue
                    if response.status_code >= 400:
                        raise SourceError(f"{url} returned HTTP {response.status_code}")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise SourceError(f"{url} exceeds {self.max_bytes} bytes")
                        chunks.append(chunk)
                    # aiter_bytes() already decoded the transfer encoding, so the copied headers
                    # must not claim the body is still compressed (httpx would inflate it twice).
                    out_headers = {
                        k: v
                        for k, v in response.headers.items()
                        if k.lower() not in ("content-encoding", "content-length")
                    }
                    return httpx.Response(
                        response.status_code,
                        content=b"".join(chunks),
                        headers=out_headers,
                        request=response.request,
                    )
            except httpx.HTTPError as exc:
                if attempt == 1:
                    await asyncio.sleep(0.5)
                    continue
                raise SourceError(f"{url}: {exc}") from exc

    async def _get(self, url: str) -> httpx.Response:
        current_url = self._rewrite(url)
        await self._assert_public(current_url)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json, text/html;q=0.8"}
        for _ in range(MAX_REDIRECTS + 1):
            # _send_once already raises SourceError for any >= 400 status, so a response that
            # comes back here is either a success (< 400) or a redirect (3xx, also < 400).
            response = await self._send_once("GET", current_url, headers)
            if response.status_code not in _REDIRECT_STATUS_CODES:
                return response
            location = response.headers.get("location")
            if not location:
                raise SourceError(f"{current_url} redirected with no Location header")
            current_url = self._rewrite(urljoin(current_url, location))
            await self._assert_public(current_url)
        raise SourceError(f"{url}: too many redirects")

    async def get_json(self, url: str) -> Any:
        response = await self._get(url)
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(f"{url}: invalid JSON") from exc

    async def get_text(self, url: str) -> str:
        return (await self._get(url)).text

    async def post_json(self, url: str, body: dict[str, Any]) -> Any:
        """JSON POST for search APIs (Workday). Same host, scheme, size and retry rules as GET.

        Redirects are not followed: replaying a POST against a new location would either drop
        the body (301/302/303 semantics) or re-send it to a host the caller never named, so a
        3xx is an error here instead of a hop.
        """
        target = self._rewrite(url)
        await self._assert_public(target)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        response = await self._send_once("POST", target, headers, body)
        if response.status_code in _REDIRECT_STATUS_CODES:
            raise SourceError(
                f"{url} redirected with HTTP {response.status_code}; POST not retried"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(f"{url}: invalid JSON") from exc


class FakeDiscoveryHttp:
    """Test double: routes keyed by URL substring; a SourceError value is raised instead of returned."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []
        self.posts: list[tuple[str, str, dict[str, Any]]] = []

    def _match(self, url: str) -> Any:
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, SourceError):
                    raise value
                return value
        raise SourceError(f"no fake route for {url}")

    def _route(self, url: str) -> Any:
        self.calls.append(url)
        return self._match(url)

    async def get_json(self, url: str) -> Any:
        return self._route(url)

    async def post_json(self, url: str, body: dict[str, Any]) -> Any:
        """POSTs are recorded in `posts` (method, url, body); `calls` stays a GET-only log."""
        self.posts.append(("POST", url, body))
        return self._match(url)

    async def get_text(self, url: str) -> str:
        value = self._route(url)
        if not isinstance(value, str):
            raise SourceError(f"fake route for {url} is not text: {value!r}")
        return value

    async def aclose(self) -> None:
        return None
