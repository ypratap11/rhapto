from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import GuardrailContext
from rhapto.engine.guardrails.registry import RULES
from rhapto.engine.guardrails.visibility import check_visibility
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.models.resume_document import ResumeEntry
from rhapto.profile.loader import load_profile

SECRET = Block(
    id="agency-secret",
    type="achievement",
    org="Acme Analytics",
    content="Delivered a client migration.",
    visibility=Visibility(exclude_when=["agency", "internal-transfer"]),
)


def make_ctx(demo_profile_dir: Path, resume, context_tags):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    blocks = profile.block_map() | {SECRET.id: SECRET}
    extract = demo_extract().model_copy(update={"context_tags": context_tags})
    return GuardrailContext(
        resume=resume, blocks=blocks, selection_ids=frozenset(blocks), extract=extract
    )


def test_registered() -> None:
    assert RULES["visibility-context"] is check_visibility


def test_passes_when_context_does_not_match(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(
        bullet("Delivered a client migration.", "agency-secret")
    )
    assert check_visibility(make_ctx(demo_profile_dir, resume, ["startup"])) == []


def test_flags_bullet_when_context_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(
        bullet("Delivered a client migration.", "agency-secret")
    )
    violations = check_visibility(make_ctx(demo_profile_dir, resume, ["agency"]))
    assert len(violations) == 1
    assert (
        violations[0].path == "sections[0].entries[0].bullets[2]"
        and "agency" in violations[0].message
    )


def test_flags_entry_when_context_matches(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries.append(
        ResumeEntry(source_block_id="agency-secret", org="Acme Analytics")
    )
    violations = check_visibility(make_ctx(demo_profile_dir, resume, ["internal-transfer"]))
    assert [v.path for v in violations] == ["sections[0].entries[1]"]


def test_passes_for_demo_without_visibility(demo_profile_dir: Path) -> None:
    assert check_visibility(make_ctx(demo_profile_dir, demo_resume(), ["agency"])) == []
