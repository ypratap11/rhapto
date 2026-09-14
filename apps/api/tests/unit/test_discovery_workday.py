"""Workday board adapter: board parsing, paged search, capped detail fetches, field mapping."""

from datetime import UTC, datetime
from typing import Any

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.sources import get_source
from rhapto.services.discovery.sources.base import SourceError
from rhapto.services.discovery.sources.workday import MAX_DETAIL_FETCHES, parse_board

BOARD = "exampleco.wd5/ExampleCoCareers"
SEARCH_URL = "https://exampleco.wd5.myworkdayjobs.com/wday/cxs/exampleco/ExampleCoCareers/jobs"


def summary(req: str, title: str = "Data Program Manager", location: str = "Denver, CO") -> Any:
    slug = title.replace(",", "").replace(" ", "-")
    return {
        "title": title,
        "externalPath": f"/job/Denver/{slug}_{req}",
        "locationsText": location,
        "postedOn": "Posted 3 Days Ago",
        "bulletFields": [req],
    }


def detail(req: str, title: str = "Data Program Manager", description: str = "") -> Any:
    return {
        "jobPostingInfo": {
            "title": title,
            "jobDescription": description or f"<p>Own the {title} charter.</p>",
            "jobReqId": req,
            "startDate": "2026-09-01",
            "location": "Denver, CO",
            "externalUrl": f"https://exampleco.wd5.myworkdayjobs.com/en-US/ExampleCoCareers/job/{req}",
            "postedOn": "Posted 3 Days Ago",
        }
    }


class WorkdayFake(FakeDiscoveryHttp):
    """Answers search POSTs from a per-search-term list (paging honoured) and detail GETs by path."""

    def __init__(
        self, by_term: dict[str, list[Any]], details: dict[str, Any] | None = None
    ) -> None:
        super().__init__({})
        self.by_term = by_term
        self.details = details or {}
        self.searches: list[tuple[str, int]] = []

    async def post_json(self, url: str, body: dict[str, Any]) -> Any:
        self.posts.append(("POST", url, body))
        term = str(body["searchText"])
        offset, limit = int(body["offset"]), int(body["limit"])
        items = self.by_term.get(term, [])
        self.searches.append((term, offset))
        return {"total": len(items), "jobPostings": items[offset : offset + limit]}

    async def get_json(self, url: str) -> Any:
        self.calls.append(url)
        for path, value in self.details.items():
            if url.endswith(path):
                return value
        raise SourceError(f"no fake detail route for {url}")


def fake_for(summaries: list[Any], *, term: str = "", **detail_kwargs: Any) -> WorkdayFake:
    details = {}
    for item in summaries:
        req = item["bulletFields"][0]
        details[item["externalPath"]] = detail(req, title=item["title"], **detail_kwargs)
    return WorkdayFake({term: summaries}, details)


def test_parse_board_accepts_host_prefix_and_site() -> None:
    assert parse_board("nvidia.wd5/NVIDIAExternalCareerSite") == (
        "nvidia.wd5",
        "nvidia",
        "NVIDIAExternalCareerSite",
    )


@pytest.mark.parametrize("board", ["nvidia", "nvidia.wd5/", "/Site", "a b/c", "", None])
def test_parse_board_rejects_malformed_boards(board: str | None) -> None:
    with pytest.raises(SourceError, match="workday board must look like"):
        parse_board(board)


async def test_search_pages_by_offset_until_total_is_reached() -> None:
    http = fake_for([summary(f"JR{i:04d}") for i in range(45)])
    postings = await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert [(url, body["offset"], body["limit"]) for _, url, body in http.posts] == [
        (SEARCH_URL, 0, 20),
        (SEARCH_URL, 20, 20),
        (SEARCH_URL, 40, 20),
    ]
    assert len(postings) == min(45, MAX_DETAIL_FETCHES)


async def test_one_search_per_keyword_and_dedupe_across_keywords() -> None:
    shared = summary("JR0001", title="Data Program Manager")
    only_etl = summary("JR0002", title="ETL Engineer")
    http = WorkdayFake(
        {"data": [shared], "ETL": [shared, only_etl]},
        {
            shared["externalPath"]: detail("JR0001", title="Data Program Manager"),
            only_etl["externalPath"]: detail("JR0002", title="ETL Engineer"),
        },
    )
    postings = await get_source("workday").fetch(http, board=BOARD, keywords=["data", "ETL"])
    assert http.searches == [("data", 0), ("ETL", 0)]
    assert [p.external_id for p in postings] == ["JR0001", "JR0002"]
    # the shared posting's detail is fetched once, not once per keyword
    assert http.calls.count(f"{SEARCH_URL[: -len('/jobs')]}{shared['externalPath']}") == 1


