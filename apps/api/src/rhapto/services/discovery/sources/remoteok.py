from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from rhapto.services.discovery.offload import parse_off_loop
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp
    from rhapto.services.discovery.search import SearchSpec


@register
class RemoteOkSource:
    info: ClassVar[SourceInfo] = SourceInfo("remoteok", "aggregator", "RemoteOK", False)

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]:
        data = await http.get_json("https://remoteok.com/api")
        items = data if isinstance(data, list) else []
        return await parse_off_loop(_parse_remoteok, list(items), keywords)

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        return await self.fetch(http, board=None, keywords=list(spec.keywords))


def _parse_remoteok(chunk: list[Any], keywords: list[str]) -> list[Posting]:
    out: list[Posting] = []
    for item in chunk:
        if not isinstance(item, dict) or "position" not in item:
            continue  # the first element is a legal notice
        try:
            title = str(item["position"])
            text = html_to_text(str(item.get("description") or ""))
            tags = " ".join(str(t) for t in item.get("tags") or [])
            if not matches_keywords(keywords, title, text, tags):
                continue
            out.append(
                Posting(
                    external_id=str(item["id"]),
                    company=str(item.get("company") or "Unknown"),
                    title=title,
                    location=str(item.get("location")) if item.get("location") else None,
                    url=str(item["url"]),
                    jd_text=text or title,
                    posted_at=parse_iso(item.get("date")),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out
