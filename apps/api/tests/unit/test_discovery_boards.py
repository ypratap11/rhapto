from datetime import UTC, datetime

from test_discovery_sources import fake_http_for

from rhapto.services.discovery.sources import get_source


async def test_greenhouse_unescapes_html_and_keeps_ids_and_dates() -> None:
    postings = await get_source("greenhouse").fetch(
        fake_http_for("greenhouse"), board="exampleco", keywords=[]
    )
    assert [p.external_id for p in postings] == ["4001", "4002"]
    first = postings[0]
    assert first.company == "ExampleCo" and first.location == "Denver, CO"
    assert (
        "Data Program Manager" in first.jd_text
        and "&lt;" not in first.jd_text
        and "<" not in first.jd_text
    )
    assert first.posted_at == datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    assert first.url == "https://boards.greenhouse.io/exampleco/jobs/4001"


async def test_greenhouse_keyword_filter_applies_to_title_and_text() -> None:
    postings = await get_source("greenhouse").fetch(
        fake_http_for("greenhouse"), board="exampleco", keywords=["GenAI"]
    )
    assert [p.external_id for p in postings] == ["4002"]


async def test_lever_joins_plain_sections_and_converts_epoch_ms() -> None:
    (p,) = await get_source("lever").fetch(fake_http_for("lever"), board="exampleco", keywords=[])
    assert p.title == "Senior Program Manager, Data Platform" and p.location == "Seattle, WA"
    assert "warehouse consolidation" in p.jd_text and "Own analytics enablement" in p.jd_text
    assert "equal opportunity" in p.jd_text and "<li>" not in p.jd_text
    assert p.posted_at == datetime.fromtimestamp(1788134400, tz=UTC)
    assert (
        p.company == "exampleco"
    )  # Lever has no company field; the board slug stands in until the poller overrides it


async def test_ashby_skips_unlisted_and_parses_iso() -> None:
    postings = await get_source("ashby").fetch(
        fake_http_for("ashby"), board="exampleco", keywords=[]
    )
    assert [p.title for p in postings] == ["ML Platform Program Manager"]
    assert postings[0].posted_at is not None and postings[0].posted_at.tzinfo is not None
