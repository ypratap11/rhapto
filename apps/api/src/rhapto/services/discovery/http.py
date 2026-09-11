from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx

from rhapto.services.discovery.errors import SourceError
from rhapto.services.jobtext import assert_public_host

DEFAULT_MAX_BYTES = 25 * 1024 * 1024


class DiscoveryHttp:
    """Vendor fetches: public hosts only, size cap, timeout, one retry on 5xx, explicit user agent."""

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
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str) -> httpx.Response:
        host = urlparse(url).hostname or ""
        try:
            await assert_public_host(host)
        except Exception as exc:  # JobTextError or resolution failure
            raise SourceError(f"refusing to fetch {url}: {exc}") from exc
        headers = {"User-Agent": self.user_agent, "Accept": "application/json, text/html;q=0.8"}
        last: httpx.Response | None = None
        for attempt in range(2):
            try:
                async with self._client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 500 and attempt == 0:
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
                    last = httpx.Response(
                        response.status_code,
                        content=b"".join(chunks),
                        headers=response.headers,
                        request=response.request,
                    )
                    return last
            except httpx.HTTPError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise SourceError(f"{url}: {exc}") from exc
        raise SourceError(f"{url}: no response after retry")

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
        return value if isinstance(value, str) else str(value)

    async def aclose(self) -> None:
        return None
