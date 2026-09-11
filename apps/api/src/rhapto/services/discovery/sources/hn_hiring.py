from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22who%20is%20hiring%22&tags=story,author_whoishiring&hitsPerPage=1"
)
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


def parse_header(first_line: str) -> tuple[str, str, str | None]:
    """'Company | Role | Location | ...' -> (company, role, location); role falls back to the whole line."""
    parts = [p.strip() for p in first_line.split("|")]
    if len(parts) >= 2 and parts[0] and parts[1]:
        return parts[0], parts[1], (parts[2] if len(parts) > 2 and parts[2] else None)
    return (parts[0] or "Unknown"), first_line.strip()[:200], None


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
                company, title, location = parse_header(first_line)
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
