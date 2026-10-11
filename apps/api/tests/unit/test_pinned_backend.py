"""DNS rebinding: outbound fetches must connect only to addresses that were validated."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import AsyncIterator
from typing import Any

import httpcore
import httpx
import pytest

from rhapto.services import jobtext
from rhapto.services.discovery.errors import SourceError
from rhapto.services.discovery.http import DiscoveryHttp

PUBLIC_IP = "93.184.216.34"


@pytest.fixture
async def loopback_server() -> AsyncIterator[tuple[int, list[int]]]:
    hits: list[int] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        hits.append(1)
        await reader.read(1024)
        writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\n\r\nhi")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    yield port, hits
    server.close()
    await server.wait_closed()


def _rebinding_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def fake(hostname: str) -> list[str]:
        calls["n"] += 1
        return [PUBLIC_IP] if calls["n"] == 1 else ["127.0.0.1"]

    monkeypatch.setattr(jobtext, "resolve_host", fake)


def _always_public(monkeypatch: pytest.MonkeyPatch, addresses: list[str] | None = None) -> None:
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: addresses or [PUBLIC_IP])


async def test_fetch_job_text_never_connects_to_rebound_loopback(
    loopback_server: tuple[int, list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, hits = loopback_server
    _rebinding_resolver(monkeypatch)
    with pytest.raises(jobtext.JobTextError):
        await jobtext.fetch_job_text(f"http://localhost:{port}/x")
    assert hits == []


async def test_discovery_http_never_connects_to_rebound_loopback(
    loopback_server: tuple[int, list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    port, hits = loopback_server
    _rebinding_resolver(monkeypatch)
    http = DiscoveryHttp(user_agent="t")
    with pytest.raises(SourceError):
        await http.get_text(f"http://localhost:{port}/x")
    assert hits == []


def _record_anyio_connects(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    hosts: list[str] = []

    async def fake_connect_tcp(self: Any, host: str, port: int, *args: Any, **kwargs: Any) -> Any:
        hosts.append(host)
        raise httpcore.ConnectError("stop")

    monkeypatch.setattr(httpcore.AnyIOBackend, "connect_tcp", fake_connect_tcp)
    return hosts


async def test_default_job_text_client_connects_to_ip_not_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _always_public(monkeypatch)
    hosts = _record_anyio_connects(monkeypatch)
    with pytest.raises(jobtext.JobTextError):
        await jobtext.fetch_job_text("https://example.com/x")
    assert hosts and set(hosts) == {PUBLIC_IP}


async def test_default_discovery_client_connects_to_ip_not_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _always_public(monkeypatch)
    hosts = _record_anyio_connects(monkeypatch)
    http = DiscoveryHttp(user_agent="t")
    with pytest.raises(SourceError):
        await http.get_text("https://example.com/x")
    assert hosts and set(hosts) == {PUBLIC_IP}


class FakeStream:
    def __init__(self, record: dict[str, Any]) -> None:
        self._record = record

    async def start_tls(
        self,
        ssl_context: ssl.SSLContext,
        server_hostname: str | None = None,
        timeout: float | None = None,
    ) -> Any:
        self._record["server_hostname"] = server_hostname
        raise httpcore.ConnectError("stop after tls")


class RecordingBackend(httpcore.AsyncNetworkBackend):
    def __init__(self) -> None:
        self.record: dict[str, Any] = {}
        self.hosts: list[str] = []
        self.fail_hosts: set[str] = set()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Any = None,
    ) -> Any:
        self.hosts.append(host)
        if host in self.fail_hosts:
            raise httpcore.ConnectError(f"refused {host}")
        return FakeStream(self.record)

    async def connect_unix_socket(self, *args: Any, **kwargs: Any) -> Any:
        raise AssertionError("unexpected")

    async def sleep(self, seconds: float) -> None:
        return None


async def test_tls_keeps_hostname_for_sni_while_connecting_to_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _always_public(monkeypatch)
    inner = RecordingBackend()
    backend = jobtext.PinnedNetworkBackend(inner=inner)
    async with httpx.AsyncClient(transport=jobtext.PinnedTransport(backend=backend)) as client:
        with pytest.raises(httpx.ConnectError):
            await client.get("https://example.com/")
    assert inner.hosts == [PUBLIC_IP]
    assert inner.record["server_hostname"] == "example.com"


async def test_private_address_is_refused_before_inner_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _always_public(monkeypatch, ["10.0.0.5"])
    inner = RecordingBackend()
    backend = jobtext.PinnedNetworkBackend(inner=inner)
    with pytest.raises(jobtext.BlockedAddressError):
        await backend.connect_tcp("example.com", 443)
    assert inner.hosts == []


async def test_falls_back_to_next_validated_ip_and_dedupes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _always_public(monkeypatch, [PUBLIC_IP, PUBLIC_IP, "93.184.216.35"])
    inner = RecordingBackend()
    inner.fail_hosts = {PUBLIC_IP}
    backend = jobtext.PinnedNetworkBackend(inner=inner)
    await backend.connect_tcp("example.com", 443)
    assert inner.hosts == [PUBLIC_IP, "93.184.216.35"]


async def test_all_addresses_failing_raises_connect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _always_public(monkeypatch)
    inner = RecordingBackend()
    inner.fail_hosts = {PUBLIC_IP}
    backend = jobtext.PinnedNetworkBackend(inner=inner)
    with pytest.raises(httpcore.ConnectError):
        await backend.connect_tcp("example.com", 443)


async def test_unix_sockets_are_refused() -> None:
    with pytest.raises(jobtext.BlockedAddressError):
        await jobtext.PinnedNetworkBackend().connect_unix_socket("/x")


async def test_pinned_transport_upgrade_tripwire() -> None:
    transport = jobtext.PinnedTransport()
    pool: Any = transport._pool
    assert isinstance(pool._network_backend, jobtext.PinnedNetworkBackend)
    assert pool._max_connections == 100
    await transport.aclose()


async def test_base_override_does_not_use_pinned_transport() -> None:
    http = DiscoveryHttp(user_agent="t", base_override="http://127.0.0.1:9")
    assert not isinstance(http._client._transport, jobtext.PinnedTransport)
    await http.aclose()
    default = DiscoveryHttp(user_agent="t")
    assert isinstance(default._client._transport, jobtext.PinnedTransport)
    await default.aclose()
