from __future__ import annotations

from pathlib import Path

import pytest

from rhapto.engine.select import keyword_matches
from rhapto.services import taxonomy as tax

SPEC_FIELDS = [
    "engineering",
    "data-science",
    "product",
    "program-project-management",
    "design",
    "marketing",
    "sales",
    "finance",
    "operations",
    "people",
    "customer-success",
    "other",
]


def test_the_shipped_file_has_the_twelve_fields_from_the_spec() -> None:
    assert [f.id for f in tax.taxonomy().fields] == SPEC_FIELDS


def test_every_role_has_between_six_and_ten_keywords() -> None:
    for field in tax.taxonomy().fields:
        assert field.roles, f"{field.id} has no roles"
        assert field.themuse_category and field.adzuna_category
        for role in field.roles:
            assert 6 <= len(role.keywords) <= 10, f"{field.id}/{role.id}: {len(role.keywords)}"


def test_keywords_are_plain_strings() -> None:
    role = tax.find_role("engineering", "backend")
    assert role is not None
    assert all(type(k) is str for k in role.keywords)


def test_every_keyword_is_between_two_and_sixty_characters() -> None:
    for field in tax.taxonomy().fields:
        for role in field.roles:
            for keyword in role.keywords:
                assert 2 <= len(keyword) <= 60, f"{field.id}/{role.id}: {keyword!r}"


def test_role_ids_are_unique_within_a_field() -> None:
    for field in tax.taxonomy().fields:
        ids = [r.id for r in field.roles]
        assert len(ids) == len(set(ids))


def test_the_roles_named_in_the_spec_are_present() -> None:
    engineering = tax.find_field("engineering")
    assert engineering is not None
    assert {
        "Backend",
        "Frontend",
        "Full stack",
        "Mobile",
        "ML Engineering",
        "DevOps and SRE",
        "Security",
        "QA",
    } <= {r.name for r in engineering.roles}
    science = tax.find_field("data-science")
    assert science is not None
    assert {
        "Data Scientist",
        "Data Analyst",
        "Data Engineer",
        "Analytics Engineer",
        "ML Research",
    } <= {r.name for r in science.roles}
    ppm = tax.find_field("program-project-management")
    assert ppm is not None
    assert {
        "Technical Program Manager",
        "Program Manager",
        "Project Manager",
        "Delivery Lead",
        "Scrum Master",
    } <= {r.name for r in ppm.roles}


def test_lookups() -> None:
    assert tax.find_field(None) is None
    assert tax.find_field("nope") is None
    role = tax.find_role("engineering", "backend")
    assert role is not None and role.name == "Backend"
    assert tax.find_role("engineering", "nope") is None
    assert tax.find_role("nope", "backend") is None
    field, tpm = tax.roles_by_name()["technical program manager"]
    assert field.id == "program-project-management"
    assert tpm.id == "technical-program-manager"


def test_roles_by_name_puts_the_longest_name_first() -> None:
    names = list(tax.roles_by_name())
    assert names.index("technical program manager") < names.index("program manager")


def test_normalise_strips_punctuation_and_case() -> None:
    assert (
        tax.normalise("  Sr. Technical  Program-Manager, II ") == "sr technical program manager ii"
    )


def test_the_env_override_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "taxonomy.yaml"
    override.write_text(
        "fields:\n"
        "  - id: only\n"
        "    name: Only\n"
        "    themuse_category: Engineering\n"
        "    adzuna_category: IT Jobs\n"
        "    roles:\n"
        "      - id: one\n"
        "        name: One\n"
        "        keywords: [aa, bb, cc, dd, ee, ff]\n"
        "        titles: [one engineer]\n"
        "        exclude_titles: [intern]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RHAPTO_TAXONOMY_PATH", str(override))
    tax.taxonomy.cache_clear()
    try:
        assert [f.id for f in tax.taxonomy().fields] == ["only"]
        role = tax.taxonomy().fields[0].roles[0]
        assert role.titles == ["one engineer"] and role.exclude_titles == ["intern"]
    finally:
        tax.taxonomy.cache_clear()


