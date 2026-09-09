from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.attribution import check_attribution
from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.registry import RULES
from rhapto.models.profile.blocks import Block
from rhapto.models.resume_document import ResumeEntry
from rhapto.profile.loader import load_profile

STUDIO = Block(
    id="studio-app",
    type="project",
    org="Example Studio",
    content="Shipped a scheduling app for a retail client.",
    attribution="built at Example Studio",
)


def make_ctx(demo_profile_dir: Path, resume):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {STUDIO.id: STUDIO}
    return GuardrailContext(
        resume=resume, blocks=blocks, selection_ids=frozenset(blocks), extract=demo_extract()
    )


def _project_entry(text: str) -> ResumeEntry:
    return ResumeEntry(
        source_block_id="studio-app",
        org="Example Studio",
        title="Scheduling app",
        bullets=[bullet(text, "studio-app")],
    )


def test_registered() -> None:
    assert RULES["attribution"] is check_attribution


def test_passes_when_no_block_has_attribution(demo_profile_dir: Path) -> None:
    assert check_attribution(make_ctx(demo_profile_dir, demo_resume())) == []


def test_passes_when_entry_carries_attribution(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries.append(
        _project_entry("Shipped a scheduling app, built at Example Studio.")
    )
    assert check_attribution(make_ctx(demo_profile_dir, resume)) == []


def test_flags_entry_missing_attribution(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[1].entries.append(
        _project_entry("Shipped a scheduling app deployed at a retail client.")
    )
    violations = check_attribution(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1 and violations[0].path == "sections[1].entries[1]"
    assert "built at Example Studio" in violations[0].message


def test_flags_leaked_bullet_under_another_entry(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(
        bullet("Shipped a scheduling app for a retail client.", "studio-app")
    )
    violations = check_attribution(make_ctx(demo_profile_dir, resume))
    assert [v.path for v in violations] == ["sections[0].entries[0].bullets[2]"]


def test_flags_summary_bullet_without_attribution(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary.append(bullet("Shipped a retail scheduling app.", "studio-app"))
    assert [v.path for v in check_attribution(make_ctx(demo_profile_dir, resume))] == ["summary[1]"]


def test_attribution_match_is_case_insensitive(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.summary.append(
        bullet("Shipped a retail scheduling app, Built At Example Studio.", "studio-app")
    )
    assert check_attribution(make_ctx(demo_profile_dir, resume)) == []
