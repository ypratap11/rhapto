from __future__ import annotations

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.sources import get_source
from rhapto.services.discovery.sources.hn_hiring import (
    looks_like_location,
    looks_like_terms,
    parse_header,
)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (
            "ExampleCo | Data Program Manager | Denver, CO or Remote | Full-time",
            ("ExampleCo", "Data Program Manager", "Denver, CO or Remote"),
        ),
        (  # a work mode in the role's slot is skipped, and becomes the location
            "Acme | Remote (US only) | Software Engineer",
            ("Acme", "Software Engineer", "Remote (US only)"),
        ),
        (  # two places joined by "and"
            "Acme | Santa Clara, CA and Berlin, Germany | Staff Engineer",
            ("Acme", "Staff Engineer", "Santa Clara, CA and Berlin, Germany"),
        ),
        (  # "Infrastructure" after a comma is not a state code
            "Acme | Software Engineer, Infrastructure | NYC",
            ("Acme", "Software Engineer, Infrastructure", "NYC"),
        ),
        (  # a role that mentions "Remote" is still a role
            "Acme | Remote Software Engineer | NYC",
            ("Acme", "Remote Software Engineer", "NYC"),
        ),
        (  # a place name inside a longer role phrase is not a place
            "Acme | Washington Post Reporter | Remote",
            ("Acme", "Washington Post Reporter", "Remote"),
        ),
        (  # US metros are not in engine/scoring's tables: they are still places, not titles
            "Acme | San Francisco | Senior Engineer",
            ("Acme", "Senior Engineer", "San Francisco"),
        ),
        ("Acme | NYC | Backend Engineer", ("Acme", "Backend Engineer", "NYC")),
        ("Acme | SF Bay Area | Engineer", ("Acme", "Engineer", "SF Bay Area")),
        (  # the segment WITH a role word wins over an earlier non-place that has none
            "Acme | Backend Platform | Senior Engineer | Full-time",
            ("Acme", "Senior Engineer", None),
        ),
        (  # an employment term containing a role word is a title
            "Acme | Contract Manager | NYC",
            ("Acme", "Contract Manager", "NYC"),
        ),
        (  # no pipe: unchanged from today (whole line is the title, nothing is skipped)
            "Acme - Software Engineer - Remote",
            ("Acme - Software Engineer - Remote", "Acme - Software Engineer - Remote", None),
        ),
    ],
)
def test_parse_header(line: str, expected: tuple[str, str, str | None]) -> None:
    assert parse_header(line) == expected


@pytest.mark.parametrize(
    "line",
    [
        "Acme | Remote (US only)",  # only a work mode
        "Acme | Santa Clara, CA and Berlin, Germany",  # only places
        "Acme | | Remote",  # an empty segment, then a work mode
        "Acme | Georgia",  # a bare state name
        "Acme | REMOTE | Full-time | $150k",  # a work mode, an employment type and pay
    ],
)
def test_a_header_with_no_role_segment_is_skipped(line: str) -> None:
    assert parse_header(line) is None


def test_looks_like_location() -> None:
    for segment in (
        "Remote (US only)",
        "REMOTE",
        "Hybrid",
        "Onsite",
        "Visa sponsorship",
        "Santa Clara, CA and Berlin, Germany",
        "Denver, CO",
        "New York",
        "CA",
        "United States",
        "Berlin",
        "San Francisco",
        "NYC",
        "SF Bay Area",
    ):
        assert looks_like_location(segment), segment
    for segment in (
        "Software Engineer, Infrastructure",
        "Software Engineer, IN",  # a capital state code after a role word is still a role
        "Remote Software Engineer",
        "Infrastructure",
        "Ca",  # state codes are matched case-sensitively
        "Washington Post Reporter",
        "Platform",
        "Backend Engineer",
    ):
        assert not looks_like_location(segment), segment


def test_looks_like_terms() -> None:
    for segment in ("Full-time", "Part time", "$150k-$180k", "Contract", "Salary + equity"):
        assert looks_like_terms(segment), segment
    for segment in ("Contract Manager", "Senior Engineer", "Full-time Engineer"):
        assert not looks_like_terms(segment), segment


async def test_fetch_skips_location_only_headers_and_keeps_real_roles() -> None:
    routes = {
        "search_by_date?query=%22who%20is%20hiring%22": {"hits": [{"objectID": "1"}]},
        "/items/1": {
            "id": 1,
            "children": [
                {
                    "id": 11,
                    "created_at": "2026-09-01T15:05:00.000Z",
                    "text": "Acme | Remote (US only)<p>A description long enough to matter.",
                },
                {
                    "id": 12,
                    "created_at": "2026-09-01T15:06:00.000Z",
                    "text": (
                        "Acme | Santa Clara, CA and Berlin, Germany | Staff Engineer"
                        "<p>Another description long enough to matter."
                    ),
                },
            ],
        },
    }
    postings = await get_source("hn-hiring").fetch(
        FakeDiscoveryHttp(routes), board=None, keywords=[]
    )
    assert [(p.external_id, p.title, p.location) for p in postings] == [
        ("12", "Staff Engineer", "Santa Clara, CA and Berlin, Germany")
    ]
