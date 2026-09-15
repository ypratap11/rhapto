from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlencode

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import (
    SourceError,
    SourceInfo,
    matches_keywords,
    require_credentials,
)
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text
from rhapto.services.taxonomy import find_field

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

MAX_PAGES = 4
PER_PAGE = 50


def salary_range(item: dict[str, Any]) -> str | None:
    low, high = item.get("salary_min"), item.get("salary_max")
    if not low and not high:
        return None
    if low and high:
        return f"{int(low)}-{int(high)}"
    single = low if low else high
    assert single is not None
    return str(int(single))


@register
class AdzunaSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "adzuna", "aggregator", "Adzuna", False, needs_key=True, fields=("app_id", "app_key")
    )

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        creds = require_credentials(self.info, credentials)
        out: list[Posting] = []
        for keyword in spec.keywords or ("",):
            for page in range(1, MAX_PAGES + 1):
                if len(out) >= SEARCH_CAP:
                    return out
                query = {
                    "app_id": creds["app_id"],
                    "app_key": creds["app_key"],
                    "what": keyword,
                    "results_per_page": PER_PAGE,
                    "content-type": "application/json",
                }
                if spec.location:
                    query["where"] = spec.location
                field = find_field(spec.field)
                if field is not None:
                    query["category"] = field.adzuna_category
                url = f"https://api.adzuna.com/v1/api/jobs/us/search/{page}?{urlencode(query)}"
                # Adzuna authenticates via app_id/app_key in the query string, so every error
                # raised from here is rewritten: the raw message (http.py embeds the full URL)
                # would otherwise carry both credentials into a run row and the UI.
                try:
                    data = await http.get_json(url)
                except SourceError as exc:
                    redacted = str(exc).replace(creds["app_id"], "…").replace(creds["app_key"], "…")
                    raise SourceError(f"Adzuna: check the API key ({redacted})") from None
                if not isinstance(data, dict):
                    raise SourceError("Adzuna: unexpected response shape")
                results = data.get("results")
                items = results if isinstance(results, list) else []
                for item in items:
                    posting = self._to_posting(spec, item)
                    if posting is not None:
                        out.append(posting)
                    if len(out) >= SEARCH_CAP:
                        return out
                if len(items) < PER_PAGE:
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
            location = str((item.get("location") or {}).get("display_name") or "") or None
            if not remote_matches(spec, location, None):
                return None
            return Posting(
                external_id=str(item["id"]),
                company=str((item.get("company") or {}).get("display_name") or "Unknown"),
                title=title,
                location=location,
                url=str(item["redirect_url"]),
                jd_text=text,
                posted_at=parse_iso(item.get("created")),
                salary_text=salary_range(item),
            )
        except (KeyError, TypeError, ValueError):
            return None
