"""Token/cost usage for Settings: per-model pricing, summed -- never a single blended rate.

`db.repositories.packages` returns raw sums grouped by model; this module is the one place that
turns those sums into a priced summary, so the API and (if it ever needs one) a CLI report share
the same arithmetic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.repositories.packages import (
    ModelUsageRow,
    RecentPackageUsage,
    recent_usage,
    usage_by_model,
)
from rhapto.engine.providers.llm import TokenUsage
from rhapto.services.pricing import estimate_cost

LAST_N_DAYS = 30
RECENT_LIMIT = 20


@dataclass(frozen=True)
class UsageSummary:
    calls: int
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    cost_usd: Decimal | None
    #: Calls whose package has no priced model (NULL `llm_model`, or a model `pricing` doesn't
    #: list). Their tokens are still in the totals above; their cost is not, so the UI can say the
    #: estimate excludes them instead of silently under-reporting.
    unpriced_calls: int


def _summarize(rows: list[ModelUsageRow]) -> UsageSummary:
    """Price each model's group at its own rate, then add the results.

    Summing tokens across every group first and pricing once would use whichever rate happened to
    be looked up, which is wrong the moment a user has run more than one model.
    """
    total_cost: Decimal | None = None
    unpriced_calls = 0
    for row in rows:
        usage = TokenUsage(
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_read_input_tokens=row.cache_read_tokens,
            cache_creation_input_tokens=row.cache_creation_tokens,
        )
        cost = estimate_cost(row.model, usage)
        if cost is None:
            unpriced_calls += row.calls
        else:
            total_cost = cost if total_cost is None else total_cost + cost
    return UsageSummary(
        calls=sum(r.calls for r in rows),
        input_tokens=sum(r.input_tokens for r in rows),
        output_tokens=sum(r.output_tokens for r in rows),
        cache_read_tokens=sum(r.cache_read_tokens for r in rows),
        cache_creation_tokens=sum(r.cache_creation_tokens for r in rows),
        cost_usd=total_cost,
        unpriced_calls=unpriced_calls,
    )


@dataclass(frozen=True)
class RecentUsageRow:
    package: RecentPackageUsage
    cost_usd: Decimal | None


@dataclass(frozen=True)
class UsageReport:
    totals: UsageSummary
    last_30_days: UsageSummary
    recent: list[RecentUsageRow]


async def usage_report(session: AsyncSession, user_id: uuid.UUID) -> UsageReport:
    all_time = await usage_by_model(session, user_id)
    since = datetime.now(UTC) - timedelta(days=LAST_N_DAYS)
    last_30 = await usage_by_model(session, user_id, since=since)
    recent = await recent_usage(session, user_id, limit=RECENT_LIMIT)
    priced_recent = [
        RecentUsageRow(
            package=row,
            cost_usd=estimate_cost(
                row.model,
                TokenUsage(
                    input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens,
                    cache_read_input_tokens=row.cache_read_tokens,
                    cache_creation_input_tokens=row.cache_creation_tokens,
                ),
            ),
        )
        for row in recent
    ]
    return UsageReport(
        totals=_summarize(all_time), last_30_days=_summarize(last_30), recent=priced_recent
    )
