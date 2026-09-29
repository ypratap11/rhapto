from pathlib import Path

import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.completeness import RULE_NAME, check_completeness
from rhapto.engine.guardrails.registry import RULES, UnknownGuardrailError, run_guardrails
from rhapto.engine.guardrails.tune import run_tune_guardrails
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.resume_document import (
    ResumeDocument,
    ResumeEntry,
    ResumeHeader,
    ResumeSection,
)
from rhapto.profile.loader import load_profile


def _role(id: str, org: str, role: str, period: str, content: str, **extra: object) -> Block:
    return Block(id=id, type="role", org=org, role=role, period=period, content=content, **extra)  # type: ignore[arg-type]


ROLE_A = _role("role-a", "Globex", "Engineer", "2018-2020", "Built things.")
ROLE_B = _role("role-b", "Initech", "Analyst", "2020-2021", "Analysed things.")
ROLE_C = _role("role-c", "Umbrella", "Lead", "2021-2022", "Led things.")
ROLE_D = _role("role-d", "Hooli", "Manager", "2022-2023", "Managed things.")
ROLE_E = _role("role-e", "Vertex Robotics", "Founder", "2023-Present", "Founded a company.")
FIVE_ROLES = [ROLE_A, ROLE_B, ROLE_C, ROLE_D, ROLE_E]

ROLE_F = _role("role-f", "Vertex Robotics", "Co-Founder", "2023-Present", "Co-founded.")
VERTEX_ACHIEVEMENT = Block(
    id="vertex-achievement", type="achievement", org="Vertex Robotics", content="Shipped a robot."
)

PROJECT_A = Block(id="project-a", type="project", org="Independent", content="Built a tool.")
CRED_A = Block(id="cred-a", type="credential", content="Some certification.")
SKILL_X = Block(id="skill-x", type="skill", content="Python")
ACHIEVEMENT_X = Block(id="ach-x", type="achievement", org="Globex", content="Did a thing.")
UNRENDERABLE = Block(id="ghost-role", type="role", content="")
ATTRIBUTION_ROLE = _role(
    "attrib-role",
    "Globex",
    "Consultant",
    "2019-2020",
    "Consulted.",
    attribution="as part of the Globex Partner Program",
)


def _ctx(blocks: list[Block], resume: ResumeDocument, selection_ids: list[str]) -> GuardrailContext:
    return GuardrailContext(
        resume=resume,
        blocks={b.id: b for b in blocks},
        selection_ids=frozenset(selection_ids),
        extract=demo_extract(),
    )


def _entry(block: Block, **overrides: object) -> ResumeEntry:
    defaults: dict[str, object] = dict(
        source_block_id=block.id,
        org=block.org,
        role=block.role,
        period=block.period,
        bullets=[bullet(f"Did {block.role} work.", block.id)],
    )
    defaults.update(overrides)
    return ResumeEntry(**defaults)  # type: ignore[arg-type]


def _resume(
    entries: list[ResumeEntry], kind: str = "experience", title: str = "Experience"
) -> ResumeDocument:
    return ResumeDocument(
        header=ResumeHeader(name="Test Person"),
        sections=[ResumeSection(title=title, kind=kind, entries=entries)],  # type: ignore[arg-type]
    )


def test_measured_case_one_role_missing_of_five() -> None:
    present = FIVE_ROLES[:4]
    resume = _resume([_entry(b) for b in present])
    ctx = _ctx(FIVE_ROLES, resume, [b.id for b in FIVE_ROLES])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    v = violations[0]
    assert v.rule == RULE_NAME and v.severity == "error" and v.block_id == "role-e"
    assert "role-e" in v.message and "Vertex Robotics" in v.message and "Founder" in v.message
    assert v.path == "selection.block_ids['role-e']"


