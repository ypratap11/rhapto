from __future__ import annotations

from decimal import Decimal

from rhapto.engine.providers.llm import TokenUsage
from rhapto.services.pricing import estimate_cost


def test_known_model_prices_input_and_output_tokens() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    cost = estimate_cost("claude-sonnet-5", usage)
    assert cost == Decimal("2.00") + Decimal("10.00")


def test_unknown_model_returns_none() -> None:
    assert estimate_cost("some-model-nobody-priced", TokenUsage(input_tokens=100)) is None


def test_none_model_returns_none() -> None:
    assert estimate_cost(None, TokenUsage(input_tokens=100)) is None


def test_cache_read_is_priced_at_a_tenth_of_input_rate() -> None:
    usage = TokenUsage(cache_read_input_tokens=1_000_000)
    cost = estimate_cost("claude-sonnet-5", usage)
    assert cost == Decimal("2.00") * Decimal("0.1")


def test_cache_creation_is_priced_at_1_25x_input_rate() -> None:
    usage = TokenUsage(cache_creation_input_tokens=1_000_000)
    cost = estimate_cost("claude-sonnet-5", usage)
    assert cost == Decimal("2.00") * Decimal("1.25")


def test_opus_and_haiku_rates_differ_from_sonnet() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert estimate_cost("claude-opus-5", usage) == Decimal("5.00") + Decimal("25.00")
    assert estimate_cost("claude-haiku-4-5", usage) == Decimal("1.00") + Decimal("5.00")


def test_returns_decimal_not_float() -> None:
    cost = estimate_cost("claude-sonnet-5", TokenUsage(input_tokens=1))
    assert isinstance(cost, Decimal)


def test_zero_usage_is_zero_cost() -> None:
    assert estimate_cost("claude-sonnet-5", TokenUsage()) == Decimal("0")


def test_a_dated_model_id_prices_the_same_as_its_alias() -> None:
    """Anthropic publishes both `claude-haiku-4-5` and `claude-haiku-4-5-20251001` for one model.

    A real run made with the dated id recorded cost=None, which is worse than a stale estimate: an
    unpriced row drops out of the usage total silently instead of showing up as a number to check.
    """
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    alias = estimate_cost("claude-haiku-4-5", usage)
    dated = estimate_cost("claude-haiku-4-5-20251001", usage)
    assert alias is not None
    assert dated == alias


def test_the_longest_matching_prefix_wins() -> None:
    """Guards the rule that keeps a future `...-pro` from being swallowed by a shorter prefix."""
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=0)
    assert estimate_cost("claude-opus-5-20260101", usage) == estimate_cost("claude-opus-5", usage)


def test_a_genuinely_unknown_model_still_returns_none() -> None:
    """Prefix tolerance must not turn 'no idea' into a wrong number."""
    assert (
        estimate_cost("some-other-vendor-model", TokenUsage(input_tokens=10, output_tokens=10))
        is None
    )
