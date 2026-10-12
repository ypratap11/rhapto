from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from rhapto.db.repositories.jobs import RECOMMENDED_FIT_FLOOR
from rhapto.engine.scoring import TITLE_MISS_CAP
from rhapto.services.ranking import (
    arrange,
    brand_key,
    company_key,
    relevance_key,
    title_key,
    wants_collapse,
    wants_company_spread,
)


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


def test_normalisation_is_case_whitespace_legal_suffix_and_requisition_suffix_only() -> None:
    assert company_key("  ACME   Corp ") == "acme"  # intentional: "Corp" is a legal suffix now
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
    ("ids_given", "expected"),
    [
        (False, True),  # every list collapses duplicates
        (True, False),  # live search re-fetching its own results gets every row it asked for
    ],
)
def test_wants_collapse(ids_given: bool, expected: bool) -> None:
    assert wants_collapse(ids_given=ids_given) is expected


@pytest.mark.parametrize(
    ("sort", "recommended", "expected"),
    [
        ("relevance", False, True),  # the Jobs page default
        ("fit", True, True),  # the dashboard
        ("fit", False, False),
        ("newest", False, False),
    ],
)
def test_wants_company_spread(sort: str, recommended: bool, expected: bool) -> None:
    assert wants_company_spread(sort=sort, recommended=recommended) is expected


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Acme, Inc.", "ACME LLC"),
        ("Acme", "Acme Inc"),
        ("Amazon.com", "Amazon"),
        ("Acme Corporation", "acme"),
        # Pinned as-is (ruling 2026-10-11): a trailing "Ag" or "Co" is stripped like any legal suffix.
        # No real company in the data needed them kept, so behaviour stays until a failing case shows up.
        ("Acme Ag", "Acme"),
        ("Foo Co", "Foo"),
    ],
)
def test_legal_suffix_and_dotcom_noise_collapse(a: str, b: str) -> None:
    assert company_key(a) == company_key(b)


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Amazon Web Services", "Amazon"),
        ("Amazon.com Services LLC", "Amazon"),  # owner confirmed: stays separate from "Amazon"
        ("X Labs", "X"),
        ("Acme Group", "Acme"),
    ],
)
def test_extra_words_do_not_collapse(a: str, b: str) -> None:
    assert company_key(a) != company_key(b)


def test_company_key_never_empty() -> None:
    assert company_key("Co") == "co"
    assert company_key("Inc.") == "inc"
    assert company_key(".com") == ".com"


def test_arrange_can_skip_company_spread() -> None:
    rows = [
        row(1, "C1", "T1", 90),
        row(2, "C1", "T2", 89),
        row(3, "C1", "T3", 88),
        row(4, "C1", "T4", 87),
        row(5, "Other", "U1", 86),
    ]
    assert [a.index for a in arrange(rows, spread_companies=False)] == [0, 1, 2, 3, 4]
    assert [a.index for a in arrange(rows)] == [0, 1, 4, 2, 3]


def test_recommended_floor_matches_the_title_miss_cap() -> None:
    """db/ may not import engine/ (import-linter), so the floor is repeated there; this is the check."""
    assert RECOMMENDED_FIT_FLOOR == TITLE_MISS_CAP == 45


@dataclass(frozen=True)
class Scored:
    id: uuid.UUID
    best_fit: int | None
    posted_at: datetime | None
    discovered_at: datetime


def test_relevance_key_orders_by_decayed_fit_then_recency_then_id() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)

    def at(days: int) -> datetime:
        return now - timedelta(days=days)

    jobs = [
        Scored(uuid.UUID(int=1), 90, at(0), at(0)),
        Scored(uuid.UUID(int=2), 80, at(10), at(10)),  # 80 - 10 * 0.2 = 78.0
        Scored(uuid.UUID(int=3), 78, at(0), at(0)),  # 78.0: ties with 2, the newer one first
        Scored(uuid.UUID(int=4), 85, at(200), at(200)),  # past the 90-day cap: 85 - 18 = 67.0
        Scored(uuid.UUID(int=5), 67, at(0), at(0)),  # 67.0: ties with 4, newer first
        Scored(uuid.UUID(int=6), None, None, at(1)),  # unscored: last, newest first
        Scored(uuid.UUID(int=7), None, at(5), at(5)),
        Scored(uuid.UUID(int=8), None, at(5), at(5)),  # same timestamp as 7: id decides
    ]
    ordered = sorted(jobs, key=lambda j: relevance_key(j, now))
    assert [j.id.int for j in ordered] == [1, 3, 2, 5, 4, 6, 7, 8]


