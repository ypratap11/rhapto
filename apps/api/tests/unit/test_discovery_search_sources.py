from __future__ import annotations

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.search import SearchSpec, query_text, remote_matches
from rhapto.services.discovery.sources import aggregator_sources, get_aggregator
from rhapto.services.discovery.sources.base import SourceError

SPEC = SearchSpec(keywords=("program manager", "delivery lead"), location="Denver, CO")


def test_query_text_joins_keywords() -> None:
    assert query_text(SPEC) == "program manager OR delivery lead"
    assert query_text(SearchSpec(keywords=())) == ""


@pytest.mark.parametrize(
    ("remote", "flag", "expected"),
    [
        ("include", True, True),
        ("include", False, True),
        ("only", True, True),
        ("only", False, False),
        ("exclude", True, False),
        ("exclude", False, True),
    ],
)
def test_remote_matches(remote: str, flag: bool, expected: bool) -> None:
    spec = SearchSpec(keywords=("pm",), remote=remote)  # type: ignore[arg-type]
    assert remote_matches(spec, None, flag) is expected


def test_remote_matches_reads_the_location_text_when_no_flag() -> None:
    spec = SearchSpec(keywords=("pm",), remote="only")
    assert remote_matches(spec, "Remote - US", None) is True
    assert remote_matches(spec, "Denver, CO", None) is False


def test_aggregator_registry_lists_seven_in_registration_order() -> None:
    assert [i.name for i in aggregator_sources()] == [
        "hn-hiring",
        "remoteok",
        "themuse",
        "remotive",
        "adzuna",
        "jooble",
        "jsearch",
    ]


def test_get_aggregator_rejects_a_board_source() -> None:
    with pytest.raises(SourceError, match="greenhouse"):
        get_aggregator("greenhouse")


def _muse_page(count: int, page: int = 1, page_count: int = 1) -> dict[str, object]:
    return {
        "page": page,
        "page_count": page_count,
        "results": [
            {
                "id": 1000 + i,
                "name": "Technical Program Manager",
                "company": {"name": "ExampleCo"},
                "locations": [{"name": "Denver, CO"}],
                "refs": {"landing_page": f"https://www.themuse.com/jobs/exampleco/tpm-{i}"},
                "contents": "<p>Run <b>programs</b> for the platform team.</p>",
                "publication_date": "2026-09-01T10:00:00Z",
            }
            for i in range(count)
        ],
    }


async def test_themuse_maps_every_field_and_quotes_the_location() -> None:
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": _muse_page(1)})
    postings = await get_aggregator("themuse").fetch_search(http, SPEC, {})  # type: ignore[arg-type]
    assert len(postings) == 1
    posting = postings[0]
    assert posting.external_id == "1000"
    assert posting.company == "ExampleCo"
    assert posting.title == "Technical Program Manager"
    assert posting.location == "Denver, CO"
    assert posting.url.endswith("/tpm-0")
    assert "Run programs" in posting.jd_text
    assert posting.posted_at is not None and posting.posted_at.tzinfo is not None
    assert "Denver%2C%20CO" in http.calls[0]


async def test_themuse_filters_on_keywords_and_stops_at_the_cap() -> None:
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": _muse_page(60, page_count=10)})
    spec = SearchSpec(keywords=("nurse",), location=None)
    assert await get_aggregator("themuse").fetch_search(http, spec, {}) == []  # type: ignore[arg-type]
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": _muse_page(60, page_count=10)})
    postings = await get_aggregator("themuse").fetch_search(http, SPEC, {})  # type: ignore[arg-type]
    assert len(postings) == 100


async def test_remotive_maps_salary_and_skips_when_remote_is_excluded() -> None:
    body = {
        "jobs": [
            {
                "id": 7,
                "title": "Delivery Lead",
                "company_name": "Remote Co",
                "candidate_required_location": "USA",
                "url": "https://remotive.com/remote-jobs/7",
                "description": "<p>Lead delivery.</p>",
                "publication_date": "2026-09-02T00:00:00",
                "salary": "$150,000 - $170,000",
            }
        ]
    }
    http = FakeDiscoveryHttp({"remotive.com/api/remote-jobs": body})
    postings = await get_aggregator("remotive").fetch_search(http, SPEC, {})  # type: ignore[arg-type]
    assert [p.salary_text for p in postings] == ["$150,000 - $170,000"]
    excluded = SearchSpec(keywords=("delivery lead",), remote="exclude")
    assert await get_aggregator("remotive").fetch_search(http, excluded, {}) == []  # type: ignore[arg-type]


