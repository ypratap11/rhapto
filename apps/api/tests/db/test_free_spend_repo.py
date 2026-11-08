from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import FreeSpend
from rhapto.db.repositories.free_spend import month_free_spend, record_free_spend


async def _add(session: AsyncSession, cost: str) -> None:
    await record_free_spend(
        session,
        user_id=uuid.uuid4(),
        model="test-model",
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        cost_usd=Decimal(cost),
    )


async def test_month_spend_is_zero_when_empty(session: AsyncSession) -> None:
    assert await month_free_spend(session) == Decimal(0)


async def test_month_spend_sums_all_users(session: AsyncSession) -> None:
    await _add(session, "0.10")
    await _add(session, "0.25")
    await session.commit()
    assert await month_free_spend(session) == Decimal("0.35")


async def test_spend_from_last_month_does_not_count(session: AsyncSession) -> None:
    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    session.add(
        FreeSpend(
            user_id=uuid.uuid4(),
            model="test-model",
            cost_usd=Decimal("9.00"),
            created_at=month_start - timedelta(seconds=1),
        )
    )
    await _add(session, "0.05")
    await session.commit()
    assert await month_free_spend(session) == Decimal("0.05")
