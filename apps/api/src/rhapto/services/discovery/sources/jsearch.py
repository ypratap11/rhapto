from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

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

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

HOST = "jsearch.p.rapidapi.com"


@register
class JSearchSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "jsearch",
        "aggregator",
        "JSearch (Google Jobs)",
        False,
        needs_key=True,
        fields=("rapidapi_key",),
    )

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        key = require_credentials(self.info, credentials)["rapidapi_key"]
        headers = {"x-rapidapi-key": key, "x-rapidapi-host": HOST}
        remote_only = "true" if spec.remote == "only" else "false"
        out: list[Posting] = []
        for keyword in spec.keywords or ("",):
            phrase = f"{keyword} in {spec.location}" if spec.location else keyword
            url = (
                f"https://{HOST}/search?query={quote(phrase, safe='')}"
                f"&page=1&num_pages=2&remote_jobs_only={remote_only}"
            )
            data = await http.get_json(url, headers=headers)
            if not isinstance(data, dict):
                raise SourceError("JSearch (Google Jobs): unexpected response shape")
            rows = data.get("data")
            for item in rows if isinstance(rows, list) else []:
                posting = self._to_posting(spec, item)
                if posting is not None:
                    out.append(posting)
                if len(out) >= SEARCH_CAP:
                    return out
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["job_title"])
            text = html_to_text(str(item.get("job_description") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            parts = [item.get("job_city"), item.get("job_state"), item.get("job_country")]
            location = ", ".join(str(p) for p in parts if p) or None
            is_remote = bool(item.get("job_is_remote"))
            if not remote_matches(spec, location, is_remote):
                return None
            low, high = item.get("job_min_salary"), item.get("job_max_salary")
            salary = f"{int(low)}-{int(high)}" if low and high else None
            return Posting(
                external_id=str(item["job_id"]),
                company=str(item.get("employer_name") or "Unknown"),
                title=title,
                location=location,
                url=str(item["job_apply_link"]),
                jd_text=text,
                posted_at=parse_iso(item.get("job_posted_at_datetime_utc")),
                salary_text=salary,
            )
        except (KeyError, TypeError, ValueError):
            return None
