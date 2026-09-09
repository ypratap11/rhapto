from pathlib import Path

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


def test_registered() -> None:
    assert RULES["no-unverified-metrics"] is check_metrics


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