def test_merge_fold_produces_one_violation_naming_the_entry() -> None:
    entry_a = _entry(
        ROLE_A,
        bullets=[
            bullet("Did Engineer work.", ROLE_A.id),
            bullet("Shipped a robot for Vertex Robotics.", VERTEX_ACHIEVEMENT.id),
        ],
    )
    resume = _resume([entry_a] + [_entry(b) for b in FIVE_ROLES[1:4]])
    blocks = FIVE_ROLES + [VERTEX_ACHIEVEMENT]
    ctx = _ctx(blocks, resume, [b.id for b in FIVE_ROLES] + [VERTEX_ACHIEVEMENT.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    assert violations[0].block_id == "role-e"
    assert "sections[0].entries[0]" in violations[0].message
    assert "folded" in violations[0].message


def test_substitution_same_org_sibling_present() -> None:
    entries = [_entry(b) for b in FIVE_ROLES[:4]] + [_entry(ROLE_F)]
    resume = _resume(entries)
    blocks = FIVE_ROLES + [ROLE_F]
    ctx = _ctx(blocks, resume, [b.id for b in FIVE_ROLES] + [ROLE_F.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    assert violations[0].block_id == "role-e"
    assert "role-f" in violations[0].message and "substituted" in violations[0].message


def test_a_common_word_org_does_not_annotate_an_unrelated_entry_as_a_fold() -> None:
    """M-1: "Independent" is an org in `profile.example`; it must not match "independently"."""
    independent_role = _role("role-i", "Independent", "Consultant", "2016-2017", "Consulted.")
    sibling = _entry(ROLE_A, bullets=[bullet("Worked independently on a rebuild.", ROLE_A.id)])
    ctx = _ctx([ROLE_A, independent_role], _resume([sibling]), [ROLE_A.id, independent_role.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1 and violations[0].block_id == "role-i"
    assert "folded" not in violations[0].message


def test_duplicate_entries_for_one_block() -> None:
    resume = _resume([_entry(ROLE_A), _entry(ROLE_A)])
    ctx = _ctx([ROLE_A], resume, [ROLE_A.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    assert violations[0].block_id == "role-a"
    assert "expected exactly one" in violations[0].message


def test_clean_variation_with_reworded_bullets_passes(demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    resume = demo_resume()
    resume.sections[0].entries[0].bullets = list(reversed(resume.sections[0].entries[0].bullets))
    resume.sections[0].entries[0].bullets[0] = bullet(
        "Different wording, same block.", "acme-data-pm"
    )
    resume.sections[0].title = "Career History"
    ctx = GuardrailContext(
        resume=resume,
        blocks=profile.block_map(),
        selection_ids=frozenset(profile.block_map()),
        extract=demo_extract(),
    )
    assert check_completeness(ctx) == []


def test_skill_and_achievement_never_checked() -> None:
    resume = _resume([])
    ctx = _ctx([SKILL_X, ACHIEVEMENT_X], resume, [SKILL_X.id, ACHIEVEMENT_X.id])
    assert check_completeness(ctx) == []


def test_role_entry_in_wrong_section_kind() -> None:
    resume = ResumeDocument(
        header=ResumeHeader(name="Test Person"),
        sections=[ResumeSection(title="Projects", kind="projects", entries=[_entry(ROLE_A)])],
    )
    ctx = _ctx([ROLE_A], resume, [ROLE_A.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    assert violations[0].block_id == "role-a"
    assert "projects" in violations[0].message


def test_role_entry_with_blank_org_is_flagged() -> None:
    resume = _resume([_entry(ROLE_A, org=None)])
    ctx = _ctx([ROLE_A], resume, [ROLE_A.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1 and "org" in violations[0].message


def test_project_entry_with_blank_title_and_role_is_flagged() -> None:
    resume = ResumeDocument(
        header=ResumeHeader(name="Test Person"),
        sections=[
            ResumeSection(
                title="Projects",
                kind="projects",
                entries=[
                    ResumeEntry(
                        source_block_id=PROJECT_A.id,
                        org="Independent",
                        bullets=[bullet("Built a tool.", PROJECT_A.id)],
                    )
                ],
            )
        ],
    )
    ctx = _ctx([PROJECT_A], resume, [PROJECT_A.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1 and "title/role" in violations[0].message


def test_credential_with_neither_label_nor_bullets_is_flagged() -> None:
    resume = ResumeDocument(
        header=ResumeHeader(name="Test Person"),
        sections=[
            ResumeSection(
                title="Credentials",
                kind="credentials",
                entries=[ResumeEntry(source_block_id=CRED_A.id)],
            )
        ],
    )
    ctx = _ctx([CRED_A], resume, [CRED_A.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1 and violations[0].block_id == "cred-a"


def test_credential_with_bullet_and_no_label_is_clean(demo_profile_dir: Path) -> None:
    """The `cred-pmp` shape: no org/role/title, one bullet -- must stay clean."""
    profile = load_profile(demo_profile_dir)
    resume = demo_resume()
    ctx = GuardrailContext(
        resume=resume,
        blocks=profile.block_map(),
        selection_ids=frozenset(profile.block_map()),
        extract=demo_extract(),
    )
    assert check_completeness(ctx) == []


def test_empty_selection_produces_no_violations() -> None:
    resume = _resume([])
    ctx = _ctx(FIVE_ROLES, resume, [])
    assert check_completeness(ctx) == []


def test_selection_id_not_in_block_map_is_skipped_not_raised() -> None:
    """C-3: the selection names ONLY the unknown id. Naming a real, absent role alongside it would
    (correctly) produce a violation for that role and hide what this test is about."""
    resume = _resume([])
    ctx = _ctx([ROLE_A], resume, ["ghost-not-in-library"])
    assert check_completeness(ctx) == []


def test_unrenderable_block_is_a_warning_not_an_error() -> None:
    resume = _resume([])
    ctx = _ctx([UNRENDERABLE], resume, [UNRENDERABLE.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    assert violations[0].severity == "warning" and violations[0].block_id == "ghost-role"


def test_unrenderable_block_leaves_the_report_passed(demo_profile_dir: Path) -> None:
    base = load_profile(demo_profile_dir)
    profile = base.model_copy(update={"blocks": [*base.blocks, UNRENDERABLE]})
    resume = demo_resume()
    report = run_guardrails(resume, profile, [*base.block_map(), UNRENDERABLE.id], demo_extract())
    assert report.passed is True
    assert any(v.rule == RULE_NAME and v.severity == "warning" for v in report.violations)


def test_attribution_bearing_block_with_bullet_less_entry_is_a_completeness_error() -> None:
    entry = ResumeEntry(
        source_block_id=ATTRIBUTION_ROLE.id,
        org="Globex",
        role="Consultant",
        period="2019-2020",
        bullets=[],
    )
    ctx = _ctx([ATTRIBUTION_ROLE], _resume([entry]), [ATTRIBUTION_ROLE.id])
    violations = check_completeness(ctx)
    assert len(violations) == 1
    assert violations[0].rule == RULE_NAME and violations[0].block_id == ATTRIBUTION_ROLE.id
    assert "attribution" in violations[0].message


def test_attribution_phrase_carried_by_the_entry_header_is_not_a_gap() -> None:
    """I-1: `check_attribution` also reads title/org/role, so a bullet-less entry whose header
    carries the phrase satisfies `attribution` -- and must not be failed by `completeness`."""
    entry = ResumeEntry(
        source_block_id=ATTRIBUTION_ROLE.id,
        title="Consultant as part of the Globex Partner Program",
        org="Globex",
        role="Consultant",
        period="2019-2020",
        bullets=[],
    )
    ctx = _ctx([ATTRIBUTION_ROLE], _resume([entry]), [ATTRIBUTION_ROLE.id])
    assert check_completeness(ctx) == []


def test_attribution_missing_from_a_bulleted_entry_is_left_to_the_attribution_rule() -> None:
    """One violation per defect (C7): with a bullet present, only `attribution` reports it."""
    ctx = _ctx([ATTRIBUTION_ROLE], _resume([_entry(ATTRIBUTION_ROLE)]), [ATTRIBUTION_ROLE.id])
    assert check_completeness(ctx) == []


def _with_blocks(demo_profile_dir: Path, *extra: Block):  # type: ignore[no-untyped-def]
    base = load_profile(demo_profile_dir)
    return base.model_copy(update={"blocks": [*base.blocks, *extra]})


def test_restoring_a_dropped_concurrent_side_role_surfaces_a_date_overlap(
    demo_profile_dir: Path,
) -> None:
    """Architecture §5.4: a model that dropped the overlapping side role made `date-consistency`
    pass BECAUSE of the omission. Once completeness forces the role back, the overlap is real.
    The fix is `concurrent: true` on the block, not a change to either rule."""
    side = _role("side-role", "Sidecar Labs", "Advisor", "2019-2021", "Advised.")
    profile = _with_blocks(demo_profile_dir, side)
    resume = demo_resume()
    resume.sections[0].entries.append(_entry(side))
    selected = [*profile.block_map()]
    report = run_guardrails(resume, profile, selected, demo_extract())
    assert not any(v.rule == RULE_NAME for v in report.violations)
    assert [v.rule for v in report.violations if v.severity == "error"] == ["date-consistency"]
    assert report.passed is False


def test_the_same_side_role_flagged_concurrent_is_clean(demo_profile_dir: Path) -> None:
    side = _role("side-role", "Sidecar Labs", "Advisor", "2019-2021", "Advised.", concurrent=True)
    profile = _with_blocks(demo_profile_dir, side)
    resume = demo_resume()
    resume.sections[0].entries.append(_entry(side))
    report = run_guardrails(resume, profile, [*profile.block_map()], demo_extract())
    assert report.passed is True, [v.model_dump() for v in report.violations]


def test_dropping_that_side_role_is_now_a_completeness_error_not_a_pass(
    demo_profile_dir: Path,
) -> None:
    """The other half of the interaction: before this rule the drop passed silently."""
    side = _role("side-role", "Sidecar Labs", "Advisor", "2019-2021", "Advised.", concurrent=True)
    profile = _with_blocks(demo_profile_dir, side)
    report = run_guardrails(demo_resume(), profile, [*profile.block_map()], demo_extract())
    assert [(v.rule, v.block_id) for v in report.violations if v.severity == "error"] == [
        (RULE_NAME, "side-role")
    ]


def test_completeness_is_unconditional_and_rejected_as_a_configured_rule(
    demo_profile_dir: Path,
) -> None:
    assert "completeness" not in RULES
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
    report = run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())
    assert report.rules_run == ["provenance", "no-unverified-metrics", "completeness"]
    bad = profile.model_copy(update={"guardrails": [GuardrailRule(rule="completeness")]})
    with pytest.raises(UnknownGuardrailError, match="completeness"):
        run_guardrails(demo_resume(), bad, profile.block_map(), demo_extract())


def test_completeness_cannot_be_switched_off_by_an_empty_guardrails_table(
    demo_profile_dir: Path,
) -> None:
    """The half that protects the user: a bare account still catches a dropped role."""
    profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
    resume = demo_resume()
    resume.sections[0].entries = []
    report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
    assert report.passed is False
    assert [v.block_id for v in report.violations if v.rule == RULE_NAME] == ["acme-data-pm"]


def test_tune_guardrails_never_emit_completeness(demo_profile_dir: Path) -> None:
    from helpers_docx import build_fixture_docx

    from rhapto.engine.document import parse_docx

    profile = load_profile(demo_profile_dir)
    doc = parse_docx(build_fixture_docx(), "resume.docx")
    report = run_tune_guardrails(doc, [], demo_extract(), profile.guardrails, cover_note=None)
    assert "completeness" not in report.rules_run
    assert all(v.rule != "completeness" for v in report.violations)


def test_a_duplicated_entry_is_reported_by_two_rules_by_design(demo_profile_dir: Path) -> None:
    """Recorded exception to "one violation per defect" (C7 / AC8 are worded around merge and
    substitution). A block printed twice overlaps itself, so `date-consistency` also errors. That
    rule is not ours to suppress, and both messages are true; this test pins the behaviour so a
    change to either rule is a decision rather than an accident."""
    profile = load_profile(demo_profile_dir)
    resume = demo_resume()
    resume.sections[0].entries.append(resume.sections[0].entries[0].model_copy(deep=True))
    report = run_guardrails(resume, profile, [*profile.block_map()], demo_extract())
    errors = [v.rule for v in report.violations if v.severity == "error"]
    assert errors.count("completeness") == 1
    assert sorted(set(errors)) == ["completeness", "date-consistency"]
