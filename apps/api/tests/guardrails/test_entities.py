from pathlib import Path

import pytest
from helpers import demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.entities import check_entities, normalize_entity
from rhapto.engine.guardrails.registry import RULES
from rhapto.models.profile.blocks import Block
from rhapto.profile.loader import load_profile

PM_BLOCK = Block(
    id="pm-role",
    type="role",
    org="Acme Analytics",
    role="Product Manager",
    period="2019-2025",
    content="Managed the product.",
)


def ctx_with_role(demo_profile_dir: Path, role: str) -> GuardrailContext:
    """The demo experience entry, re-pointed at a block whose role is exactly "Product Manager"."""
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {PM_BLOCK.id: PM_BLOCK}
    resume = demo_resume()
    entry = resume.sections[0].entries[0]
    entry.source_block_id = PM_BLOCK.id
    entry.role = role
    return GuardrailContext(
        resume=resume,
        blocks=blocks,
        selection_ids=frozenset(blocks),
        extract=demo_extract(),
    )


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


def test_normalize_collapses_spaces_around_dashes() -> None:
    assert normalize_entity("2019 - Present") == normalize_entity("2019-present")


def test_spaced_dash_period_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].period = "2019 - 2025"
    assert check_entities(make_ctx(demo_profile_dir, resume)) == []


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


@pytest.mark.parametrize(
    "role", ["Sr Product Manager", "Product Manager II", "Lead Product Manager"]
)
def test_flags_titles_that_add_a_token(demo_profile_dir: Path, role: str) -> None:
    violations = check_entities(ctx_with_role(demo_profile_dir, role))
    assert len(violations) == 1 and "role" in violations[0].message


def test_allows_case_and_dash_variants_of_the_same_title(demo_profile_dir: Path) -> None:
    assert check_entities(ctx_with_role(demo_profile_dir, "product-manager")) == []


def test_flags_near_miss_org(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].org = "Acme Analytica"  # ratio 92.9: above the floor
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and "org" in violations[0].message


def test_flags_org_with_an_added_token_at_both_thresholds(demo_profile_dir: Path) -> None:
    """The token rule is stricter than the ratio: an added word is an added entity either way."""
    resume = demo_resume()
    resume.sections[0].entries[0].org = "Acme Analytics Inc"
    assert len(check_entities(make_ctx(demo_profile_dir, resume))) == 1
    assert len(check_entities(make_ctx(demo_profile_dir, resume, {"fuzzy_threshold": 80}))) == 1


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


def test_role_entry_may_not_omit_fields_the_block_has(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].role = None
    violations = check_entities(make_ctx(demo_profile_dir, resume))
    assert (
        len(violations) == 1
        and "missing" in violations[0].message
        and "role" in violations[0].message
    )


def test_non_role_entry_may_omit_fields(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries[
        0
    ].org = None  # side-llm-tool is a project block with org Independent
    assert check_entities(make_ctx(demo_profile_dir, resume)) == []
