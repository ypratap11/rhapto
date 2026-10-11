from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable, Iterable
from urllib.parse import urljoin, urlparse

import httpcore
import httpx
import trafilatura

from rhapto.db.hashing import dedupe_hash

SocketOption = (
    tuple[int, int, int] | tuple[int, int, bytes | bytearray] | tuple[int, int, None, int]
)

__all__ = [
    "BlockedAddressError",
    "FetchText",
    "JobTextError",
    "PinnedNetworkBackend",
    "PinnedTransport",
    "assert_public_host",
    "dedupe_hash",
    "fetch_job_text",
    "html_to_text",
    "public_addresses",
    "public_http_client",
    "resolve_host",
]

FetchText = Callable[[str], Awaitable[str]]
MIN_TEXT_CHARS = 200
TIMEOUT_SECONDS = 20.0
MAX_REDIRECTS = 5
MAX_BYTES = 5 * 1024 * 1024
ALLOWED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml", "text/plain"})
_REDIRECT_STATUS_CODES = (301, 302, 303, 307, 308)
_USER_AGENT = {"User-Agent": "rhapto/0.1 (+https://github.com)"}


class JobTextError(Exception):
    """The job posting could not be fetched or contained too little text."""


# Named explicitly rather than inferred from ``is_private``/``is_reserved``: the stdlib's special-purpose
# tables changed between 3.12 patch releases, and ``is_global`` is not reliable for NAT64 on every patch.
# CGNAT (100.64/10) is carrier-internal. 6to4 and NAT64 (plain and the RFC 8215 local-use prefix) embed an
# IPv4 address, so they are refused outright: a public job board has native v4/v6 records.
_EXTRA_BLOCKED = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("2002::/16"),
    ipaddress.ip_network("64:ff9b::/96"),
    ipaddress.ip_network("64:ff9b:1::/48"),
)


def resolve_host(hostname: str) -> list[str]:
    """Resolve a hostname to its IP address strings. Overridable in tests."""
    infos = socket.getaddrinfo(hostname, None)
    return [str(info[4][0]) for info in infos]


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        return _is_blocked(ip.ipv4_mapped)
    if any(ip.version == net.version and ip in net for net in _EXTRA_BLOCKED):
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def public_addresses(hostname: str) -> list[str]:
    """Resolve a hostname and return its addresses, rejecting any that are not public, to prevent SSRF via
    job posting URLs.

    Refused: private, loopback, link-local, reserved, multicast and unspecified addresses; carrier-grade
    NAT (100.64.0.0/10); 6to4 (2002::/16) and NAT64 (64:ff9b::/96, 64:ff9b:1::/48) in full. An IPv4-mapped
    IPv6 address (::ffff:a.b.c.d) is judged by the IPv4 address it wraps. Every resolved address must
    pass, so a host with one blocked record is rejected. Returns the validated addresses in resolver order.
    """
    try:
        addresses = await asyncio.to_thread(resolve_host, hostname)
    except OSError as exc:
        raise JobTextError("URL host could not be resolved") from exc
    if not addresses:
        raise JobTextError("URL host could not be resolved")
    for address in addresses:
        if _is_blocked(ipaddress.ip_address(address)):
            raise JobTextError("URL host is not allowed")
    return addresses


async def assert_public_host(hostname: str) -> None:
    """Raise JobTextError unless every address the hostname resolves to is public."""
    await public_addresses(hostname)


class BlockedAddressError(JobTextError):
    """A connection was refused because it would reach a non-public address."""


