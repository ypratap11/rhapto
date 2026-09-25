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
    # Reached through OpenRouter, so the id carries its vendor prefix -- that string is what the
    # package records and therefore what this table must be keyed on. NOTE: a promotional rate
    # (50% off list) as of 2026-09-25; when the sale ends this line is wrong until someone updates
    # it, which is the standing hazard of any price list in source.
    "google/gemini-3.8-flash": ModelRate(Decimal("0.75"), Decimal("3.75")),
}

# Cache-token multipliers of the base input rate. These are standard Anthropic cache pricing
# ratios (a cache read is far cheaper than a fresh input token; writing to the cache costs a
# premium over it), ASSUMED here because MODEL_RATES only lists input/output rates -- if Anthropic
# changes these ratios, or a model's own listing differs, this is a one-line correction.
CACHE_READ_MULTIPLIER = Decimal("0.1")
CACHE_CREATION_MULTIPLIER = Decimal("1.25")


def _rate_for(model: str) -> ModelRate | None:
    """The rate for a model id, tolerating the dated form vendors also publish.

    Anthropic ships both a rolling alias and a dated id for the same model -- `claude-haiku-4-5`
    and `claude-haiku-4-5-20251001` price identically, but only the alias is listed above. A run
    made with the dated id was therefore recorded with no cost at all, which is worse than a stale
    estimate: it silently drops out of the usage total instead of showing up as a number to check.
    So an exact match wins, and failing that the longest listed id the model starts with does --
    longest so that adding, say, `claude-haiku-4-5-pro` later cannot be swallowed by the shorter
    `claude-haiku-4-5` prefix.
    """
    exact = MODEL_RATES.get(model)
    if exact is not None:
        return exact
    prefixes = [known for known in MODEL_RATES if model.startswith(known)]
    if not prefixes:
        return None
    return MODEL_RATES[max(prefixes, key=len)]


def estimate_cost(model: str | None, usage: TokenUsage) -> Decimal | None:
    """The estimated USD cost of `usage` on `model`, or None if the model isn't priced.

    None (not zero) is the "can't say" case: an unknown or missing model must never be reported as
    free, so callers that sum this across packages need to track how many rows return None
    separately rather than adding them into the total in place of a price.
    """
    if model is None:
        return None
    rate = _rate_for(model)
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
