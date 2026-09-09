from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db import models as db
from rhapto.db.repositories import profile as repo
from rhapto.engine.types import Profile, ProfileError
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.profile.loader import default_guardrails, dump_profile, load_profile, synthesize_bases


def block_row_to_model(row: db.ResumeBlock) -> Block:
    return Block(
        id=row.block_id,
        type=row.type,
        org=row.org,
        role=row.role,
        period=row.period,
        verified=row.verified,
        metric=row.metric,
        content=row.content,
        tags=list(row.tags),
        attribution=row.attribution,
        concurrent=row.concurrent,
        visibility=Visibility(exclude_when=list(row.exclude_when)) if row.exclude_when else None,
    )


def base_row_to_model(row: db.ResumeBase) -> ResumeBase:
    kwargs: dict[str, Any] = dict(
        id=row.base_id,
        name=row.name,
        block_ids=list(row.block_ids),
        style=dict(row.style_json),
    )
    if row.section_order:
        kwargs["section_order"] = list(row.section_order)
    return ResumeBase(**kwargs)


def track_row_to_model(row: db.Track) -> Track:
    return Track(
        id=row.track_id,
        name=row.name,
        description=row.description,
        keywords=list(row.keywords),
        resume_base=row.resume_base,
        min_fit=row.min_fit,
    )


def guardrail_row_to_model(row: db.Guardrail) -> GuardrailRule:
    return GuardrailRule(rule=row.rule, active=row.active, config=dict(row.config_json))


def watchlist_row_to_model(row: db.WatchlistEntry) -> WatchlistEntry:
    return WatchlistEntry(company=row.company, source=row.source, board=row.board)


async def load_profile_from_db(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    blocks = [block_row_to_model(r) for r in await repo.list_blocks(session, user_id)]
    if not blocks:
        raise ProfileError(
            "profile has no blocks; import one with `rhapto profile import` or add blocks in the UI"
        )
    tracks = [track_row_to_model(r) for r in await repo.list_tracks(session, user_id)]
    if not tracks:
        raise ProfileError("profile has no tracks")
    base_rows = await repo.list_bases(session, user_id)
    bases = (
        [base_row_to_model(r) for r in base_rows] if base_rows else synthesize_bases(tracks, blocks)
    )
    guardrail_rows = await repo.list_guardrails(session, user_id)
    guardrails = (
        [guardrail_row_to_model(r) for r in guardrail_rows]
        if guardrail_rows
        else default_guardrails()
    )
    return Profile(
        blocks=blocks,
        tracks=tracks,
        bases=bases,
        guardrails=guardrails,
        answers=await repo.get_answers(session, user_id),
        watchlist=[watchlist_row_to_model(r) for r in await repo.list_watchlist(session, user_id)],
    )


async def replace_profile_in_db(
    session: AsyncSession, user_id: uuid.UUID, profile: Profile
) -> None:
    await repo.delete_all_profile_rows(session, user_id)
    for block in profile.blocks:
        await repo.upsert_block(session, user_id, block)
    for base in profile.bases:
        await repo.upsert_base(session, user_id, base)
    for track in profile.tracks:
        await repo.upsert_track(session, user_id, track)
    for rule in profile.guardrails:
        await repo.upsert_guardrail(session, user_id, rule)
    await repo.set_answers(session, user_id, profile.answers)
    await repo.replace_watchlist(session, user_id, profile.watchlist)


async def import_profile_dir(session: AsyncSession, user_id: uuid.UUID, path: Path) -> Profile:
    profile = load_profile(path)
    await replace_profile_in_db(session, user_id, profile)
    return profile


async def export_profile_dir(session: AsyncSession, user_id: uuid.UUID, path: Path) -> Profile:
    profile = await load_profile_from_db(session, user_id)
    dump_profile(profile, path)
    return profile