async def test_adzuna_sends_both_key_fields_and_maps_salary() -> None:
    body = {
        "results": [
            {
                "id": "55",
                "title": "Program Manager",
                "company": {"display_name": "ExampleCo"},
                "location": {"display_name": "Denver, CO"},
                "redirect_url": "https://www.adzuna.com/details/55",
                "description": "Run programs.",
                "created": "2026-09-03T08:00:00Z",
                "salary_min": 150000,
                "salary_max": 170000,
            }
        ]
    }
    http = FakeDiscoveryHttp({"api.adzuna.com": body})
    creds = {"app_id": "id-1", "app_key": "key-1"}
    postings = await get_aggregator("adzuna").fetch_search(http, SPEC, creds)  # type: ignore[arg-type]
    assert postings[0].salary_text == "150000-170000"
    assert "app_id=id-1" in http.calls[0] and "app_key=key-1" in http.calls[0]
    assert "where=Denver%2C+CO" in http.calls[0] or "where=Denver%2C%20CO" in http.calls[0]


async def test_adzuna_missing_key_is_a_source_error() -> None:
    http = FakeDiscoveryHttp({"api.adzuna.com": {"results": []}})
    with pytest.raises(SourceError, match="Adzuna"):
        await get_aggregator("adzuna").fetch_search(http, SPEC, {})  # type: ignore[arg-type]


async def test_adzuna_never_puts_the_key_in_an_error() -> None:
    http = FakeDiscoveryHttp(
        {
            "api.adzuna.com": SourceError(
                "https://api.adzuna.com/v1/api/jobs/us/search/1"
                "?app_id=id-1&app_key=key-1 returned HTTP 401"
            )
        }
    )
    with pytest.raises(SourceError) as exc:
        await get_aggregator("adzuna").fetch_search(  # type: ignore[arg-type]
            http, SPEC, {"app_id": "id-1", "app_key": "key-1"}
        )
    assert "id-1" not in str(exc.value)
    assert "key-1" not in str(exc.value)
    assert "check the API key" in str(exc.value)


async def test_jooble_never_puts_the_key_in_an_error() -> None:
    http = FakeDiscoveryHttp(
        {"jooble.org/api": SourceError("https://jooble.org/api/s3cret returned HTTP 401")}
    )
    with pytest.raises(SourceError) as exc:
        await get_aggregator("jooble").fetch_search(http, SPEC, {"api_key": "s3cret"})  # type: ignore[arg-type]
    assert "s3cret" not in str(exc.value)
    assert "check the API key" in str(exc.value)


async def test_jsearch_sends_the_key_as_a_header_only() -> None:
    body = {
        "data": [
            {
                "job_id": "abc",
                "job_title": "Technical Program Manager",
                "employer_name": "ExampleCo",
                "job_city": "Denver",
                "job_state": "CO",
                "job_country": "US",
                "job_apply_link": "https://example.com/apply",
                "job_description": "Run programs.",
                "job_posted_at_datetime_utc": "2026-09-04T00:00:00Z",
                "job_is_remote": False,
                "job_min_salary": 150000,
                "job_max_salary": 170000,
            }
        ]
    }
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": body})
    postings = await get_aggregator("jsearch").fetch_search(http, SPEC, {"rapidapi_key": "rk"})  # type: ignore[arg-type]
    assert postings[0].location == "Denver, CO, US"
    assert http.headers[0]["x-rapidapi-key"] == "rk"
    assert "rk" not in http.calls[0]


async def test_a_malformed_item_is_skipped_not_fatal() -> None:
    page = _muse_page(1)
    page["results"].append({"id": 2000})  # type: ignore[attr-defined]
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": page})
    assert len(await get_aggregator("themuse").fetch_search(http, SPEC, {})) == 1  # type: ignore[arg-type]


def test_needs_key_and_fields_per_source() -> None:
    by_name = {i.name: i for i in aggregator_sources()}
    assert by_name["themuse"].needs_key is False and by_name["themuse"].fields == ()
    assert by_name["adzuna"].needs_key is True and by_name["adzuna"].fields == ("app_id", "app_key")
    assert by_name["jooble"].fields == ("api_key",)
    assert by_name["jsearch"].fields == ("rapidapi_key",)
