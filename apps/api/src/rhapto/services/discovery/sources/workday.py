"""Workday (myworkdayjobs.com) tenant boards.

Workday has no public board API: the careers site talks to its own CXS endpoints, a paged
search POST plus one detail GET per posting. Boards are large, so keywords are pushed into the
search (`searchText`) rather than filtered client-side, and detail fetches are capped per poll.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, ClassVar

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

#: Workday silently clamps `limit` to 20, so paging by anything larger just loses postings.
PAGE_LIMIT = 20
#: Per keyword; a board with more matches than this is a sign the keyword is too broad.
MAX_POSTINGS_PER_SEARCH = 200
#: One detail GET per posting is the expensive half of a poll; postings past the cap are
#: skipped (not an error) and picked up by a later poll as the board turns over.
MAX_DETAIL_FETCHES = 60

_PART = re.compile(r"^[A-Za-z0-9._-]+$")
_BOARD_HELP = "workday board must look like <company>.wd5/<SiteName>"


def parse_board(board: str | None) -> tuple[str, str, str]:
    """`nvidia.wd5/NVIDIAExternalCareerSite` -> host prefix, tenant, site.

    The tenant is the first dotted label of the host prefix: the CXS paths use it, while the
    hostname needs the data-centre suffix (`wd1`, `wd5`, `wd103`...) that the careers URL shows.
    """
    parts = (board or "").split("/")
    if len(parts) != 2:
        raise SourceError(_BOARD_HELP)
    host_prefix, site = parts
    if not _PART.match(host_prefix) or not _PART.match(site):
        raise SourceError(_BOARD_HELP)
    tenant = host_prefix.split(".")[0]
    if not tenant:
        raise SourceError(_BOARD_HELP)
    return host_prefix, tenant, site


def parse_start_date(value: Any) -> datetime | None:
    """`startDate` is a bare `YYYY-MM-DD`; postings are dated, not timestamped, so UTC midnight."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


@register
class WorkdaySource:
    info: ClassVar[SourceInfo] = SourceInfo("workday", "board", "Workday", True)

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]:
        host_prefix, tenant, site = parse_board(board)
        base = f"https://{host_prefix}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
        # Insertion order keeps the first keyword's hits first; the dict dedupes the overlap
        # between keywords so a posting is only ever detail-fetched once per poll.
        summaries: dict[str, Any] = {}
        for term in keywords or [""]:
            await self._search(http, f"{base}/jobs", term, summaries)

        out: list[Posting] = []
        for path, item in list(summaries.items())[:MAX_DETAIL_FETCHES]:
            try:
                out.extend(
                    await self._posting(
                        http, (host_prefix, tenant, site), path, item, keywords=keywords
                    )
                )
            except (KeyError, TypeError, ValueError, AttributeError, SourceError):
                # One bad or vanished posting (a req closed between the search and the detail
                # fetch answers 404) never fails the board; the search-level errors above do.
                continue
        return out

    async def _search(
        self, http: DiscoveryHttp, url: str, term: str, summaries: dict[str, Any]
    ) -> None:
        offset = 0
        seen = 0
        while seen < MAX_POSTINGS_PER_SEARCH:
            data = await http.post_json(
                url,
                {"appliedFacets": {}, "limit": PAGE_LIMIT, "offset": offset, "searchText": term},
            )
            if not isinstance(data, dict):
                return
            page = data.get("jobPostings")
            if not isinstance(page, list) or not page:
                return
            for item in page:
                path = item.get("externalPath") if isinstance(item, dict) else None
                if isinstance(path, str) and path.startswith("/"):
                    summaries.setdefault(path, item)
            seen += len(page)
            offset += PAGE_LIMIT
            total = data.get("total")
            if len(page) < PAGE_LIMIT or not isinstance(total, int) or offset >= total:
                return

    async def _posting(
        self,
        http: DiscoveryHttp,
        parsed: tuple[str, str, str],
        path: str,
        item: Any,
        *,
        keywords: list[str],
    ) -> list[Posting]:
        """At most one posting; a list so a filtered-out or malformed job is simply empty."""
        host_prefix, tenant, site = parsed
        base = f"https://{host_prefix}.myworkdayjobs.com/wday/cxs/{tenant}/{site}"
        detail = await http.get_json(f"{base}{path}")
        if not isinstance(detail, dict):
            raise TypeError("detail response is not an object")
        info = detail.get("jobPostingInfo") or {}
        if not isinstance(info, dict):
            raise TypeError("jobPostingInfo is not an object")
        title = str(info.get("title") or item.get("title") or "")
        text = html_to_text(str(info.get("jobDescription") or ""))
        if not title or not matches_keywords(keywords, title, text):
            return []
        return [
            Posting(
                external_id=str(info.get("jobReqId") or path.rsplit("/", 1)[-1]),
                # Workday postings carry no company name; the tenant stands in until the
                # poller overrides it with the watchlist row's company.
                company=tenant,
                title=title,
                location=str(info.get("location") or item.get("locationsText") or "") or None,
                url=str(
                    info.get("externalUrl")
                    or f"https://{host_prefix}.myworkdayjobs.com/{site}{path}"
                ),
                jd_text=text or title,
                posted_at=parse_start_date(info.get("startDate")),
            )
        ]
