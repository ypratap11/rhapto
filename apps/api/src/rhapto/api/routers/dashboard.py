"""Everything the Dashboard shows, in one call.

Five reads, no N+1: `tests/api/test_dashboard_api.py` asserts the whole request stays inside
eight SELECTs, so this endpoint cannot quietly become a loop.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session, get_storage
from rhapto.api.schemas import (
    ChecklistOut,
    DashboardOut,
    FollowUpOut,
    JobRef,
    SavedSearchCountOut,
)
from rhapto.db.repositories import dashboard as repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories.discovery import NEVER_RUN, search_run_stats
from rhapto.services.storage import PackageStorage

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(user_id: UserDep, session: SessionDep, storage: StorageDep) -> DashboardOut:
    checklist = await repo.checklist(session, user_id)
    # The repository counts `resume_documents` rows, which is all SQL can see. A row whose file has
    # vanished from the volume is not a usable template: `documents.load_source` already treats that
    # as "no document" and tune mode refuses to run. Reporting the step complete anyway is how this
    # deployment told its owner he was set up for three days after his upload was gone, then failed
    # at the moment he pressed Tailor. One stat() call, on the same path `read_document` uses.
    resume_template = checklist.resume_template and await asyncio.to_thread(
        storage.has_document, user_id
    )
    counts = await searches_repo.new_counts(session, user_id)
    searches = await searches_repo.list_searches(session, user_id)
    run_stats = await search_run_stats(session, user_id)
    followups = await repo.due_followups(session, user_id)
    return DashboardOut(
        new_fit_count=await repo.new_fit_count(session, user_id),
        needs_review_count=await repo.needs_review_count(session, user_id),
        checklist=ChecklistOut(
            resume_template=resume_template,
            contact_answers=checklist.contact_answers,
            tracks=checklist.tracks,
            blocks_verified=checklist.blocks_verified,
            guardrails=checklist.guardrails,
            location_preferences=checklist.location_preferences,
            verified_blocks=checklist.verified_blocks,
            total_blocks=checklist.total_blocks,
        ),
        saved_searches=[
            SavedSearchCountOut(
                id=s.id,
                name=s.name,
                new_count=counts.get(s.id, 0),
                # The rail's badge is hidden when `new_count` is 0, so without this a search that
                # has never found anything renders exactly like one the user has already read.
                ever_found=run_stats.get(s.id, NEVER_RUN).ever_found,
            )
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