def test_importing_the_module_never_raises_even_from_a_shallow_anchor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for the image-boot crash: the old code computed the repo-root candidate eagerly
    at import time as `Path(__file__).resolve().parents[5]`. Inside the Docker image the module
    sits at a shallower path than that assumes (`/app/rhapto/services/taxonomy.py` has only four
    parents), so merely importing the module raised `IndexError: 5` and the api/worker containers
    crashed on startup before ever asking for the taxonomy.

    Re-importing the already-imported module cannot reproduce an import-time crash, so this
    exercises the equivalent condition directly: with the module's anchor patched to a path as
    shallow as the image's, resolving *where* the taxonomy would come from must not raise, and
    the missing-checkout case must fall back to the (non-existent, here) image path rather than
    blowing up -- the corresponding TaxonomyError only appears once someone actually loads it.
    """
    monkeypatch.setattr(tax, "_MODULE_FILE", Path("/app/rhapto/services/taxonomy.py"))
    monkeypatch.delenv("RHAPTO_TAXONOMY_PATH", raising=False)
    assert tax._repo_checkout_path() is None
    assert tax.taxonomy_path() == tax.IMAGE_PATH
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(tax.taxonomy_path())


def test_a_broken_or_missing_file_raises_taxonomy_error(tmp_path: Path) -> None:
    bad = tmp_path / "taxonomy.yaml"
    bad.write_text("fields: [{id: x}]", encoding="utf-8")
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(bad)
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(tmp_path / "missing.yaml")


def test_every_shipped_role_has_non_empty_titles() -> None:
    for field in tax.taxonomy().fields:
        for role in field.roles:
            assert role.titles, f"{field.id}/{role.id} has no titles"
            assert all(p.strip() for p in [*role.titles, *role.exclude_titles]), role.id


def test_no_exclusion_contradicts_its_own_titles() -> None:
    """An exclusion that matches one of the role's OWN phrases would make that phrase unmatchable
    (e.g. excluding "test" from a role whose title is "test engineer")."""
    for field in tax.taxonomy().fields:
        for role in field.roles:
            for exclusion in role.exclude_titles:
                for phrase in role.titles:
                    assert not keyword_matches(exclusion, phrase), (
                        f"{field.id}/{role.id}: exclusion {exclusion!r} matches title {phrase!r}"
                    )


def test_the_roles_the_spec_gives_as_examples_ship_with_those_lists() -> None:
    qa = tax.find_role("engineering", "qa")
    assert qa is not None
    assert {
        "QA engineer",
        "QA analyst",
        "quality assurance",
        "quality engineer",
        "test engineer",
        "SDET",
        "test automation engineer",
        "software tester",
    } <= set(qa.titles)
    assert {
        "mechanical",
        "flight",
        "hardware",
        "manufacturing",
        "supplier",
        "structural",
        "electrical",
        "chemical",
        "civil",
        "construction",
        "clinical",
        "food safety",
    } <= set(qa.exclude_titles)

    tpm = tax.find_role("program-project-management", "technical-program-manager")
    assert tpm is not None
    assert {"technical program manager", "TPM", "program manager"} <= set(tpm.titles)
    assert {
        "construction",
        "clinical",
        "nursing",
        "facilities",
        "real estate",
        "manufacturing",
    } <= set(tpm.exclude_titles)

    project = tax.find_role("program-project-management", "project-manager")
    assert project is not None
    assert {"project manager", "project lead", "project coordinator", "delivery manager"} <= set(
        project.titles
    )
    assert {
        "construction",
        "civil",
        "electrical",
        "mechanical",
        "field",
        "site",
        "clinical",
    } <= set(project.exclude_titles)

    scrum = tax.find_role("program-project-management", "scrum-master")
    assert scrum is not None
    assert {"scrum master", "agile coach", "agile delivery lead"} <= set(scrum.titles)


def test_titles_and_exclusions_are_optional_in_a_custom_file(tmp_path: Path) -> None:
    """A RHAPTO_TAXONOMY_PATH file written before these fields existed must still load."""
    legacy = tmp_path / "taxonomy.yaml"
    legacy.write_text(
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
    role = tax.load_taxonomy(legacy).fields[0].roles[0]
    assert role.titles == [] and role.exclude_titles == []
