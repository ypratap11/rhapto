from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp


@register
class AshbySource:
    info: ClassVar[SourceInfo] = SourceInfo("ashby", "board", "Ashby", True)

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]:
        data = await http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        out: list[Posting] = []
        for job in data.get("jobs", []) if isinstance(data, dict) else []:
            try:
                if job.get("isListed") is False:
                    continue
                title = str(job["title"])
                text = str(job.get("descriptionPlain") or "").strip() or html_to_text(
                    str(job.get("descriptionHtml") or "")
                )
                if not matches_keywords(keywords, title, text):
                    continue
                out.append(
                    Posting(
                        external_id=str(job["id"]),
                        company=str(board),
                        title=title,
                        location=str(job.get("location")) if job.get("location") else None,
                        url=str(job["jobUrl"]),
                        jd_text=text or title,
                        posted_at=parse_iso(job.get("publishedAt")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
