from __future__ import annotations

import asyncio
import sys
import threading
import time
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec
from rhapto.services.discovery.sources import greenhouse as greenhouse_mod
from rhapto.services.discovery.sources.adzuna import AdzunaSource
from rhapto.services.discovery.sources.ashby import AshbySource
from rhapto.services.discovery.sources.greenhouse import GreenhouseSource
from rhapto.services.discovery.sources.hn_hiring import HnHiringSource
from rhapto.services.discovery.sources.lever import LeverSource
from rhapto.services.discovery.sources.remoteok import RemoteOkSource
from rhapto.services.discovery.sources.remotive import RemotiveSource
from rhapto.services.discovery.sources.workday import WorkdaySource

SPEC = SearchSpec(keywords=())
ADZUNA_CREDS = {"app_id": "app-id-fixture", "app_key": "app-key-fixture"}

GREENHOUSE_BODY: dict[str, Any] = {
    "jobs": [
        {
            "id": 1,
            "title": "Program Manager",
            "content": "<p>Lead delivery.</p>",
            "absolute_url": "https://boards.example/acme/1",
            "company_name": "Acme",
            "location": {"name": "Denver, CO"},
            "first_published": "2026-09-01T00:00:00Z",
        }
    ]
}

LEVER_BODY: list[dict[str, Any]] = [
    {
        "id": "lev-1",
        "text": "Program Manager",
        "description": "<p>Lead delivery.</p>",
        "hostedUrl": "https://jobs.example/lev-1",
        "categories": {"location": "Denver, CO"},
        "createdAt": 1788000000000,
    }
]

ASHBY_BODY: dict[str, Any] = {
    "jobs": [
        {
            "id": "ash-1",
            "title": "Program Manager",
            "descriptionHtml": "<p>Lead delivery.</p>",
            "jobUrl": "https://jobs.example/ash-1",
            "location": "Denver, CO",
            "publishedAt": "2026-09-01T00:00:00Z",
        }
    ]
}

REMOTEOK_BODY: list[dict[str, Any]] = [
    {"legal": "notice, not a job"},
    {
        "id": "rok-1",
        "position": "Program Manager",
        "description": "<p>Lead delivery.</p>",
        "company": "Acme",
        "url": "https://remoteok.example/rok-1",
        "location": "Remote",
        "tags": ["pm"],
        "date": "2026-09-01T00:00:00+00:00",
    },
]

REMOTIVE_BODY: dict[str, Any] = {
    "jobs": [
        {
            "id": 7,
            "title": "Program Manager",
            "company_name": "Acme",
            "candidate_required_location": "USA",
            "url": "https://remotive.example/7",
            "description": "<p>Lead delivery.</p>",
            "publication_date": "2026-09-02T00:00:00",
        }
    ]
}

ADZUNA_BODY: dict[str, Any] = {
    "results": [
        {
            "id": 5,
            "title": "Program Manager",
            "description": "<p>Lead delivery.</p>",
            "redirect_url": "https://adzuna.example/5",
            "company": {"display_name": "Acme"},
            "location": {"display_name": "Denver, CO"},
            "created": "2026-09-02T00:00:00Z",
        }
    ]
}

HN_ROUTES: dict[str, Any] = {
    "hn.algolia.com/api/v1/search_by_date": {"hits": [{"objectID": "99"}]},
    "hn.algolia.com/api/v1/items/99": {
        "children": [
            {
                "id": 5,
                "text": "<p>Acme | Program Manager | Denver, CO</p><p>Lead delivery.</p>",
                "created_at": "2026-09-01T00:00:00Z",
            }
        ]
    },
}

WORKDAY_ROUTES: dict[str, Any] = {
    "/wday/cxs/acme/Careers/job/Denver/PM_R1": {
        "jobPostingInfo": {
            "title": "Program Manager",
            "jobDescription": "<p>Lead delivery.</p>",
            "jobReqId": "R1",
            "location": "Denver, CO",
        }
    },
    "/wday/cxs/acme/Careers/jobs": {
        "total": 1,
        "jobPostings": [
            {"externalPath": "/job/Denver/PM_R1", "title": "Program Manager"},
        ],
    },
}

Runner = Callable[[Any], Awaitable[list[Posting]]]

