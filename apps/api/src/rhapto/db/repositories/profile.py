from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import (
    Aggregator,
    Answers,
    Guardrail,
    ResumeBase,
    ResumeBlock,
    Track,
    WatchlistEntry,
)
from rhapto.models.profile.bases import ResumeBase as ResumeBaseModel
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track as TrackModel
from rhapto.models.profile.watchlist import AggregatorEntry
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistEntryModel


async def _next_position(session: AsyncSession, model: type[Any], user_id: uuid.UUID) -> int:
    """One past the current max `position` for this user/table; -1 when there are no rows yet."""
    current_max = await session.scalar(
        select(func.coalesce(func.max(model.position), -1)).where(model.user_id == user_id)
    )
    return int(current_max) + 1


async def list_blocks(session: AsyncSession, user_id: uuid.UUID) -> list[ResumeBlock]:
    rows = await session.scalars(
        select(ResumeBlock)
        .where(ResumeBlock.user_id == user_id)
        .order_by(ResumeBlock.position, ResumeBlock.created_at, ResumeBlock.block_id)
    )
    return list(rows)


async def get_block(session: AsyncSession, user_id: uuid.UUID, block_id: str) -> ResumeBlock | None:
    result: ResumeBlock | None = await session.scalar(
        select(ResumeBlock).where(ResumeBlock.user_id == user_id, ResumeBlock.block_id == block_id)
    )
    return result


async def upsert_block(
    session: AsyncSession, user_id: uuid.UUID, data: Block, position: int | None = None
) -> ResumeBlock:
    row = await get_block(session, user_id, data.id)
    if row is None:
        resolved_position = (
            position
            if position is not None
            else await _next_position(session, ResumeBlock, user_id)
        )
        row = ResumeBlock(
            user_id=user_id,
            block_id=data.id,
            type=data.type,
            content=data.content,
            position=resolved_position,
        )
        session.add(row)
    elif position is not None:
        row.position = position
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
            select(ResumeBase)
            .where(ResumeBase.user_id == user_id)
            .order_by(ResumeBase.position, ResumeBase.created_at, ResumeBase.base_id)
        )
    )


async def get_base(session: AsyncSession, user_id: uuid.UUID, base_id: str) -> ResumeBase | None:
    result: ResumeBase | None = await session.scalar(
        select(ResumeBase).where(ResumeBase.user_id == user_id, ResumeBase.base_id == base_id)
    )
    return result


async def upsert_base(
    session: AsyncSession, user_id: uuid.UUID, data: ResumeBaseModel, position: int | None = None
) -> ResumeBase:
    row = await get_base(session, user_id, data.id)
    if row is None:
        resolved_position = (
            position if position is not None else await _next_position(session, ResumeBase, user_id)
        )
        row = ResumeBase(
            user_id=user_id, base_id=data.id, name=data.name, position=resolved_position
        )
        session.add(row)
    elif position is not None:
        row.position = position
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
            select(Track)
            .where(Track.user_id == user_id)
            .order_by(Track.position, Track.created_at, Track.track_id)
        )
    )


async def get_track(session: AsyncSession, user_id: uuid.UUID, track_id: str) -> Track | None:
    result: Track | None = await session.scalar(
        select(Track).where(Track.user_id == user_id, Track.track_id == track_id)
    )
    return result


async def upsert_track(
    session: AsyncSession, user_id: uuid.UUID, data: TrackModel, position: int | None = None
) -> Track:
    row = await get_track(session, user_id, data.id)
    if row is None:
        resolved_position = (
            position if position is not None else await _next_position(session, Track, user_id)
        )
        row = Track(
            user_id=user_id,
            track_id=data.id,
            name=data.name,
            resume_base=data.resume_base,
            position=resolved_position,
        )
        session.add(row)
    elif position is not None:
        row.position = position
    embedding_stale = (
        row.name != data.name
        or row.description != data.description
        or list(row.keywords or []) != list(data.keywords)
    )
    row.name = data.name
    row.description = data.description
    row.keywords = list(data.keywords)
    row.resume_base = data.resume_base
    row.min_fit = data.min_fit
    row.field = data.field
    row.role = data.role
    if embedding_stale:
        row.embedding = None
    row.updated_at = datetime.now(UTC)
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
            select(Guardrail)
            .where(Guardrail.user_id == user_id)
            .order_by(Guardrail.position, Guardrail.created_at, Guardrail.rule)
        )
    )


async def get_guardrail(session: AsyncSession, user_id: uuid.UUID, rule: str) -> Guardrail | None:
    result: Guardrail | None = await session.scalar(
        select(Guardrail).where(Guardrail.user_id == user_id, Guardrail.rule == rule)
    )
    return result


async def upsert_guardrail(
    session: AsyncSession, user_id: uuid.UUID, data: GuardrailRule, position: int | None = None
) -> Guardrail:
    row = await get_guardrail(session, user_id, data.rule)
    if row is None:
        resolved_position = (
            position if position is not None else await _next_position(session, Guardrail, user_id)
        )
        row = Guardrail(user_id=user_id, rule=data.rule, position=resolved_position)
        session.add(row)
    elif position is not None:
        row.position = position
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
    now = datetime.now(UTC)
    for entry in entries:
        session.add(
            WatchlistEntry(
                user_id=user_id,
                company=entry.company,
                source=entry.source,
                board=entry.board,
                keywords=list(entry.keywords),
                updated_at=now,
            )
        )
    await session.flush()


async def list_aggregators(session: AsyncSession, user_id: uuid.UUID) -> list[Aggregator]:
    return list(
        await session.scalars(
            select(Aggregator).where(Aggregator.user_id == user_id).order_by(Aggregator.created_at)
        )
    )


async def replace_aggregators(
    session: AsyncSession, user_id: uuid.UUID, entries: list[AggregatorEntry]
) -> None:
    await session.execute(delete(Aggregator).where(Aggregator.user_id == user_id))
    now = datetime.now(UTC)
    for index, entry in enumerate(entries):
        # Explicit, strictly increasing timestamps: the mixin's server_default is the
        # transaction start time, so every row in this loop would otherwise tie and
        # list_aggregators' insertion-order guarantee (relied on by the profile API
        # round trip) would not hold.
        stamp = now + timedelta(microseconds=index)
        session.add(
            Aggregator(
                user_id=user_id,
                source=entry.source,
                enabled=entry.enabled,
                keywords=list(entry.keywords),
                created_at=stamp,
                updated_at=stamp,
            )
        )
    await session.flush()


def set_track_embedding(track: Track, vector: list[float]) -> None:
    track.embedding = vector


async def delete_all_profile_rows(session: AsyncSession, user_id: uuid.UUID) -> None:
    for model in (ResumeBlock, ResumeBase, Track, Guardrail, Answers, WatchlistEntry):
        await session.execute(delete(model).where(model.user_id == user_id))
    await session.flush()
