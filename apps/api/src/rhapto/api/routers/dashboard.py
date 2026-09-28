"""Everything the Dashboard shows, in one call.

Ten reads, no N+1. `tests/api/test_dashboard_api.py` caps the request at ten SELECTs
(`MAX_DASHBOARD_SELECTS`, itemised there) and — the part that matters — asserts the count is the
SAME with one saved search as with five. The cap alone stops being a guard the moment someone
raises the constant; the invariance test is what actually forbids a per-row loop.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session, get_settings_dep, get_storage
from rhapto.api.schemas import (
    ChecklistOut,
    DashboardOut,
    FollowUpOut,
    JobRef,
    SavedSearchCountOut,
)
from rhapto.config import Settings
from rhapto.db.repositories import dashboard as repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories.discovery import NEVER_RUN, search_run_stats
from rhapto.services.discovery.sources import aggregator_sources
from rhapto.services.discovery.sources.status import usable_source_ids
from rhapto.services.storage import PackageStorage
from rhapto.services.trial import llm_setup_status

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[PackageStorage, Depends(get_storage)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(
    user_id: UserDep, session: SessionDep, storage: StorageDep, settings: SettingsDep
) -> DashboardOut:
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
    # `runs_used` comes from the checklist composite, so this does not add a statement of its own.
    llm = await llm_setup_status(session, settings, user_id, runs_used=checklist.trial_runs_used)
    # The same pure function `GET /settings/sources` uses for `configured`, so the checklist and the
    # Settings page cannot disagree about what "set up" means. Deliberately NOT `runnable`: that adds
    # pause, and a transient pause must not flip a completed setup step to "not done"
    # (architecture §12.1 point 3).
    sources = await repo.source_setup(session, user_id)
    usable = usable_source_ids(
        sources, {s for s, row in sources.items() if row.key_set}, aggregator_sources()
    )
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
            llm_key=llm.llm_key,
            llm_key_source=llm.llm_key_source,
            trial_runs_left=llm.trial_runs_left,
            job_sources=len(usable) > 0,
            usable_sources=len(usable),
            saved_searches=checklist.active_searches > 0,
            active_searches=checklist.active_searches,
            jobs_found=checklist.jobs_found,
            dateless_blocks=checklist.dateless_blocks,
        ),
        saved_searches=[
            SavedSearchCountOut(
                id=s.id,
                name=s.name,
                new_count=counts.get(s.id, 0),
                # The rail's badge is hidden when `new_count` is 0, so without these a search that
                # has never found anything renders exactly like one the user has already read --
                # and `runs` is what separates that from one created a moment ago.
                ever_found=run_stats.get(s.id, NEVER_RUN).ever_found,
                runs=run_stats.get(s.id, NEVER_RUN).runs,
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
