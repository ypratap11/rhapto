from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp


@register
class LeverSource:
    info: ClassVar[SourceInfo] = SourceInfo("lever", "board", "Lever", True)

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]:
        data = await http.get_json(f"https://api.lever.co/v0/postings/{board}?mode=json")
        out: list[Posting] = []
        for job in data if isinstance(data, list) else []:
            try:
                title = str(job["text"])
                parts = [
                    str(
                        job.get("descriptionPlain")
                        or html_to_text(str(job.get("description") or ""))
                    )
                ]
                for section in job.get("lists") or []:
                    parts.append(
                        f"{section.get('text', '')}\n{html_to_text(str(section.get('content') or ''))}"
                    )
                parts.append(str(job.get("additionalPlain") or ""))
                text = "\n\n".join(p.strip() for p in parts if p and p.strip())
                if not matches_keywords(keywords, title, text):
                    continue
                categories = job.get("categories") or {}
                created = job.get("createdAt")
                out.append(
                    Posting(
                        external_id=str(job["id"]),
                        company=str(board),
                        title=title,
                        location=str(categories.get("location"))
                        if categories.get("location")
                        else None,
                        url=str(job["hostedUrl"]),
                        jd_text=text or title,
                        posted_at=datetime.fromtimestamp(int(created) / 1000, tz=UTC)
                        if isinstance(created, (int, float))
                        else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
