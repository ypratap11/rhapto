from pathlib import Path

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.metrics import (
    check_metrics,
    find_numeric_tokens,
    find_spelled_quantities,
    normalize_number,
)
from rhapto.engine.guardrails.registry import RULES
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    return GuardrailContext(
        resume=resume or demo_resume(),
        blocks=profile.block_map(),
        selection_ids=frozenset(profile.block_map()),
        extract=demo_extract(),
    )


def test_not_registered_because_it_is_unconditional() -> None:
    """It used to be in RULES, which made it a row a user could omit or disable. It is not any more.

    `run_guardrails` calls `check_metrics` directly, beside provenance.
    """
    assert "no-unverified-metrics" not in RULES
    assert check_metrics is not None


def test_tokenizers() -> None:
    assert find_numeric_tokens("cut cost 18% and saved $2.5M across 12 pipelines, 3x faster") == [
        "18%",
        "$2.5M",
        "12",
        "3x",
    ]
    assert find_numeric_tokens("v2 API and iso-8601") == []
    assert [normalize_number(t) for t in ["18%", "$2.5M", "1,200", "3x"]] == [
        "18",
        "2.5",
        "1200",
        "3",
    ]
    assert find_spelled_quantities(
        "shrank the backlog by nearly a fifth and doubled throughput"
    ) == [
        "a fifth",
        "doubled",
    ]


def test_passes_when_numbers_trace_to_verified_blocks(demo_profile_dir: Path) -> None:
    assert check_metrics(make_ctx(demo_profile_dir)) == []


def test_flags_number_absent_from_source(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets[1] = bullet(
        "Cut warehouse cost 25% via Snowflake migration.", "acme-migration"
    )
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0].bullets[1]"
    assert "25%" in violations[0].message and violations[0].block_id == "acme-migration"


def test_flags_number_from_unverified_block_even_if_present_in_source(
    demo_profile_dir: Path,
) -> None:
    resume = demo_resume()
    resume.sections[1].entries[0].bullets[0] = bullet(
        "Built an LLM eval harness with 1.2k GitHub stars.", "side-llm-tool"
    )
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "not verified" in violations[0].message


def test_adversarial_spelled_out_fraction(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets[1] = bullet(
        "Cut warehouse cost by nearly a fifth through the Snowflake migration.", "acme-migration"
    )
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "a fifth" in violations[0].message


def test_adversarial_multiplier_and_currency(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Delivered $2M in savings, 3x faster than plan.", "acme-migration")]
    messages = " ".join(v.message for v in check_metrics(make_ctx(demo_profile_dir, resume)))
    assert "$2M" in messages and "3x" in messages


def test_years_in_block_period_are_exempt(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [
        bullet("Since 2019 has led data platform programs at Acme Analytics.", "acme-data-pm")
    ]
    assert check_metrics(make_ctx(demo_profile_dir, resume)) == []


def test_years_outside_block_period_are_not_exempt(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Since 2015 has led data platform programs.", "acme-data-pm")]
    assert len(check_metrics(make_ctx(demo_profile_dir, resume))) == 1


def test_unknown_block_is_skipped_here(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Saved 99%.", "ghost")]
    assert check_metrics(make_ctx(demo_profile_dir, resume)) == []  # provenance rule reports it


def test_cardinal_tokenizer() -> None:
    assert find_spelled_quantities("cut costs by eighteen percent") == ["eighteen"]
    assert find_spelled_quantities("a twenty-five percent reduction") == ["twenty-five"]
    assert find_spelled_quantities("saved forty thousand dollars") == ["forty thousand"]
    assert find_spelled_quantities("one platform for one team") == []
    assert find_spelled_quantities("grew one million users") == ["one million"]
    assert find_spelled_quantities("hundreds of migrations") == ["hundreds"]


def test_adversarial_spelled_out_cardinal(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets[1] = bullet(
        "Cut warehouse cost by eighteen percent through the Snowflake migration.", "acme-migration"
    )
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "eighteen" in violations[0].message


def test_prose_one_is_not_a_metric(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary = [bullet("Led one platform program end to end.", "acme-data-pm")]
    assert check_metrics(make_ctx(demo_profile_dir, resume)) == []


NUMERIC_ROWS = [
    ("Cut p95 latency by 40ms.", ["40ms"]),
    ("Led a 40-person team.", ["40"]),
    ("Grew revenue 3-fold.", ["3"]),
    ("Scaled to 10TB of data.", ["10TB"]),
    ("Cut build time from 30min to 5min.", ["30min", "5min"]),
    ("raised $2.5M", ["$2.5M"]),
    ("improved NPS by 12 points", ["12"]),
    ("Shipped v2 API", []),
    ("Follows iso-8601", []),
    ("Wrote it in Python3", []),
]


@pytest.mark.parametrize(("text", "expected"), NUMERIC_ROWS, ids=[row[0] for row in NUMERIC_ROWS])
def test_numeric_tokenizer_realistic_metrics(text: str, expected: list[str]) -> None:
    tokens = find_numeric_tokens(text)
    if not expected:
        assert tokens == []
        return
    assert tokens, f"no numeric token found in {text!r}"
    for token in expected:
        assert token in tokens, f"{token!r} not in {tokens!r}"


def test_adversarial_unit_suffixed_and_hyphenated_metrics(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries[0].bullets[0] = bullet(
        "Cut eval latency by 40ms for a 12-person team.", "side-llm-tool"
    )
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert "40ms" in violations[0].message and "12" in violations[0].message


def test_adversarial_metric_hidden_in_entry_title(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries[
        0
    ].title = "Open-source LLM eval harness (12k GitHub stars, 40% faster)"
    violations = check_metrics(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[1].entries[0].title"
    assert violations[0].block_id == "side-llm-tool" and "12k" in violations[0].message


def test_entry_period_copied_from_a_verified_block_is_not_a_metric(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    assert resume.sections[0].entries[0].period == "2019-2025"  # verified block acme-data-pm
    assert check_metrics(make_ctx(demo_profile_dir, resume)) == []
