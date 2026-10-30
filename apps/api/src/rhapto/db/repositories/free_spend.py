"""Free-spend ledger: model calls paid for by the deployment's key. Append-only."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import FreeSpend
from rhapto.engine.providers.llm import TokenUsage


async def record_free_spend(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    model: str,
    usage: TokenUsage,
    cost_usd: Decimal,
) -> None:
    """Add one ledger row. The caller commits."""
    session.add(
        FreeSpend(
            user_id=user_id,
            model=model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_read_tokens=usage.cache_read_input_tokens,
            cache_creation_tokens=usage.cache_creation_input_tokens,
            cost_usd=cost_usd,
        )
    )


async def month_free_spend(session: AsyncSession) -> Decimal:
    """This UTC calendar month's spend across all users; `Decimal(0)` when there is none.

    The boundary is computed in SQL with the three-argument `date_trunc`, so it does not depend on
    the session's time zone.
    """
    total = await session.scalar(
        select(func.coalesce(func.sum(FreeSpend.cost_usd), 0)).where(
            FreeSpend.created_at >= text("date_trunc('month', now(), 'UTC')")
        )
    )
    return Decimal(0) if total is None else Decimal(total)
