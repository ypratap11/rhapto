from __future__ import annotations

import asyncio
import html as html_module
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

from rhapto.db.hashing import dedupe_hash

__all__ = [
    "FetchText",
    "JobTextError",
    "assert_public_host",
    "dedupe_hash",
    "fetch_job_text",
    "html_to_text",
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


NAT64_PREFIX = ipaddress.ip_network("64:ff9b::/96")


def resolve_host(hostname: str) -> list[str]:
    """Resolve a hostname to its IP address strings. Overridable in tests."""
    infos = socket.getaddrinfo(hostname, None)
    return [str(info[4][0]) for info in infos]


def _is_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def assert_public_host(hostname: str) -> None:
    """Reject hostnames that resolve to private, loopback, link-local, reserved,
    multicast, or unspecified addresses, to prevent SSRF via job posting URLs.

    Also unwraps IPv4-mapped IPv6 addresses (::ffff:a.b.c.d) and NAT64-embedded
    IPv4 addresses (64:ff9b::/96) and applies the same checks to the embedded
    IPv4 address, since either could otherwise be used to smuggle a blocked
    address past the IPv6 checks.
    """
    try:
        addresses = await asyncio.to_thread(resolve_host, hostname)
    except OSError as exc:
        raise JobTextError("URL host could not be resolved") from exc
    if not addresses:
        raise JobTextError("URL host could not be resolved")
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if _is_blocked(ip):
            raise JobTextError("URL host is not allowed")
        if isinstance(ip, ipaddress.IPv6Address):
            if ip.ipv4_mapped is not None and _is_blocked(ip.ipv4_mapped):
                raise JobTextError("URL host is not allowed")
            if ip in NAT64_PREFIX:
                embedded = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
                if _is_blocked(embedded):
                    raise JobTextError("URL host is not allowed")


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
    client = client or httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT_SECONDS)
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
