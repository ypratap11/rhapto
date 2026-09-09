from __future__ import annotations

import uuid

from pydantic import BaseModel


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
