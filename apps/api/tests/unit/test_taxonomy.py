from __future__ import annotations

from pathlib import Path

import pytest

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
        "        keywords: [aa, bb, cc, dd, ee, ff]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RHAPTO_TAXONOMY_PATH", str(override))
    tax.taxonomy.cache_clear()
    try:
        assert [f.id for f in tax.taxonomy().fields] == ["only"]
    finally:
        tax.taxonomy.cache_clear()


def test_a_broken_or_missing_file_raises_taxonomy_error(tmp_path: Path) -> None:
    bad = tmp_path / "taxonomy.yaml"
    bad.write_text("fields: [{id: x}]", encoding="utf-8")
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(bad)
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(tmp_path / "missing.yaml")
