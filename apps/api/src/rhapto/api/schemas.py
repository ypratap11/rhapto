from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator

from rhapto.models.jd_extract import JDExtract


class HealthOut(BaseModel):
    status: str


class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID


class ImportOut(BaseModel):
    blocks: int
    tracks: int
    bases: int
    guardrails: int


class JobCreate(BaseModel):
    jd_text: str | None = None
    url: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> JobCreate:
        if bool(self.jd_text) == bool(self.url):
            raise ValueError("provide exactly one of jd_text or url")
        if self.jd_text is not None and len(self.jd_text.strip()) < 50:
            raise ValueError("jd_text must be at least 50 characters")
        return self


class PackageSummary(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    created_at: datetime


class JobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str | None
    title: str | None
    location: str | None
    url: str | None
    jd_text: str
    extracted: JDExtract | None
    discovered_at: datetime
    latest_package: PackageSummary | None
    application_status: str | None
