from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from rhapto.services.failure_categories import FailureCategory


class AdminSessionOut(BaseModel):
    ok: bool


class AlertOut(BaseModel):
    id: str
    tone: Literal["warn", "info"]
    title: str
    detail: str


class OverviewOut(BaseModel):
    signups_total: int
    signups_today: int
    free_spend_month_usd: str
    budget_usd: float | None
    accounts: int
    account_cap: int
    want_more_users: int
    failed_7d: int
    alerts: list[AlertOut]


class UserSearchIn(BaseModel):
    q: str = Field("", max_length=320)
    offset: int = Field(0, ge=0, le=10000)


class UserRowOut(BaseModel):
    id: uuid.UUID
    email: str
    runs_used: int
    runs_limit: int | None
    failed_count: int
    last_seen_at: datetime
    blocked: bool


class UserSearchOut(BaseModel):
    users: list[UserRowOut]
    next_offset: int | None


class FailureOut(BaseModel):
    when: datetime
    type: str
    category: FailureCategory
    label: str


class ActionOut(BaseModel):
    when: datetime
    actor_email: str
    action: str
    before: dict[str, Any]
    after: dict[str, Any]


class UserDetailOut(BaseModel):
    id: uuid.UUID
    email: str
    joined_at: datetime
    runs_used: int
    runs_limit: int | None
    free_spend_usd: str
    asked_for_more: bool
    blocked: bool
    failures: list[FailureOut]
    suggested_reset_runs: int | None
    history: list[ActionOut]
