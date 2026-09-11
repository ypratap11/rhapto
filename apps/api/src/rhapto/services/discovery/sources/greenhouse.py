from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


@register
class GreenhouseSource:
    info: ClassVar[SourceInfo] = SourceInfo("greenhouse", "board", "Greenhouse", True)

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]:
        data = await http.get_json(
            f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
        )
        out: list[Posting] = []
        for job in data.get("jobs", []) if isinstance(data, dict) else []:
            try:
                title = str(job["title"])
                text = html_to_text(str(job.get("content") or ""))
                if not matches_keywords(keywords, title, text):
                    continue
                location = job.get("location") or {}
                out.append(
                    Posting(
                        external_id=str(job["id"]),
                        company=str(job.get("company_name") or board),
                        title=title,
                        location=str(location.get("name"))
                        if isinstance(location, dict) and location.get("name")
                        else None,
                        url=str(job["absolute_url"]),
                        jd_text=text or title,
                        posted_at=parse_iso(job.get("first_published"))
                        or parse_iso(job.get("updated_at")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # one bad posting never fails the board
        return out
