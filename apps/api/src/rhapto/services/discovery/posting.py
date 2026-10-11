from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator


class Posting(BaseModel):
    external_id: str
    company: str
    title: str
    location: str | None = None
    url: str
    jd_text: str
    posted_at: datetime | None = None
    #: What the source said about pay, verbatim. None when it said nothing; never computed.
    salary_text: str | None = None

    @field_validator("external_id", "company", "title", "jd_text")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("posted_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("posted_at must be timezone-aware")
        return value

    @field_validator("url")
    @classmethod
    def _http_url(cls, value: str) -> str:
        v = value.strip()
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("url must not contain control characters")
        parts = urlsplit(v)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError("url must be an absolute http(s) URL")
        return v
