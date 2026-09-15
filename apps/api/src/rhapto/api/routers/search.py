"""One search box, every source at once.

Everything slow is bounded here: `live_search` caps each source and gives it
`LIVE_TIMEOUT_SECONDS`, so this endpoint answers in roughly that long no matter how many vendors
are having a bad day. Scoring is not part of the response -- the new rows are enqueued and the
client refetches `GET /jobs?ids=` until they have a fit ring.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session, get_settings_dep, get_state
from rhapto.api.routers.jobs import _outs
from rhapto.api.schemas import LiveSearchIn, LiveSearchOut, PerSourceOut
from rhapto.config import Settings
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.services.discovery.live import LIVE_TIMEOUT_SECONDS, LiveTarget, live_search
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.enqueue import Enqueuer
from rhapto.services.secrets import SecretsError, fernet_for
from rhapto.services.taxonomy import find_field

logger = logging.getLogger(__name__)

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]


async def build_targets(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, wanted: list[str] | None
) -> list[LiveTarget]:
    """Every enabled aggregator plus every watchlist board, narrowed by `wanted` if given."""
    fernet = None
    try:
        fernet = fernet_for(settings)
    except SecretsError:
        # No deployment secret: keyless sources still work, keyed ones report a missing key.
        logger.warning("no encryption secret configured; keyed sources will be skipped")
    targets: list[LiveTarget] = []
    for row in await profile_repo.list_aggregators(session, user_id):
        if not row.enabled or (wanted is not None and row.source not in wanted):
            continue
        info = SOURCES[row.source].info if row.source in SOURCES else None
        credentials: dict[str, str] = {}
        if info is not None and info.needs_key and fernet is not None:
            credentials = await creds_repo.get_credentials(session, fernet, user_id, row.source)
        targets.append(LiveTarget(source=row.source, credentials=credentials))
    for entry in await profile_repo.list_watchlist(session, user_id):
        if wanted is not None and entry.source not in wanted:
            continue
        targets.append(LiveTarget(source=entry.source, board=entry.board, company=entry.company))
    return targets


@router.post("/search", response_model=LiveSearchOut)
async def live(
    body: LiveSearchIn,
    request: Request,
    user_id: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    enqueuer: EnqueuerDep,
) -> LiveSearchOut:
    if body.field is not None and find_field(body.field) is None:
        raise HTTPException(status_code=422, detail=f"unknown taxonomy field {body.field!r}")
    spec = SearchSpec(
        keywords=(body.query.strip(),),
        location=(body.location or "").strip() or None,
        remote=body.remote,
        name=body.query.strip(),
        field=body.field,
        posted_within=body.posted_within,
    )
    targets = await build_targets(session, settings, user_id, body.sources)
    result = await live_search(
        session,
        user_id,
        http=get_state(request).discovery_http,
        spec=spec,
        targets=targets,
        timeout=LIVE_TIMEOUT_SECONDS,
    )
    await session.commit()
    # Captured before expire_all(): touching an attribute on an expired ORM object triggers a
    # synchronous lazy-load, which blows up on an AsyncSession outside of an awaited call.
    ids = [job.id for job in result.jobs]
    if result.new_job_ids:
        try:
            await enqueuer.enqueue(
                "score_jobs",
                user_id=str(user_id),
                job_ids=[str(i) for i in result.new_job_ids],
            )
        except Exception:  # the rows are committed; a queue outage must not fail the search
            logger.exception(
                "could not enqueue %s; %d new job(s) are saved but not scored",
                "score_jobs",
                len(result.new_job_ids),
            )
    session.expire_all()
    rows = await jobs_repo.list_jobs(session, user_id, ids=ids, sort="fit")
    return LiveSearchOut(
        jobs=await _outs(session, user_id, rows),
        per_source={
            name: PerSourceOut(found=o.found, new=o.new, error=o.error)
            for name, o in result.per_source.items()
        },
    )
