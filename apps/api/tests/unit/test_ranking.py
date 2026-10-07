from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest

from rhapto.db.repositories.jobs import RECOMMENDED_FIT_FLOOR
from rhapto.engine.scoring import TITLE_MISS_CAP
from rhapto.services.ranking import arrange, company_key, title_key, wants_arrangement


@dataclass(frozen=True)
class Row:
    id: uuid.UUID
    company: str | None
    title: str | None
    best_fit: int | None = 80


def row(n: int, company: str | None, title: str | None, fit: int | None = 80) -> Row:
    return Row(uuid.UUID(int=n), company, title, fit)


def test_six_copies_of_one_posting_become_one_row_with_five_also_ids() -> None:
    rows = [row(n, "Acme", f"Senior Engineer (R{5800 + n})") for n in range(1, 7)]
    [only] = arrange(rows)
    assert only.index == 0  # the first (highest-ranked, newest on ties) copy represents the group
    assert only.also_ids == tuple(r.id for r in rows[1:])


def test_a_companys_third_row_sorts_after_the_others_first_two() -> None:
    rows = [
        row(1, "Shield AI", "A1"),
        row(2, "Shield AI", "A2"),
        row(3, "Shield AI", "A3"),
        row(4, "Other Co", "B1"),
        row(5, "Other Co", "B2"),
    ]
    assert [a.index for a in arrange(rows)] == [0, 1, 3, 4, 2]  # nothing removed, A3 moved back


def test_company_cap_only_reorders_rows_above_the_title_miss_cap() -> None:
    rows = [
        row(1, "Shield AI", "A1", 80),
        row(2, "Shield AI", "A2", 79),
        row(3, "Shield AI", "A3", 78),  # the third above-cap row of its company: deferred
        row(4, "Other Co", "B1", 60),
        row(5, "Zed Co", "C1", 30),  # at or below the cap: stays exactly where it is
        row(6, "Zed Co", "C2", None),  # unscored: stays
    ]
    # The deferred title match still precedes every capped and unscored row.
    assert [a.index for a in arrange(rows)] == [0, 1, 3, 2, 4, 5]


def test_capped_and_unscored_rows_of_one_company_are_never_moved() -> None:
    # Another company's row sits after the third Shield AI row: a cap applied to ALL rows would
    # defer that third row behind it; applied only above the cap, nothing moves.
    rows = [
        row(1, "Shield AI", "T1", 40),
        row(2, "Shield AI", "T2", 30),
        row(3, "Shield AI", "T3", None),
        row(4, "Other Co", "U1", 20),
        row(5, "Shield AI", "T4", 10),
        row(6, "Other Co", "U2", 5),
    ]
    assert [a.index for a in arrange(rows)] == [0, 1, 2, 3, 4, 5]


def test_missing_company_is_never_collapsed_or_capped() -> None:
    rows = [row(n, None, "Engineer") for n in range(1, 5)] + [
        row(5, "  ", "Engineer"),
        row(6, "", "X"),
    ]
    assert [a.index for a in arrange(rows)] == [0, 1, 2, 3, 4, 5]
    assert all(a.also_ids == () for a in arrange(rows))
    # A missing title is never collapsed either.
    assert [a.index for a in arrange([row(1, "Acme", None), row(2, "Acme", None)])] == [0, 1]


def test_same_title_at_different_companies_is_not_a_duplicate() -> None:
    assert len(arrange([row(1, "A Co", "Engineer"), row(2, "B Co", "Engineer")])) == 2


def test_normalisation_is_case_whitespace_and_requisition_suffix_only() -> None:
    assert company_key("  ACME   Corp ") == "acme corp"
    assert company_key("   ") is None and company_key(None) is None
    assert title_key("Senior  Engineer (R5803) ") == "senior engineer"
    assert title_key("Senior Engineer [REQ-12345]") == "senior engineer"
    assert title_key("Engineer (Remote)") == "engineer (remote)"  # no digits: not a requisition id
    assert title_key("Intern (Summer 2026)") == "intern (summer 2026)"
    assert title_key("(R5803)") is None
    dup = arrange([row(1, "Acme", "Senior  Engineer"), row(2, "ACME ", "senior engineer (R12345)")])
    assert len(dup) == 1 and dup[0].also_ids == (uuid.UUID(int=2),)


def test_arrange_never_reorders_rows_that_need_no_change() -> None:
    rows = [row(n, f"Company {n}", f"Role {n}") for n in range(1, 8)]
    assert [a.index for a in arrange(rows)] == list(range(7))


@pytest.mark.parametrize(
    ("ids_given", "sort", "recommended", "expected"),
    [
        (False, "relevance", False, True),  # the Jobs page default
        (False, "fit", True, True),  # the dashboard
        (False, "fit", False, False),
        (False, "newest", False, False),
        (True, "relevance", False, False),  # live search re-fetching its own results
        (True, "fit", True, False),
    ],
)
def test_wants_arrangement(ids_given: bool, sort: str, recommended: bool, expected: bool) -> None:
    assert wants_arrangement(ids_given=ids_given, sort=sort, recommended=recommended) is expected


def test_recommended_floor_matches_the_title_miss_cap() -> None:
    """db/ may not import engine/ (import-linter), so the floor is repeated there; this is the check."""
    assert RECOMMENDED_FIT_FLOOR == TITLE_MISS_CAP == 45
