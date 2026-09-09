from pathlib import Path

from helpers import demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.entities import check_entities, normalize_entity
from rhapto.engine.guardrails.registry import RULES
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None, config=None):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    return GuardrailContext(
        resume=resume or demo_resume(),
        blocks=profile.block_map(),
        selection_ids=frozenset(profile.block_map()),
        extract=demo_extract(),
        config=config or {},
    )


def test_registered() -> None:
    assert RULES["no-invented-entities"] is check_entities


def test_normalize_handles_dashes_case_and_spaces() -> None:
    assert normalize_entity("  Acme   Analytics ") == "acme analytics"
    assert normalize_entity("2019–2025") == "2019-2025"


def test_passes_for_matching_entities(demo_profile_dir: Path) -> None:
    assert check_entities(make_ctx(demo_profile_dir)) == []


def test_en_dash_period_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2019–2025"
    assert check_entities(make_ctx(demo_profile_dir, resume)) == []


def test_flags_inflated_title(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].role = "Director of Data Programs"
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0]" and "role" in violations[0].message


def test_flags_org_suffix_below_threshold_but_allows_with_lower_threshold(
    demo_profile_dir: Path,
) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].org = "Acme Analytics Inc"
    assert len(check_entities(make_ctx(demo_profile_dir, resume))) == 1
    assert check_entities(make_ctx(demo_profile_dir, resume, {"fuzzy_threshold": 80})) == []


def test_flags_changed_period(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2018-2025"
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "period" in violations[0].message


def test_flags_entity_the_block_does_not_have(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[2].entries[0].org = "Project Management Institute"  # cred-pmp has no org
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and violations[0].block_id == "cred-pmp"


def test_unknown_block_is_skipped_here(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].source_block_id = "ghost"
    assert check_entities(make_ctx(demo_profile_dir, resume)) == []