class PinnedNetworkBackend(httpcore.AsyncNetworkBackend):
    """Network backend that resolves, validates and connects to the validated IP itself.

    httpcore passes the hostname to `connect_tcp` and then does TLS with the hostname as SNI,
    so connecting to the IP keeps certificate verification on the hostname while closing the
    gap between the SSRF check and the connection (DNS rebinding). Each sequential attempt
    gets the full connect timeout; there is no happy-eyeballs.
    """

    def __init__(self, inner: httpcore.AsyncNetworkBackend | None = None) -> None:
        self._inner = inner or httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        try:
            addresses = await public_addresses(host)
        except JobTextError as exc:
            raise BlockedAddressError(str(exc)) from exc
        last: Exception | None = None
        for ip in list(dict.fromkeys(addresses)):
            try:
                return await self._inner.connect_tcp(
                    ip,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except (httpcore.ConnectError, httpcore.ConnectTimeout) as exc:
                last = exc
        raise last or httpcore.ConnectError("no address")

    async def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[SocketOption] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        raise BlockedAddressError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedTransport(httpx.AsyncHTTPTransport):
    """httpx transport whose connections go through `PinnedNetworkBackend`.

    `trust_env=False`: proxy environment variables are ignored for these fetchers, so a
    proxy cannot be used to reach a host this module has not validated.
    """

    def __init__(self, *, backend: httpcore.AsyncNetworkBackend | None = None) -> None:
        super().__init__(trust_env=False)
        # httpx 0.28 has no public network_backend parameter; replace the pool it built,
        # keeping httpx's own limits (httpcore's defaults would queue concurrent fetches).
        self._pool = httpcore.AsyncConnectionPool(
            ssl_context=httpx.create_ssl_context(trust_env=False),
            max_connections=100,
            max_keepalive_connections=20,
            keepalive_expiry=5.0,
            http1=True,
            http2=False,
            network_backend=backend or PinnedNetworkBackend(),
        )


def public_http_client(
    *, timeout: float, backend: httpcore.AsyncNetworkBackend | None = None
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=PinnedTransport(backend=backend),
        timeout=timeout,
        follow_redirects=False,
        trust_env=False,
    )


async def _check_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise JobTextError("only http(s) URLs are supported")
    await assert_public_host(parsed.hostname)


def _strip_tags(html: str) -> str:
    """Strip tags, collapsing horizontal whitespace only. Newlines are preserved (not folded
    into spaces) so a caller that pre-converts `<p>`/`<br>` into `\\n` (see `html_to_text`)
    keeps those line breaks through this fallback path."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_module.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def html_to_text(html: str) -> str:
    """Plain text from HTML: trafilatura first, then a tag-strip fallback; whitespace collapsed.

    `<p>` and `<br>` tags are turned into newlines before extraction so a leading line (e.g.
    a title line in a plain-text-ish snippet) stays separate from the body that follows it.
    """
    unescaped = html_module.unescape(html) if "&lt;" in html and "<" not in html else html
    unescaped = re.sub(r"<\s*(p|br)\b[^>]*>", "\n", unescaped, flags=re.I)
    extracted = trafilatura.extract(unescaped, include_comments=False, include_tables=True) or ""
    text = extracted.strip() or _strip_tags(unescaped)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()


def _check_content_type(header: str | None) -> None:
    """Only markup and plain text can be a job posting. An absent header is allowed, since
    plenty of servers omit it; anything else (a PDF, an image, a tarball) is refused before
    its bytes are read."""
    if not header:
        return
    mime = header.split(";", 1)[0].strip().lower()
    if mime and mime not in ALLOWED_CONTENT_TYPES:
        raise JobTextError("unsupported content type")


async def _read_capped(response: httpx.Response) -> str:
    """Accumulate at most MAX_BYTES of the body; a remote host is the one place where bytes
    entering this process are not under our control."""
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_BYTES:
            raise JobTextError("page too large")
        chunks.append(chunk)
    body = b"".join(chunks)
    try:
        return body.decode(response.encoding or "utf-8", errors="replace")
    except LookupError:  # the server named an encoding Python does not know
        return body.decode("utf-8", errors="replace")


async def fetch_job_text(url: str, *, client: httpx.AsyncClient | None = None) -> str:
    await _check_url(url)
    own_client = client is None
    client = client or public_http_client(timeout=TIMEOUT_SECONDS)
    try:
        current_url = url
        redirects = 0
        html = ""
        while True:
            next_url: str | None = None
            try:
                async with client.stream("GET", current_url, headers=_USER_AGENT) as response:
                    if response.status_code in _REDIRECT_STATUS_CODES:
                        if redirects >= MAX_REDIRECTS:
                            raise JobTextError("too many redirects")
                        location = response.headers.get("location")
                        if not location:
                            raise JobTextError(f"fetch failed with HTTP {response.status_code}")
                        next_url = urljoin(current_url, location)
                    elif response.status_code >= 400:
                        raise JobTextError(f"fetch failed with HTTP {response.status_code}")
                    else:
                        _check_content_type(response.headers.get("content-type"))
                        html = await _read_capped(response)
            except httpx.HTTPError as exc:
                raise JobTextError(f"fetch failed: {exc}") from exc
            if next_url is None:
                break
            redirects += 1
            current_url = next_url
            await _check_url(current_url)
    finally:
        if own_client:
            await client.aclose()
    text = html_to_text(html)
    if len(text) < MIN_TEXT_CHARS:
        raise JobTextError("too little text extracted from the page; paste the description instead")
    return text
