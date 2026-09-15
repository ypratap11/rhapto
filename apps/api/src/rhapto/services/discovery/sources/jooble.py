from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

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

MAX_PAGES = 3


@register
class JoobleSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "jooble", "aggregator", "Jooble", False, needs_key=True, fields=("api_key",)
    )

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        # Jooble authenticates by putting the key in the path, so every error raised from here
        # is rewritten: the raw message would otherwise carry the key into a run row and the UI.
        key = require_credentials(self.info, credentials)["api_key"]
        out: list[Posting] = []
        for keyword in spec.keywords or ("",):
            for page in range(1, MAX_PAGES + 1):
                if len(out) >= SEARCH_CAP:
                    return out
                body: dict[str, Any] = {"keywords": keyword, "page": page}
                if spec.location:
                    body["location"] = spec.location
                try:
                    data = await http.post_json(f"https://jooble.org/api/{key}", body)
                except SourceError as exc:
                    raise SourceError(
                        f"Jooble: check the API key ({str(exc).replace(key, '…')})"
                    ) from None
                if not isinstance(data, dict):
                    raise SourceError("Jooble: unexpected response shape")
                jobs = data.get("jobs")
                items = jobs if isinstance(jobs, list) else []
                for item in items:
                    posting = self._to_posting(spec, item)
                    if posting is not None:
                        out.append(posting)
                    if len(out) >= SEARCH_CAP:
                        return out
                if not items:
                    break
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["title"])
            text = html_to_text(str(item.get("snippet") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            location = str(item.get("location") or "") or None
            if not remote_matches(spec, location, None):
                return None
            return Posting(
                external_id=str(item["id"]),
                company=str(item.get("company") or "Unknown"),
                title=title,
                location=location,
                url=str(item["link"]),
                jd_text=text,
                posted_at=parse_iso(item.get("updated")),
                salary_text=str(item.get("salary") or "").strip() or None,
            )
        except (KeyError, TypeError, ValueError):
            return None
