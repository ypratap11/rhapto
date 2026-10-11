from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import get_aggregator, get_source

SPEC = SearchSpec(keywords=("program manager",), location=None)


def make(url: str) -> Posting:
    return Posting(
        external_id="1",
        company="ExampleCo",
        title="Program Manager",
        url=url,
        jd_text="Run programs for the platform team.",
    )


@pytest.mark.parametrize(
    "bad",
    [
        "javascript:alert(1)",
        "data:text/html,x",
        "file:///etc/passwd",
        "ftp://x.com/a",
        "example.com/a",
        "http:///x",
        "None",
        "",
        "  ",
        "https://x.com/a\nb",
    ],
)
def test_posting_rejects_bad_urls(bad: str) -> None:
    with pytest.raises(ValidationError):
        make(bad)


def test_posting_strips_url_whitespace() -> None:
    assert make("  https://x.com/a  ").url == "https://x.com/a"


def _adzuna_item(n: int, url: str) -> dict[str, Any]:
    return {
        "id": str(n),
        "title": "Program Manager",
        "company": {"display_name": "ExampleCo"},
        "location": {"display_name": "Denver, CO"},
        "redirect_url": url,
        "description": "Run programs.",
        "created": "2026-09-03T08:00:00Z",
    }


async def test_adzuna_skips_an_item_with_a_bad_url_and_keeps_the_rest() -> None:
    body = {
        "results": [
            _adzuna_item(1, "https://www.adzuna.com/details/1"),
            _adzuna_item(2, "javascript:alert(1)"),
            _adzuna_item(3, "https://www.adzuna.com/details/3"),
        ]
    }
    http = FakeDiscoveryHttp({"api.adzuna.com": body})
    creds = {"app_id": "id-1", "app_key": "key-1"}
    postings = await get_aggregator("adzuna").fetch_search(http, SPEC, creds)  # type: ignore[arg-type]
    assert [p.external_id for p in postings] == ["1", "3"]


async def test_greenhouse_skips_a_job_with_a_bad_url_and_keeps_the_rest() -> None:
    def job(n: int, url: str) -> dict[str, Any]:
        return {
            "id": n,
            "title": "Program Manager",
            "company_name": "ExampleCo",
            "location": {"name": "Denver, CO"},
            "absolute_url": url,
            "content": "<p>Run programs.</p>",
            "first_published": "2026-09-01T10:00:00Z",
        }

    body = {
        "jobs": [
            job(1, "https://boards.greenhouse.io/exampleco/jobs/1"),
            job(2, "javascript:alert(1)"),
            job(3, "https://boards.greenhouse.io/exampleco/jobs/3"),
        ]
    }
    http = FakeDiscoveryHttp({"boards-api.greenhouse.io": body})
    postings = await get_source("greenhouse").fetch(http, board="exampleco", keywords=[])  # type: ignore[arg-type]
    assert [p.external_id for p in postings] == ["1", "3"]
