from __future__ import annotations

import re
from typing import TYPE_CHECKING, ClassVar

from rhapto.engine.scoring import NON_US_CITIES, NON_US_COUNTRIES, US_STATES
from rhapto.engine.select import keyword_matches
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp
    from rhapto.services.discovery.search import SearchSpec

SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22who%20is%20hiring%22&tags=story,author_whoishiring&hitsPerPage=1"
)
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"

_MODE_WORDS = ("remote", "onsite", "on-site", "hybrid", "visa")

#: Employment terms and pay: never a title. ("$" is tested separately.)
_TERMS_WORDS = (
    "full-time",
    "full time",
    "part-time",
    "part time",
    "contract",
    "contractor",
    "salary",
    "equity",
    "relocation",
    "benefits",
)

#: A segment containing one of these is a role, whatever else it mentions ("Remote Software
#: Engineer", "Software Engineer, IN"): the guard that stops a real job being skipped as a place.
_ROLE_WORDS = (
    "engineer",
    "engineers",
    "engineering",
    "developer",
    "manager",
    "designer",
    "analyst",
    "scientist",
    "lead",
    "director",
    "architect",
    "specialist",
    "recruiter",
    "administrator",
    "coordinator",
    "consultant",
    "officer",
    "intern",
    "researcher",
    "writer",
    "accountant",
    "marketer",
    "representative",
    "executive",
    "associate",
    "sre",
    "devops",
    "founder",
    "president",
    "head",
)

#: US metros and abbreviations are not in `engine/scoring.py`'s tables (states, non-US countries,
#: non-US cities), so the common ones are listed here.
_US_METROS = (
    "nyc",
    "new york city",
    "sf",
    "san francisco",
    "sf bay area",
    "bay area",
    "los angeles",
    "la",
    "seattle",
    "boston",
    "austin",
    "chicago",
    "denver",
    "atlanta",
    "dallas",
    "houston",
    "miami",
    "portland",
    "san diego",
    "san jose",
    "palo alto",
    "mountain view",
    "sunnyvale",
    "santa clara",
    "menlo park",
    "redwood city",
    "washington dc",
    "dc",
    "cambridge",
    "pittsburgh",
    "philadelphia",
    "raleigh",
    "salt lake city",
    "boulder",
    "nashville",
    "detroit",
    "minneapolis",
)

_PLACES = frozenset(
    {name.casefold() for name in NON_US_COUNTRIES}
    | {city.casefold() for city, _ in NON_US_CITIES}
    | {name.casefold() for name in US_STATES.values()}
    | set(_US_METROS)
    | {"us", "usa", "u.s.", "u.s.a.", "united states", "worldwide", "global", "anywhere"}
)

#: Splits "Santa Clara, CA and Berlin, Germany" and "Denver, CO or Remote" into tokens.
_TOKEN_SPLIT = re.compile(r"\s*(?:,|/|;|&|\(|\)|\band\b|\bor\b|\s[-–—]\s)\s*", re.IGNORECASE)


def _has_role_word(segment: str) -> bool:
    return any(keyword_matches(word, segment) for word in _ROLE_WORDS)


def looks_like_location(segment: str) -> bool:
    """Does this header segment read as a location or work mode rather than a job title?

    Two-letter state codes are compared case-sensitively ("CA" is California, "Ca" is not), and
    tokens are compared whole, so "Software Engineer, Infrastructure" and "Washington Post
    Reporter" are not places.
    """
    if _has_role_word(segment):
        return False
    if any(keyword_matches(word, segment) for word in _MODE_WORDS):
        return True
    for raw in _TOKEN_SPLIT.split(segment):
        token = raw.strip().strip(".")
        if token and (token in US_STATES or token.casefold() in _PLACES):
            return True
    return False


def looks_like_terms(segment: str) -> bool:
    """Employment type or pay ("Full-time", "$150k-$180k"): never a title."""
    if _has_role_word(segment):
        return False
    return "$" in segment or any(keyword_matches(word, segment) for word in _TERMS_WORDS)


def parse_header(first_line: str) -> tuple[str, str, str | None] | None:
    """'Company | Role | Location | ...' -> (company, role, location), or None to skip the posting.

    The role is the first segment after the company that contains a role word and is not a
    location, work mode or employment terms; failing that, the first segment that is not one of
    those. A header with no `|` is unchanged: the whole line is the title. With a `|` but no usable
    segment ("Acme | Remote (US only)") the posting is skipped -- a place or a work mode is not a
    title.
    """
    parts = [p.strip() for p in first_line.split("|")]
    company = parts[0] or "Unknown"
    if len(parts) < 2:
        return company, first_line.strip()[:200], None
    rest = parts[1:]
    candidates = [
        i
        for i, p in enumerate(rest)
        if p and not looks_like_location(p) and not looks_like_terms(p)
    ]
    if not candidates:
        return None
    role_index = next((i for i in candidates if _has_role_word(rest[i])), candidates[0])
    location = next((p for p in rest if p and looks_like_location(p)), None)
    following = rest[role_index + 1] if role_index + 1 < len(rest) else ""
    if location is None and following and not looks_like_terms(following):
        location = following
    return company, rest[role_index], location


@register
class HnHiringSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "hn-hiring", "aggregator", "Hacker News Who's Hiring", False
    )

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]:
        search = await http.get_json(SEARCH_URL)
        hits = search.get("hits") if isinstance(search, dict) else None
        if not hits:
            raise SourceError("no Who is hiring thread found")
        story_id = str(hits[0]["objectID"])
        item = await http.get_json(ITEM_URL.format(id=story_id))
        out: list[Posting] = []
        for comment in item.get("children", []) if isinstance(item, dict) else []:
            try:
                raw = comment.get("text")
                if not raw:
                    continue
                text = html_to_text(str(raw))
                first_line, _, rest = text.partition("\n")
                parsed = parse_header(first_line)
                if parsed is None:  # the header names no role (only a place or a work mode)
                    continue
                company, title, location = parsed
                body = rest.strip() or text
                if not matches_keywords(keywords, title, body, first_line):
                    continue
                out.append(
                    Posting(
                        external_id=str(comment["id"]),
                        company=company,
                        title=title,
                        location=location,
                        url=f"https://news.ycombinator.com/item?id={comment['id']}",
                        jd_text=body,
                        posted_at=parse_iso(comment.get("created_at")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        return await self.fetch(http, board=None, keywords=list(spec.keywords))
