from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.dates import PRESENT, check_dates, parse_period
from rhapto.engine.guardrails.registry import RULES
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeEntry
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None, extra_blocks=()):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {b.id: b for b in extra_blocks}
    return GuardrailContext(
        resume=resume or demo_resume(),
        blocks=blocks,
        selection_ids=frozenset(blocks),
        extract=demo_extract(),
    )


def _second_role(concurrent: bool = False, period: str = "2022-2024") -> tuple[Block, ResumeEntry]:
    block = Block(
        id="beta-role",
        type="role",
        org="Beta Labs",
        role="Advisor",
        period=period,
        content="Advised.",
        concurrent=concurrent,
    )
    entry = ResumeEntry(
        source_block_id="beta-role",
        org="Beta Labs",
        role="Advisor",
        period=period,
        bullets=[bullet("Advised.", "beta-role")],
    )
    return block, entry


def test_registered() -> None:
    assert RULES["date-consistency"] is check_dates


def test_parse_period_formats() -> None:
    assert parse_period("2019-2025") == (2019, 2025)
    assert parse_period("2019 – 2025") == (2019, 2025)
    assert parse_period("2019 to 2025") == (2019, 2025)
    assert parse_period("2021-Present") == (2021, PRESENT)
    assert parse_period("2023") == (2023, 2023)
    assert parse_period("Spring 2020") is None
    assert parse_period("") is None


def test_passes_for_demo(demo_profile_dir: Path) -> None:
    assert check_dates(make_ctx(demo_profile_dir)) == []


def test_flags_unparseable_period(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "Spring 2020"
    violations = check_dates(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "unparseable" in violations[0].message


def test_flags_reversed_range(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2025-2019"
    violations = check_dates(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "ends before it starts" in violations[0].message


def test_flags_overlapping_roles(demo_profile_dir: Path) -> None:
    block, entry = _second_role()
    resume = demo_resume()
    resume.sections[0].entries.append(entry)
    violations = check_dates(make_ctx(demo_profile_dir, resume, [block]))
    assert len(violations) == 1 and "overlaps" in violations[0].message
    assert violations[0].path == "sections[0].entries[1]"


def test_allows_overlap_when_a_block_is_concurrent(demo_profile_dir: Path) -> None:
    block, entry = _second_role(concurrent=True)
    resume = demo_resume()
    resume.sections[0].entries.append(entry)
    assert check_dates(make_ctx(demo_profile_dir, resume, [block])) == []


def test_adjacent_years_do_not_overlap(demo_profile_dir: Path) -> None:
    block, entry = _second_role(period="2025-Present")
    resume = demo_resume()
    resume.sections[0].entries.append(entry)
    assert check_dates(make_ctx(demo_profile_dir, resume, [block])) == []


def test_projects_section_is_not_checked_for_overlap(demo_profile_dir: Path) -> None:
    block, entry = _second_role()
    resume = demo_resume()
    resume.sections[1].entries.append(entry)  # projects section
    assert check_dates(make_ctx(demo_profile_dir, resume, [block])) == []
