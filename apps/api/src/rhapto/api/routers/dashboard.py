"""Everything the Dashboard shows, in one call.

Five reads, no N+1: `tests/api/test_dashboard_api.py` asserts the whole request stays inside
eight SELECTs, so this endpoint cannot quietly become a loop.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.schemas import (
    ChecklistOut,
    DashboardOut,
    FollowUpOut,
    JobRef,
    SavedSearchCountOut,
)
from rhapto.db.repositories import dashboard as repo
from rhapto.db.repositories import searches as searches_repo

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(user_id: UserDep, session: SessionDep) -> DashboardOut:
    checklist = await repo.checklist(session, user_id)
    counts = await searches_repo.new_counts(session, user_id)
    searches = await searches_repo.list_searches(session, user_id)
    followups = await repo.due_followups(session, user_id)
    return DashboardOut(
        new_fit_count=await repo.new_fit_count(session, user_id),
        needs_review_count=await repo.needs_review_count(session, user_id),
        checklist=ChecklistOut(
            resume_template=checklist.resume_template,
            contact_answers=checklist.contact_answers,
            tracks=checklist.tracks,
            blocks_verified=checklist.blocks_verified,
            guardrails=checklist.guardrails,
            location_preferences=checklist.location_preferences,
            verified_blocks=checklist.verified_blocks,
            total_blocks=checklist.total_blocks,
        ),
        saved_searches=[
            SavedSearchCountOut(id=s.id, name=s.name, new_count=counts.get(s.id, 0))
            for s in searches
        ],
        due_followups=[
            FollowUpOut(
                application_id=application.id,
                job=JobRef(id=job.id, company=job.company, title=job.title),
                status=application.status,
                follow_up_at=follow_up,
            )
            for application, job in followups
            # `due_followups` only returns rows with a date, but mypy cannot see that.
            if (follow_up := application.follow_up_at) is not None
        ],
    )
