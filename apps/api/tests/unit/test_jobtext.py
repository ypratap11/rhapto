import httpx
import pytest

import rhapto.services.jobtext as jobtext
from rhapto.services.jobtext import JobTextError, dedupe_hash, fetch_job_text

HTML = (
    "<html><body><nav>menu</nav><main><h1>Data Platform PM</h1>"
    + "<p>"
    + "We need Snowflake migration experience. " * 20
    + "</p></main></body></html>"
)

TWO_PARAGRAPH_HTML = (
    "<html><body><main>"
    + "<p>"
    + "We need Snowflake migration experience. " * 10
    + "</p>"
    + "<p>"
    + "Remote work and quarterly OKRs are required. " * 10
    + "</p>"
    + "</main></body></html>"
)


@pytest.fixture(autouse=True)
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["93.184.216.34"])


def test_dedupe_hash_normalises_whitespace_and_case() -> None:
    assert dedupe_hash("Hello   World\n") == dedupe_hash("hello world")
    assert dedupe_hash("a") != dedupe_hash("b")
    assert len(dedupe_hash("x")) == 64


async def test_fetch_extracts_main_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await fetch_job_text("https://example.com/job", client=client)
    assert "Snowflake migration" in text and "<p>" not in text


async def test_fetch_extracts_both_paragraphs() -> None:
    """Regression guard for the html_to_text refactor: a two-paragraph page must still yield
    both paragraphs' text, not just the first."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=TWO_PARAGRAPH_HTML, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await fetch_job_text("https://example.com/job", client=client)
    assert "Snowflake migration" in text
    assert "quarterly OKRs" in text


async def test_fetch_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="404"):
            await fetch_job_text("https://example.com/missing", client=client)


async def test_fetch_too_little_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><p>tiny</p></body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="too little"):
            await fetch_job_text("https://example.com/tiny", client=client)


def test_fetch_rejects_non_http_urls() -> None:
    import asyncio

    with pytest.raises(JobTextError, match="http"):
        asyncio.run(fetch_job_text("file:///etc/passwd"))


async def test_rejects_loopback_and_private_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["127.0.0.1"])
    with pytest.raises(JobTextError, match="not allowed"):
        await fetch_job_text("http://localhost/jobs")
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["10.0.0.5"])
    with pytest.raises(JobTextError, match="not allowed"):
        await fetch_job_text("http://intranet.example/jobs")


async def test_redirect_to_private_host_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    hops = {"example.com": ["93.184.216.34"], "169.254.169.254": ["169.254.169.254"]}
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: hops[host])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "example.com":
            return httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data"}
            )
        return httpx.Response(200, text="should never be fetched")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="not allowed"):
            await fetch_job_text("https://example.com/job", client=client)


async def test_redirect_to_public_host_is_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(301, headers={"location": "/new"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert "Snowflake migration" in await fetch_job_text(
            "https://example.com/old", client=client
        )


async def test_too_many_redirects() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/again"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="too many redirects"):
            await fetch_job_text("https://example.com/loop", client=client)


async def test_rejects_ipv4_mapped_and_nat64_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["::ffff:127.0.0.1"])
    with pytest.raises(JobTextError, match="not allowed"):
        await fetch_job_text("http://example.com/jobs")
    monkeypatch.setattr(jobtext, "resolve_host", lambda host: ["64:ff9b::7f00:1"])
    with pytest.raises(JobTextError, match="not allowed"):
        await fetch_job_text("http://example.com/jobs")


async def test_oversized_body_is_rejected() -> None:
    """A hostile or broken host must not be able to drive the process into OOM."""
    body = b"<html><body><p>" + b"x" * (6 * 1024 * 1024) + b"</p></body></html>"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=body, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="page too large"):
            await fetch_job_text("https://example.com/huge", client=client)


async def test_unsupported_content_type_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"%PDF-1.7 ...", headers={"content-type": "application/pdf"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="unsupported content type"):
            await fetch_job_text("https://example.com/job.pdf", client=client)


async def test_missing_content_type_is_allowed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=HTML.encode(), headers={"content-length": str(len(HTML))}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert "Snowflake migration" in await fetch_job_text(
            "https://example.com/job", client=client
        )