def test_a_dateless_posting_is_judged_by_when_it_was_discovered() -> None:
    now = datetime(2026, 10, 7, 12, tzinfo=UTC)
    fresh = Scored(uuid.UUID(int=1), 70, None, now - timedelta(days=0))
    stale = Scored(uuid.UUID(int=2), 70, None, now - timedelta(days=60))
    assert relevance_key(fresh, now) < relevance_key(stale, now)


# --- loose company match in C1 (dedupe) -------------------------------------------------------

T = "Sr. Technical Program Manager"


def groups(companies: list[str | None], title: str | None = T) -> list[tuple[int, tuple[int, ...]]]:
    rows = [row(n + 1, c, title) for n, c in enumerate(companies)]
    by_id = {r.id: n for n, r in enumerate(rows)}
    return [(a.index, tuple(by_id[i] for i in a.also_ids)) for a in arrange(rows)]


def test_brand_key_strips_dotcom_from_every_token() -> None:
    assert brand_key("Amazon.com Services LLC") == ("amazon", "services")
    assert brand_key("Amazon.com") == ("amazon",)
    assert brand_key(".com") == (".com",)
    assert brand_key(None) is None
    assert brand_key("   ") is None


def test_company_key_is_untouched_by_brand_key() -> None:
    assert company_key("Amazon.com Services LLC") == "amazon.com services"


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Amazon", "Amazon.com Services LLC"),
        ("Amazon.com Services LLC", "Amazon"),
        ("Amazon.com", "Amazon"),
        ("Acme Labs Inc", "Acme Labs"),
        ("Delta", "Delta Dental"),
        ("United", "United"),
    ],
)
def test_loose_company_match_collapses(a: str, b: str) -> None:
    assert groups([a, b]) == [(0, (1,))]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Delta Dental", "Delta Air Lines"),
        ("Amaz", "Amazon"),
        ("Amazon", "Amaz"),
        ("United", "United Airlines"),
        ("American", "American Express"),
    ],
)
def test_loose_company_match_refuses(a: str, b: str) -> None:
    assert groups([a, b]) == [(0, ()), (1, ())]


def test_loose_match_needs_the_same_title() -> None:
    rows = [row(1, "Amazon", T), row(2, "Amazon.com Services LLC", "Data Engineer")]
    assert [a.index for a in arrange(rows)] == [0, 1]


def test_loose_match_never_collapses_missing_company_or_title() -> None:
    assert groups([None, None]) == [(0, ()), (1, ())]
    assert groups(["Amazon", "Amazon Web Services"], title=None) == [(0, ()), (1, ())]


@pytest.mark.parametrize(
    "order", [["Amazon", "Amazon.com Services LLC"], ["Amazon.com Services LLC", "Amazon"]]
)
def test_amazon_case_collapses_in_either_arrival_order(order: list[str]) -> None:
    assert groups(order) == [(0, (1,))]  # whichever arrived first represents


def test_three_way_join_follows_input_order() -> None:
    assert groups(["Amazon", "Amazon.com Services LLC", "Amazon Web Services"]) == [(0, (1, 2))]


def test_bare_brand_representative_absorbs_both_longer_names() -> None:
    assert groups(["Delta", "Delta Dental", "Delta Air Lines"]) == [(0, (1, 2))]


def test_bare_brand_arriving_last_joins_only_the_earliest_group() -> None:
    assert groups(["Delta Dental", "Delta Air Lines", "Delta"]) == [(0, (2,)), (1, ())]


def test_arrange_stays_near_linear_for_many_distinct_companies() -> None:
    rows = [row(n + 1, f"Company{n}", T) for n in range(5000)]
    started = time.perf_counter()
    result = arrange(rows)
    assert time.perf_counter() - started < 0.5
    assert len(result) == 5000
