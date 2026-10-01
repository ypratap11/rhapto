"""Tester feedback intake. One route, insert-only: there is no GET, list, PATCH or DELETE for
feedback over HTTP, and nothing under `rhapto.api` imports the cross-user read. The owner reads it
with `rhapto feedback report` on the server.

Nothing here logs the body, and the 422 handler already drops `input` from validation errors.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import rhapto
from rhapto.api.deps import current_user, get_session, get_settings_dep
from rhapto.api.errors import problem
from rhapto.api.schemas import FeedbackIn, FeedbackOut
from rhapto.config import Settings
from rhapto.db.repositories import feedback as feedback_repo
from rhapto.services.feedback import SCHEMA_VERSION

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]

FEEDBACK_DAILY_LIMIT = 50


def _app_version(settings: Settings) -> str:
    build = settings.rhapto_build_id
    return f"{rhapto.__version__}+{build}" if build else rhapto.__version__


@router.post("/feedback", status_code=201, response_model=FeedbackOut)
async def create_feedback(
    body: FeedbackIn, user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> FeedbackOut | JSONResponse:
    since = datetime.now(UTC) - timedelta(hours=24)
    if await feedback_repo.count_since(session, user_id, since) >= FEEDBACK_DAILY_LIMIT:
        response = problem(
            429,
            "Too Many Requests",
            "too much feedback in the last 24 hours; thank you, please try again later",
            code="feedback_rate_limited",
        )
        response.headers["Retry-After"] = "3600"
        return response

    job_id: uuid.UUID | None = None
    package_id: uuid.UUID | None = None
    if body.form == "quick":
        job_id, package_id = await feedback_repo.owned_context(
            session, user_id, body.job_id, body.package_id
        )
    row = await feedback_repo.insert(
        session,
        user_id=user_id,
        form=body.form,
        page_area=body.page_area,
        schema_version=SCHEMA_VERSION,
        answers=body.answers.model_dump(mode="json", exclude_none=True),
        app_version=_app_version(settings),
        job_id=job_id,
        package_id=package_id,
    )
    await session.commit()
    return FeedbackOut(id=row.id, created_at=row.created_at)