async def test_no_keywords_searches_once_with_empty_text() -> None:
    http = fake_for([summary("JR0001")])
    await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert [body["searchText"] for _, _, body in http.posts] == [""]
    assert http.posts[0][2]["appliedFacets"] == {}


async def test_keywords_match_title_first_then_description() -> None:
    by_title = summary("JR0001", title="GenAI Program Manager")
    by_body = summary("JR0002", title="Platform Lead")
    unrelated = summary("JR0003", title="Facilities Coordinator")
    http = WorkdayFake(
        {"GenAI": [by_title, by_body, unrelated]},
        {
            by_title["externalPath"]: detail("JR0001", title="GenAI Program Manager"),
            by_body["externalPath"]: detail(
                "JR0002", title="Platform Lead", description="<p>Lead our GenAI platform.</p>"
            ),
            unrelated["externalPath"]: detail(
                "JR0003", title="Facilities Coordinator", description="<p>Badge desk.</p>"
            ),
        },
    )
    postings = await get_source("workday").fetch(http, board=BOARD, keywords=["GenAI"])
    assert [p.external_id for p in postings] == ["JR0001", "JR0002"]


async def test_detail_fetches_are_capped_per_poll() -> None:
    http = fake_for([summary(f"JR{i:04d}") for i in range(MAX_DETAIL_FETCHES + 1)])
    postings = await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert len(http.calls) == MAX_DETAIL_FETCHES
    assert len(postings) == MAX_DETAIL_FETCHES


async def test_maps_ids_company_url_location_and_posted_at() -> None:
    item = summary("JR1234567")
    http = WorkdayFake({"": [item]}, {item["externalPath"]: detail("JR1234567")})
    (posting,) = await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert posting.external_id == "JR1234567"
    assert posting.company == "exampleco"  # tenant stands in until the poller overrides it
    assert posting.title == "Data Program Manager" and posting.location == "Denver, CO"
    assert posting.url == (
        "https://exampleco.wd5.myworkdayjobs.com/en-US/ExampleCoCareers/job/JR1234567"
    )
    assert "Own the Data Program Manager charter." in posting.jd_text
    assert "<p>" not in posting.jd_text
    assert posting.posted_at == datetime(2026, 9, 1, tzinfo=UTC)


async def test_falls_back_to_path_tail_public_url_and_summary_location() -> None:
    item = summary("JR7", location="Remote - US")
    thin = {"jobPostingInfo": {"title": "Data Program Manager", "jobDescription": "<p>Body</p>"}}
    http = WorkdayFake({"": [item]}, {item["externalPath"]: thin})
    (posting,) = await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert posting.external_id == "Data-Program-Manager_JR7"
    assert posting.location == "Remote - US"
    assert posting.url == (
        "https://exampleco.wd5.myworkdayjobs.com/ExampleCoCareers"
        "/job/Denver/Data-Program-Manager_JR7"
    )
    assert posting.posted_at is None


async def test_malformed_postings_are_skipped_not_fatal() -> None:
    good = summary("JR0002")
    http = WorkdayFake(
        {"": [{"title": "No path"}, {"externalPath": "/job/Denver/Broken_JR0001"}, good]},
        {
            "/job/Denver/Broken_JR0001": {"jobPostingInfo": []},
            good["externalPath"]: detail("JR0002"),
        },
    )
    postings = await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert [p.external_id for p in postings] == ["JR0002"]


async def test_bad_board_raises_source_error_before_any_request() -> None:
    http = WorkdayFake({})
    with pytest.raises(SourceError, match="workday board must look like"):
        await get_source("workday").fetch(http, board="exampleco", keywords=[])
    assert http.posts == [] and http.calls == []


async def test_a_vanished_posting_detail_does_not_fail_the_board() -> None:
    gone = summary("JR0001", title="Data Program Manager")
    kept = summary("JR0002", title="Data Program Manager II")
    http = WorkdayFake(
        {"": [gone, kept]},
        {
            gone["externalPath"]: SourceError("404 Not Found"),
            kept["externalPath"]: detail("JR0002", title="Data Program Manager II"),
        },
    )
    postings = await get_source("workday").fetch(http, board=BOARD, keywords=[])
    assert [p.external_id for p in postings] == ["JR0002"]
