from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Answers, Guardrail, ResumeBase, ResumeBlock, Track, WatchlistEntry
from rhapto.models.profile.bases import ResumeBase as ResumeBaseModel
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track as TrackModel
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistEntryModel


async def list_blocks(session: AsyncSession, user_id: uuid.UUID) -> list[ResumeBlock]:
    rows = await session.scalars(
        select(ResumeBlock).where(ResumeBlock.user_id == user_id).order_by(ResumeBlock.created_at)
    )
    return list(rows)


async def get_block(session: AsyncSession, user_id: uuid.UUID, block_id: str) -> ResumeBlock | None:
    result: ResumeBlock | None = await session.scalar(
        select(ResumeBlock).where(ResumeBlock.user_id == user_id, ResumeBlock.block_id == block_id)
    )
    return result


async def upsert_block(session: AsyncSession, user_id: uuid.UUID, data: Block) -> ResumeBlock:
    row = await get_block(session, user_id, data.id)
    if row is None:
        row = ResumeBlock(user_id=user_id, block_id=data.id, type=data.type, content=data.content)
        session.add(row)
    row.type = data.type
    row.org = data.org
    row.role = data.role
    row.period = data.period
    row.verified = data.verified
    row.metric = data.metric
    row.content = data.content
    row.tags = list(data.tags)
    row.attribution = data.attribution
    row.concurrent = data.concurrent
    row.exclude_when = list(data.visibility.exclude_when) if data.visibility else []
    await session.flush()
    return row


async def delete_block(session: AsyncSession, user_id: uuid.UUID, block_id: str) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(ResumeBlock).where(
                ResumeBlock.user_id == user_id, ResumeBlock.block_id == block_id
            )
        ),
    )
    return bool(result.rowcount)


async def list_bases(session: AsyncSession, user_id: uuid.UUID) -> list[ResumeBase]:
    return list(
        await session.scalars(
            select(ResumeBase).where(ResumeBase.user_id == user_id).order_by(ResumeBase.created_at)
        )
    )


async def get_base(session: AsyncSession, user_id: uuid.UUID, base_id: str) -> ResumeBase | None:
    result: ResumeBase | None = await session.scalar(
        select(ResumeBase).where(ResumeBase.user_id == user_id, ResumeBase.base_id == base_id)
    )
    return result


async def upsert_base(
    session: AsyncSession, user_id: uuid.UUID, data: ResumeBaseModel
) -> ResumeBase:
    row = await get_base(session, user_id, data.id)
    if row is None:
        row = ResumeBase(user_id=user_id, base_id=data.id, name=data.name)
        session.add(row)
    row.name = data.name
    row.block_ids = list(data.block_ids)
    row.section_order = list(data.section_order)
    row.style_json = dict(data.style)
    await session.flush()
    return row


async def delete_base(session: AsyncSession, user_id: uuid.UUID, base_id: str) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(ResumeBase).where(ResumeBase.user_id == user_id, ResumeBase.base_id == base_id)
        ),
    )
    return bool(result.rowcount)


async def list_tracks(session: AsyncSession, user_id: uuid.UUID) -> list[Track]:
    return list(
        await session.scalars(
            select(Track).where(Track.user_id == user_id).order_by(Track.created_at)
        )
    )


async def get_track(session: AsyncSession, user_id: uuid.UUID, track_id: str) -> Track | None:
    result: Track | None = await session.scalar(
        select(Track).where(Track.user_id == user_id, Track.track_id == track_id)
    )
    return result


async def upsert_track(session: AsyncSession, user_id: uuid.UUID, data: TrackModel) -> Track:
    row = await get_track(session, user_id, data.id)
    if row is None:
        row = Track(user_id=user_id, track_id=data.id, name=data.name, resume_base=data.resume_base)
        session.add(row)
    row.name = data.name
    row.description = data.description
    row.keywords = list(data.keywords)
    row.resume_base = data.resume_base
    row.min_fit = data.min_fit
    await session.flush()
    return row


async def delete_track(session: AsyncSession, user_id: uuid.UUID, track_id: str) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(Track).where(Track.user_id == user_id, Track.track_id == track_id)
        ),
    )
    return bool(result.rowcount)


async def list_guardrails(session: AsyncSession, user_id: uuid.UUID) -> list[Guardrail]:
    return list(
        await session.scalars(
            select(Guardrail).where(Guardrail.user_id == user_id).order_by(Guardrail.created_at)
        )
    )


async def get_guardrail(session: AsyncSession, user_id: uuid.UUID, rule: str) -> Guardrail | None:
    result: Guardrail | None = await session.scalar(
        select(Guardrail).where(Guardrail.user_id == user_id, Guardrail.rule == rule)
    )
    return result


async def upsert_guardrail(
    session: AsyncSession, user_id: uuid.UUID, data: GuardrailRule
) -> Guardrail:
    row = await get_guardrail(session, user_id, data.rule)
    if row is None:
        row = Guardrail(user_id=user_id, rule=data.rule)
        session.add(row)
    row.active = data.active
    row.config_json = dict(data.config)
    await session.flush()
    return row


async def delete_guardrail(session: AsyncSession, user_id: uuid.UUID, rule: str) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(Guardrail).where(Guardrail.user_id == user_id, Guardrail.rule == rule)
        ),
    )
    return bool(result.rowcount)


async def get_answers(session: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    return dict(row.answers_json) if row else {}


async def set_answers(session: AsyncSession, user_id: uuid.UUID, answers: dict[str, str]) -> None:
    row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    if row is None:
        row = Answers(user_id=user_id, answers_json={})
        session.add(row)
    row.answers_json = dict(answers)
    await session.flush()


async def list_watchlist(session: AsyncSession, user_id: uuid.UUID) -> list[WatchlistEntry]:
    return list(
        await session.scalars(
            select(WatchlistEntry)
            .where(WatchlistEntry.user_id == user_id)
            .order_by(WatchlistEntry.created_at)
        )
    )


async def replace_watchlist(
    session: AsyncSession, user_id: uuid.UUID, entries: list[WatchlistEntryModel]
) -> None:
    await session.execute(delete(WatchlistEntry).where(WatchlistEntry.user_id == user_id))
    for entry in entries:
        session.add(
            WatchlistEntry(
                user_id=user_id, company=entry.company, source=entry.source, board=entry.board
            )
        )
    await session.flush()


async def delete_all_profile_rows(session: AsyncSession, user_id: uuid.UUID) -> None:
    for model in (ResumeBlock, ResumeBase, Track, Guardrail, Answers, WatchlistEntry):
        await session.execute(delete(model).where(model.user_id == user_id))
    await session.flush()
