"""Workday (myworkdayjobs.com) tenant boards.

Workday has no public board API: the careers site talks to its own CXS endpoints, a paged
search POST plus one detail GET per posting. Boards are large, so keywords are pushed into the
search (`searchText`) rather than filtered client-side, and detail fetches are capped per poll.
"""

from __future__ import annotations

import logging
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
logger = logging.getLogger(__name__)
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


def _interleave(groups: list[dict[str, Any]]) -> list[tuple[str, Any]]:
    """Round-robin over the per-keyword hit lists, deduped by path, so one broad keyword cannot
    consume the whole detail budget before the others get a turn."""
    seen: set[str] = set()
    out: list[tuple[str, Any]] = []
    iters = [iter(g.items()) for g in groups]
    while iters:
        for it in list(iters):
            try:
                path, item = next(it)
            except StopIteration:
                iters.remove(it)
                continue
            if path not in seen:
                seen.add(path)
                out.append((path, item))
    return out


def _req_id(info: dict[str, Any], item: Any, path: str) -> str:
    if info.get("jobReqId"):
        return str(info["jobReqId"])
    bullets = item.get("bulletFields") if isinstance(item, dict) else None
    if isinstance(bullets, list) and bullets and isinstance(bullets[0], str) and bullets[0]:
        return bullets[0]
    return path.rsplit("/", 1)[-1]


def _org_name(info: dict[str, Any]) -> str | None:
    org = info.get("hiringOrganization")
    if isinstance(org, dict) and isinstance(org.get("name"), str):
        return org["name"] or None
    return None


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
        per_term: list[dict[str, Any]] = []
        for term in keywords or [""]:
            found: dict[str, Any] = {}
            await self._search(http, f"{base}/jobs", term, found)
            per_term.append(found)

        out: list[Posting] = []
        skipped = 0
        for path, item in _interleave(per_term)[:MAX_DETAIL_FETCHES]:
            try:
                out.extend(
                    await self._posting(
                        http, (host_prefix, tenant, site), path, item, keywords=keywords
                    )
                )
            except (KeyError, TypeError, ValueError, AttributeError, SourceError) as exc:
                # One bad or vanished posting (a req closed between the search and the detail
                # fetch answers 404) never fails the board; the search-level errors above do.
                skipped += 1
                logger.info("workday %s/%s: skipped %s (%s)", tenant, site, path, exc)
        if skipped:
            logger.warning("workday %s/%s: skipped %d posting(s) this poll", tenant, site, skipped)
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
            if len(page) < PAGE_LIMIT or (isinstance(total, int) and offset >= total):
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
                # Req ids are unique within a tenant only, and jobs dedupe on
                # (user, source, external_id) without the board, so the tenant is part of the id.
                external_id=f"{tenant}:{_req_id(info, item, path)}",
                company=str(_org_name(info) or tenant),
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
