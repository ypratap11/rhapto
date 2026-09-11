from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from rhapto.services.discovery.errors import SourceError
from rhapto.services.jobtext import assert_public_host

DEFAULT_MAX_BYTES = 25 * 1024 * 1024
MAX_REDIRECTS = 5
_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)


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
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=False)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _assert_public(self, url: str) -> None:
        host = urlparse(url).hostname or ""
        try:
            await assert_public_host(host)
        except Exception as exc:  # JobTextError or resolution failure
            raise SourceError(f"refusing to fetch {url}: {exc}") from exc

    async def _get_once(self, url: str, headers: dict[str, str]) -> httpx.Response:
        """One hop, no redirect handling: at most one retry on a 5xx or transport error.

        A `while True` with no `break` is used (rather than `for attempt in range(2)`) so every
        exit is a `return` or `raise` inside the loop; mypy can then see the function never
        falls off the end, with no unreachable trailing statement needed to satisfy it.
        """
        attempt = 0
        while True:
            attempt += 1
            try:
                async with self._client.stream("GET", url, headers=headers) as response:
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
                    return httpx.Response(
                        response.status_code,
                        content=b"".join(chunks),
                        headers=response.headers,
                        request=response.request,
                    )
            except httpx.HTTPError as exc:
                if attempt == 1:
                    await asyncio.sleep(0.5)
                    continue
                raise SourceError(f"{url}: {exc}") from exc

    async def _get(self, url: str) -> httpx.Response:
        await self._assert_public(url)
        headers = {"User-Agent": self.user_agent, "Accept": "application/json, text/html;q=0.8"}
        current_url = url
        for _ in range(MAX_REDIRECTS + 1):
            # _get_once already raises SourceError for any >= 400 status, so a response that
            # comes back here is either a success (< 400) or a redirect (3xx, also < 400).
            response = await self._get_once(current_url, headers)
            if response.status_code not in _REDIRECT_STATUS_CODES:
                return response
            location = response.headers.get("location")
            if not location:
                raise SourceError(f"{current_url} redirected with no Location header")
            current_url = urljoin(current_url, location)
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


class FakeDiscoveryHttp:
    """Test double: routes keyed by URL substring; a SourceError value is raised instead of returned."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def _route(self, url: str) -> Any:
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, SourceError):
                    raise value
                return value
        raise SourceError(f"no fake route for {url}")

    async def get_json(self, url: str) -> Any:
        return self._route(url)

    async def get_text(self, url: str) -> str:
        value = self._route(url)
        if not isinstance(value, str):
            raise SourceError(f"fake route for {url} is not text: {value!r}")
        return value

    async def aclose(self) -> None:
        return None