#: name -> (module under sources/, fake routes, the adapter call)
CASES: dict[str, tuple[str, dict[str, Any], Runner]] = {
    "greenhouse": (
        "greenhouse",
        {"boards-api.greenhouse.io": GREENHOUSE_BODY},
        lambda h: GreenhouseSource().fetch(h, board="acme", keywords=[]),
    ),
    "lever": (
        "lever",
        {"api.lever.co": LEVER_BODY},
        lambda h: LeverSource().fetch(h, board="acme", keywords=[]),
    ),
    "ashby": (
        "ashby",
        {"api.ashbyhq.com": ASHBY_BODY},
        lambda h: AshbySource().fetch(h, board="acme", keywords=[]),
    ),
    "remoteok": (
        "remoteok",
        {"remoteok.com/api": REMOTEOK_BODY},
        lambda h: RemoteOkSource().fetch(h, board=None, keywords=[]),
    ),
    "remotive": (
        "remotive",
        {"remotive.com/api/remote-jobs": REMOTIVE_BODY},
        lambda h: RemotiveSource().fetch_search(h, SPEC, {}),
    ),
    "adzuna": (
        "adzuna",
        {"api.adzuna.com": ADZUNA_BODY},
        lambda h: AdzunaSource().fetch_search(h, SPEC, ADZUNA_CREDS),
    ),
    "hn_hiring": (
        "hn_hiring",
        HN_ROUTES,
        lambda h: HnHiringSource().fetch(h, board=None, keywords=[]),
    ),
    "workday": (
        "workday",
        WORKDAY_ROUTES,
        lambda h: WorkdaySource().fetch(h, board="acme.wd5/Careers", keywords=[]),
    ),
}


@pytest.fixture(autouse=True)
def fast_switch() -> Iterator[None]:
    old = sys.getswitchinterval()
    sys.setswitchinterval(0.001)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


class Heartbeat:
    def __init__(self) -> None:
        self.max_gap = 0.0
        self._stop = False

    async def run(self) -> None:
        last = time.perf_counter()
        while not self._stop:
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            self.max_gap = max(self.max_gap, now - last)
            last = now

    def stop(self) -> None:
        self._stop = True


async def _with_heartbeat(work: Awaitable[Any]) -> float:
    hb = Heartbeat()
    task = asyncio.create_task(hb.run())
    await asyncio.sleep(0.02)
    try:
        await work
    finally:
        hb.stop()
        await task
    return hb.max_gap


@pytest.mark.parametrize("name", sorted(CASES))
async def test_adapter_parses_html_off_the_loop_thread(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    import importlib

    module_name, routes, run = CASES[name]
    module = importlib.import_module(f"rhapto.services.discovery.sources.{module_name}")
    real_html_to_text = module.html_to_text
    seen: list[int] = []

    def recording(value: str) -> str:
        seen.append(threading.get_ident())
        return str(real_html_to_text(value))

    monkeypatch.setattr(module, "html_to_text", recording)
    loop_thread = threading.get_ident()

    postings = await run(FakeDiscoveryHttp(routes))

    assert postings, "the fixture must reach html_to_text"
    assert seen, "the adapter must call html_to_text through its module global"
    assert loop_thread not in seen


async def test_large_greenhouse_board_does_not_starve_a_fast_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def burn_25ms(value: str) -> str:
        end = time.perf_counter() + 0.025
        while time.perf_counter() < end:
            pass
        return value

    monkeypatch.setattr(greenhouse_mod, "html_to_text", burn_25ms)
    jobs = [
        {
            "id": i,
            "title": f"Program Manager {i}",
            "content": "<p>Lead delivery.</p>",
            "absolute_url": f"https://boards.example/acme/{i}",
            "company_name": "Acme",
        }
        for i in range(80)
    ]
    http = FakeDiscoveryHttp({"boards-api.greenhouse.io": {"jobs": jobs}})

    results: list[list[Posting]] = []

    async def fetch() -> None:
        results.append(
            await GreenhouseSource().fetch(http, board="acme", keywords=[])  # type: ignore[arg-type]
        )

    gap = await _with_heartbeat(fetch())

    assert len(results[0]) == 80
    assert gap < 0.25


async def test_greenhouse_and_remotive_output_equal_the_inline_reference() -> None:
    from rhapto.services.discovery.sources.greenhouse import _parse_greenhouse
    from rhapto.services.discovery.sources.remotive import _parse_chunk

    gh_http = FakeDiscoveryHttp({"boards-api.greenhouse.io": GREENHOUSE_BODY})
    fetched_gh = await GreenhouseSource().fetch(gh_http, board="acme", keywords=[])  # type: ignore[arg-type]
    assert fetched_gh == _parse_greenhouse(GREENHOUSE_BODY["jobs"], "acme", [])

    rm_http = FakeDiscoveryHttp({"remotive.com/api/remote-jobs": REMOTIVE_BODY})
    fetched_rm = await RemotiveSource().fetch_search(rm_http, SPEC, {})  # type: ignore[arg-type]
    reference = _parse_chunk(REMOTIVE_BODY["jobs"], SPEC)[:SEARCH_CAP]
    assert fetched_rm == reference
