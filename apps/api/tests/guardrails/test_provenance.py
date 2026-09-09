from pathlib import Path

from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.guardrails.base import (
    GuardrailContext,
    iter_bullets,
    iter_entries,
    iter_entries_with_section,
    iter_texts,
)
from rhapto.engine.guardrails.provenance import check_provenance
from rhapto.profile.loader import load_profile


def make_ctx(demo_profile_dir: Path, resume=None, selection=None):  # type: ignore[no-untyped-def]
    profile = load_profile(demo_profile_dir)
    resume = resume or demo_resume()
    ids = frozenset(selection if selection is not None else profile.block_map())
    return GuardrailContext(
        resume=resume, blocks=profile.block_map(), selection_ids=ids, extract=demo_extract()
    )


def test_iterators_yield_paths() -> None:
    resume = demo_resume()
    assert [p for p, _ in iter_entries(resume)] == [
        "sections[0].entries[0]",
        "sections[1].entries[0]",
        "sections[2].entries[0]",
    ]
    paths = [p for p, _ in iter_bullets(resume)]
    assert paths[0] == "summary[0]" and "sections[0].entries[0].bullets[1]" in paths


def test_iter_texts_covers_bullets_and_entry_header_fields() -> None:
    resume = demo_resume()
    items = list(iter_texts(resume))
    # 1 summary bullet + (org, role, period + 2 bullets) + (org, title + 1 bullet) + 1 bullet
    assert len(items) == 10
    paths = [p for p, _, _ in items]
    assert paths[0] == "summary[0]"
    assert "sections[0].entries[0].period" in paths
    assert "sections[1].entries[0].title" in paths
    assert ("sections[0].entries[0].role", "Senior Data Program Manager", "acme-data-pm") in items
    assert all(text and block_id for _, text, block_id in items)


def test_iter_entries_with_section_yields_section_objects() -> None:
    resume = demo_resume()
    kinds = [section.kind for _, section, _ in iter_entries_with_section(resume)]
    assert kinds == ["experience", "projects", "credentials"]


def test_passes_for_valid_resume(demo_profile_dir: Path) -> None:
    assert check_provenance(make_ctx(demo_profile_dir)) == []


def test_flags_bullet_with_unknown_block(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].bullets.append(bullet("Invented thing.", "ghost-block"))
    violations = check_provenance(make_ctx(demo_profile_dir, resume))
    assert len(violations) == 1
    assert violations[0].path == "sections[0].entries[0].bullets[2]"
    assert violations[0].block_id == "ghost-block" and violations[0].severity == "error"


def test_flags_entry_with_unknown_block(demo_profile_dir: Path) -> None:
    resume = demo_resume()
    resume.sections[0].entries[0].source_block_id = "ghost"
    violations = check_provenance(make_ctx(demo_profile_dir, resume))
    assert [v.path for v in violations] == ["sections[0].entries[0]"]


def test_flags_block_outside_selection(demo_profile_dir: Path) -> None:
    violations = check_provenance(
        make_ctx(demo_profile_dir, selection={"acme-data-pm", "acme-migration"})
    )
    assert {v.block_id for v in violations} == {"side-llm-tool", "cred-pmp"}
    assert all("not in the selection" in v.message for v in violations)
