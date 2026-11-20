from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from rhapto.engine.select import keyword_matches
from rhapto.services.discovery.errors import Quota
from rhapto.services.discovery.http import parse_quota
from rhapto.services.discovery.offload import parse_off_loop
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import (
    SourceError,
    SourceInfo,
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
        live_only=True,
    )

    def __init__(self) -> None:
        # Set by fetch_search from the response headers; get_aggregator builds a fresh instance
        # per call, so this is per-request state.
        self.quota: Quota | None = None

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        """Exactly ONE /search-v2 request (10 jobs) per call: the free plan is 200 a month.

        Only the first keyword forms the query; the others feed the local keyword filter. No
        paging, no `cursor`, no `OR` syntax.
        """
        key = require_credentials(self.info, credentials)["rapidapi_key"]
        headers = {"x-rapidapi-key": key, "x-rapidapi-host": HOST}
        keyword = next((k.strip() for k in spec.keywords if k.strip()), "")
        phrase = f"{keyword} in {spec.location}" if spec.location else keyword
        url = f"https://{HOST}/search-v2?query={quote(phrase, safe='')}&country=us"
        response = await http.get_json_response(url, headers=headers)
        self.quota = parse_quota(response.headers)
        data = response.body
        inner = data.get("data") if isinstance(data, dict) else None
        jobs = inner.get("jobs") if isinstance(inner, dict) else None
        if not isinstance(jobs, list):
            raise SourceError("JSearch (Google Jobs): unexpected response shape")
        postings = await parse_off_loop(_parse_chunk, jobs, spec)
        return postings[:SEARCH_CAP]


_STOP_WORDS = frozenset(
    "a an and or the of for in at to with on job jobs role roles position positions".split()
)


def _significant_words(keyword: str) -> list[str]:
    words = (w for w in re.split(r"[\s\-/,&]+", keyword) if w)
    return [w for w in words if w.casefold() not in _STOP_WORDS]


def _matches_all_words(keywords: tuple[str, ...], *texts: str | None) -> bool:
    """A posting matches when every significant word of some keyword appears in it, in any order."""
    if not keywords:
        return True
    haystack = " ".join(t for t in texts if t)
    for keyword in keywords:
        words = _significant_words(keyword)
        if words:
            if all(keyword_matches(w, haystack) for w in words):
                return True
        elif keyword_matches(keyword, haystack):
            return True
    return False


def _to_posting(spec: SearchSpec, item: Any) -> Posting | None:
    if not isinstance(item, dict):
        return None
    try:
        title = str(item["job_title"])
        text = html_to_text(str(item.get("job_description") or "")) or title
        parts = [item.get("job_city"), item.get("job_state"), item.get("job_country")]
        location = ", ".join(str(p) for p in parts if p) or None
        if not _matches_all_words(spec.keywords, title, text, location):
            return None
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


def _parse_chunk(chunk: list[Any], spec: SearchSpec) -> list[Posting]:
    out: list[Posting] = []
    for item in chunk:
        posting = _to_posting(spec, item)
        if posting is not None:
            out.append(posting)
    return out
