from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text
from rhapto.services.taxonomy import find_field

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

MAX_PAGES = 10


@register
class TheMuseSource:
    info: ClassVar[SourceInfo] = SourceInfo("themuse", "aggregator", "The Muse", False)

    def _url(self, spec: SearchSpec, page: int) -> str:
        url = f"https://www.themuse.com/api/public/jobs?page={page}"
        if spec.location:
            url += f"&location={quote(spec.location, safe='')}"
        field = find_field(spec.field)
        if field is not None:
            url += f"&category={quote(field.themuse_category, safe='')}"
        return url

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        out: list[Posting] = []
        page = 1
        while page <= MAX_PAGES and len(out) < SEARCH_CAP:
            data = await http.get_json(self._url(spec, page))
            if not isinstance(data, dict):
                raise SourceError("The Muse: unexpected response shape")
            results = data.get("results")
            for item in results if isinstance(results, list) else []:
                posting = self._to_posting(spec, item)
                if posting is not None:
                    out.append(posting)
                if len(out) >= SEARCH_CAP:
                    break
            page_count = int(data.get("page_count") or 1)
            if page >= page_count:
                break
            page += 1
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["name"])
            text = html_to_text(str(item.get("contents") or "")) or title
            locations = [str(loc.get("name") or "") for loc in item.get("locations") or []]
            location = ", ".join(loc_name for loc_name in locations if loc_name) or None
            if not matches_keywords(spec.keywords, title, text):
                return None
            is_remote = any(
                "remote" in loc_name.lower() or "flexible" in loc_name.lower()
                for loc_name in locations
            )
            if not remote_matches(spec, location, is_remote):
                return None
            return Posting(
                external_id=str(item["id"]),
                company=str((item.get("company") or {}).get("name") or "Unknown"),
                title=title,
                location=location,
                url=str((item.get("refs") or {})["landing_page"]),
                jd_text=text,
                posted_at=parse_iso(item.get("publication_date")),
            )
        except (KeyError, TypeError, ValueError):
            return None
