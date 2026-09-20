"""Estimated USD cost of an LLM run, from a model id and its token usage.

Estimates only: the price list below is a point-in-time snapshot the vendors can change without
notice, and an unpriced model (a new release, a typo, a provider we don't track yet) must degrade
to "no estimate" rather than a wrong number, so callers show tokens either way and cost only when
it means something.
"""

from __future__ import annotations

from decimal import Decimal
from typing import NamedTuple

from rhapto.engine.providers.llm import TokenUsage


class ModelRate(NamedTuple):
    """USD per 1,000,000 tokens."""

    input_per_million: Decimal
    output_per_million: Decimal


#: Anthropic's published per-1M-token rates for the models Settings offers. Extend this table as
#: new models are priced; an unlisted model simply returns no estimate (see `estimate_cost`).
MODEL_RATES: dict[str, ModelRate] = {
    "claude-opus-5": ModelRate(Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": ModelRate(Decimal("2.00"), Decimal("10.00")),
    "claude-haiku-4-5": ModelRate(Decimal("1.00"), Decimal("5.00")),
}

# Cache-token multipliers of the base input rate. These are standard Anthropic cache pricing
# ratios (a cache read is far cheaper than a fresh input token; writing to the cache costs a
# premium over it), ASSUMED here because MODEL_RATES only lists input/output rates -- if Anthropic
# changes these ratios, or a model's own listing differs, this is a one-line correction.
CACHE_READ_MULTIPLIER = Decimal("0.1")
CACHE_CREATION_MULTIPLIER = Decimal("1.25")


def estimate_cost(model: str | None, usage: TokenUsage) -> Decimal | None:
    """The estimated USD cost of `usage` on `model`, or None if the model isn't priced.

    None (not zero) is the "can't say" case: an unknown or missing model must never be reported as
    free, so callers that sum this across packages need to track how many rows return None
    separately rather than adding them into the total in place of a price.
    """
    if model is None:
        return None
    rate = MODEL_RATES.get(model)
    if rate is None:
        return None
    million = Decimal(1_000_000)
    input_cost = Decimal(usage.input_tokens) * rate.input_per_million / million
    output_cost = Decimal(usage.output_tokens) * rate.output_per_million / million
    cache_read_cost = (
        Decimal(usage.cache_read_input_tokens)
        * rate.input_per_million
        * CACHE_READ_MULTIPLIER
        / million
    )
    cache_creation_cost = (
        Decimal(usage.cache_creation_input_tokens)
        * rate.input_per_million
        * CACHE_CREATION_MULTIPLIER
        / million
    )
    return input_cost + output_cost + cache_read_cost + cache_creation_cost
