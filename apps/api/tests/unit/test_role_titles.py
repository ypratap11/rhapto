from __future__ import annotations

import logging
from pathlib import Path
from typing import NoReturn

import pytest

from rhapto.engine.scoring import RoleTitles, title_match
from rhapto.models.profile.tracks import Track
from rhapto.services import taxonomy as tax
from rhapto.services.scoring import role_titles_for


def _track(track_id: str, **extra: str) -> Track:
    return Track(id=track_id, name=track_id, resume_base="b", **extra)  # type: ignore[arg-type]


def test_a_role_track_resolves_to_the_shipped_titles_and_exclusions() -> None:
    resolved = role_titles_for([_track("qa", field="engineering", role="qa")])
    role = resolved["qa"]
    assert isinstance(role, RoleTitles)
    assert "QA engineer" in role.titles and "flight" in role.exclude


def test_hand_written_tracks_are_not_resolved() -> None:
    assert role_titles_for([_track("manual")]) == {}
    assert role_titles_for([_track("field-only", field="engineering")]) == {}


def test_stale_role_and_taxonomy_failure_fall_back_per_run(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # A role id removed from the taxonomy after the track row was written.
    stale = _track("stale", field="engineering", role="removed-from-the-taxonomy")
    assert role_titles_for([stale]) == {}

    # The taxonomy cannot be loaded: every track falls back, scoring is not stopped, ONE error is logged.
    def boom() -> NoReturn:
        raise tax.TaxonomyError("cannot read the taxonomy")

    monkeypatch.setattr(tax, "taxonomy", boom)
    tracks = [
        _track("a", field="engineering", role="qa"),
        _track("b", field="engineering", role="backend"),
    ]
    with caplog.at_level(logging.ERROR, logger="rhapto.services.scoring"):
        assert role_titles_for(tracks) == {}
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1 and "legacy blend" in errors[0].getMessage()


def _shipped(field: str, role: str) -> RoleTitles:
    found = tax.find_role(field, role)
    assert found is not None
    return RoleTitles(titles=tuple(found.titles), exclude=tuple(found.exclude_titles))


PPM = "program-project-management"
NOT_A_PROGRAM_MANAGER = [
    "Marketing Program Manager",
    "Partner Program Manager",
    "HR Program Manager",
    "Community Program Manager",
    "Sales Enablement Program Manager",
    "Program Manager, Government Programs",
    "Program Manager, Construction",
]
NOT_QA = [
    "Flight Test Engineer",
    "Mechanical Test Engineer",
    "Supplier Quality Engineer",
    "Systems Test Engineer",
    "Integration and Test Engineer",
    "Test Engineer, Satellites",
    "QA Specialist, GMP",
    "Quality Engineer - Medical Devices",  # plural: the exclusion list carries both forms
    "Quality Engineer, Batteries",
    "Quality Assurance Associate - Pharmaceuticals",
]


@pytest.mark.parametrize("role", ["technical-program-manager", "program-manager"])
def test_shipped_program_roles_reject_other_business_functions(role: str) -> None:
    lists = _shipped(PPM, role)
    for title in NOT_A_PROGRAM_MANAGER:
        assert title_match(title, lists) is None, title
    assert title_match("Program Manager, Operations", _shipped(PPM, "program-manager")) is not None
    assert title_match(
        "Technical Program Manager, Platform", _shipped(PPM, "technical-program-manager")
    )


def test_shipped_lists_on_the_reviewed_titles() -> None:
    qa = _shipped("engineering", "qa")
    for title in NOT_QA:
        assert title_match(title, qa) is None, title
    for title in (
        "Senior QA Engineer",
        "Software Test Engineer",
        "Software Development Engineer in Test",
    ):
        assert title_match(title, qa) is not None, title

    sre = _shipped("engineering", "devops-sre")
    for title in (
        "Software Engineer, Infrastructure",
        "Senior Software Engineer - Platform",
        "Site Reliability Engineer",
    ):
        assert title_match(title, sre) is not None, title
    for title in (
        "Production Engineer, Injection Molding",
        "Platform Product Manager",
        "Program Manager, Platform",
    ):
        assert title_match(title, sre) is None, title

    tpm_product = _shipped("product", "technical-product-manager")
    for title in ("Product Manager, Platform", "Senior Product Manager - Developer Platform"):
        assert title_match(title, tpm_product) is not None, title


def test_a_role_with_no_titles_is_not_resolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    custom = tmp_path / "taxonomy.yaml"
    custom.write_text(
        "fields:\n"
        "  - id: only\n"
        "    name: Only\n"
        "    themuse_category: Engineering\n"
        "    adzuna_category: IT Jobs\n"
        "    roles:\n"
        "      - id: one\n"
        "        name: One\n"
        "        keywords: [aa, bb, cc, dd, ee, ff]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RHAPTO_TAXONOMY_PATH", str(custom))
    tax.taxonomy.cache_clear()
    try:
        assert role_titles_for([_track("t", field="only", role="one")]) == {}
    finally:
        tax.taxonomy.cache_clear()
