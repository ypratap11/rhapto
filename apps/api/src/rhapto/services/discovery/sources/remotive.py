from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp


@register
class RemotiveSource:
    info: ClassVar[SourceInfo] = SourceInfo("remotive", "aggregator", "Remotive", False)

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        # Every Remotive listing is remote by definition, so an "exclude remote" search has
        # nothing to ask this source for.
        if spec.remote == "exclude":
            return []
        first = spec.keywords[0] if spec.keywords else ""
        url = f"https://remotive.com/api/remote-jobs?search={quote(first, safe='')}&limit=100"
        data = await http.get_json(url)
        if not isinstance(data, dict):
            raise SourceError("Remotive: unexpected response shape")
        jobs = data.get("jobs")
        out: list[Posting] = []
        for item in jobs if isinstance(jobs, list) else []:
            posting = self._to_posting(spec, item)
            if posting is not None:
                out.append(posting)
            if len(out) >= SEARCH_CAP:
                break
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["title"])
            text = html_to_text(str(item.get("description") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            location = str(item.get("candidate_required_location") or "") or None
            if not remote_matches(spec, location, True):
                return None
            salary = str(item.get("salary") or "").strip() or None
            return Posting(
                external_id=str(item["id"]),
                company=str(item.get("company_name") or "Unknown"),
                title=title,
                location=location,
                url=str(item["url"]),
                jd_text=text,
                posted_at=parse_iso(item.get("publication_date")),
                salary_text=salary,
            )
        except (KeyError, TypeError, ValueError):
            return None
