from datetime import UTC, datetime

from test_discovery_sources import fake_http_for

from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import get_aggregator, get_source


async def test_remoteok_skips_legal_notice_and_filters_keywords() -> None:
    postings = await get_source("remoteok").fetch(
        fake_http_for("remoteok"), board=None, keywords=["ETL", "program manager"]
    )
    assert [p.external_id for p in postings] == ["1500001"]
    p = postings[0]
    assert (
        p.company == "ExampleCo" and p.title == "Data Program Manager" and p.location == "Worldwide"
    )
    assert "<strong>" not in p.jd_text and "ETL cutover" in p.jd_text
    assert p.posted_at == datetime(2026, 9, 8, 14, 57, 50, tzinfo=UTC)
    assert p.url == "https://remoteOK.com/remote-jobs/1500001"


async def test_remoteok_keywords_match_tags_too() -> None:
    postings = await get_source("remoteok").fetch(
        fake_http_for("remoteok"), board=None, keywords=["coffee"]
    )
    assert [p.external_id for p in postings] == ["1500002"]


async def test_hn_hiring_parses_header_line_and_skips_empty_comments() -> None:
    postings = await get_source("hn-hiring").fetch(
        fake_http_for("hn-hiring"), board=None, keywords=["program manager"]
    )
    assert [p.external_id for p in postings] == ["49500002"]
    p = postings[0]
    assert (
        p.company == "ExampleCo"
        and p.title == "Data Program Manager"
        and p.location == "Denver, CO or Remote"
    )
    assert p.url == "https://news.ycombinator.com/item?id=49500002"
    assert "analytics data platform" in p.jd_text and "<p>" not in p.jd_text
    assert p.posted_at == datetime(2026, 9, 1, 15, 5, tzinfo=UTC)


async def test_remoteok_fetch_search_matches_fetch() -> None:
    keywords = ["ETL", "program manager"]
    expected = await get_source("remoteok").fetch(
        fake_http_for("remoteok"), board=None, keywords=keywords
    )
    postings = await get_aggregator("remoteok").fetch_search(
        fake_http_for("remoteok"), SearchSpec(keywords=tuple(keywords)), {}
    )
    assert postings == expected


async def test_hn_hiring_fetch_search_matches_fetch() -> None:
    keywords = ["program manager"]
    expected = await get_source("hn-hiring").fetch(
        fake_http_for("hn-hiring"), board=None, keywords=keywords
    )
    postings = await get_aggregator("hn-hiring").fetch_search(
        fake_http_for("hn-hiring"), SearchSpec(keywords=tuple(keywords)), {}
    )
    assert postings == expected
