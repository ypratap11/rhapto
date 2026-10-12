"""Ordering helpers shared by `GET /jobs` and `rhapto rank-preview`.

Pure Python: no session, no clock except what the caller passes. `arrange` is applied after
`repo.list_jobs` has ordered the rows; it never re-sorts, so the order it receives is "the request's
own ordering" and the first copy of a duplicate group is the one that ranks highest (ties already
go to the newest, because both orderings break ties by recency).
"""

from __future__ import annotations

import re
import uuid
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from rhapto.db.repositories.jobs import RECENCY_DECAY, RECENCY_DECAY_CAP_DAYS
from rhapto.engine.scoring import TITLE_MISS_CAP

#: How many rows of one company may sit among the top of the list before the rest sort after them.
PER_COMPANY_TOP = 2

_WS = re.compile(r"\s+")
#: A trailing requisition id such as "(R5803)" or "[REQ-12345]": a bracket, up to four letters, an
#: optional separator, at least three digits. "(Remote)" and "(Summer 2026)" are not stripped.
_TRAILING_REQ = re.compile(r"\s*[(\[]\s*[A-Za-z]{0,4}[-_ ]?\d{3,}\s*[)\]]\s*$")


class Rankable(Protocol):
    @property
    def id(self) -> uuid.UUID: ...
    @property
    def company(self) -> str | None: ...
    @property
    def title(self) -> str | None: ...
    @property
    def best_fit(self) -> int | None: ...


@dataclass(frozen=True)
class Arranged:
    #: Position of the representative row in the sequence passed to `arrange`.
    index: int
    #: The other copies of the same posting, in input order. Computed, never stored.
    also_ids: tuple[uuid.UUID, ...]


#: Legal-form words dropped from the END of a company name so "Acme, Inc." and "ACME LLC" meet.
#: Only these: "Services", "Group", "Labs" and other real words are never stripped.
LEGAL_SUFFIXES = frozenset(
    {
        "inc",
        "incorporated",
        "llc",
        "l.l.c",
        "ltd",
        "limited",
        "corp",
        "corporation",
        "co",
        "gmbh",
        "plc",
        "ag",
        "sa",
        "s.a",
        "bv",
        "nv",
        "pty",
        "lp",
        "llp",
    }
)


def company_key(company: str | None) -> str | None:
    """Lower-case, whitespace collapsed, trailing legal suffixes and a ".com" tail removed.

    Never empty for a non-blank name ("Inc." stays "inc"); None for a missing or blank company.
    """
    if not company:
        return None
    tokens = [t.rstrip(",.") or t for t in _WS.sub(" ", company).strip().lower().split(" ") if t]
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    if tokens:
        last = tokens[-1]
        if last.endswith(".com") and len(last) > len(".com"):
            tokens[-1] = last[: -len(".com")]
    return " ".join(tokens) or None


#: Single-word brands too generic to stand for a longer company name: "United" must not absorb
#: "United Airlines". Equal brands still match.
GENERIC_HEADS = frozenset(
    {
        "the",
        "american",
        "united",
        "national",
        "general",
        "first",
        "global",
        "international",
        "new",
        "great",
        "bank",
        "capital",
        "city",
        "state",
        "university",
        "co",
    }
)


def brand_key(company: str | None) -> tuple[str, ...] | None:
    """Tokens of `company_key` with ".com" removed from the end of every token (a lone ".com" stays).

    "Amazon.com Services LLC" -> ("amazon", "services"). None for a missing or blank company.
    """
    key = company_key(company)
    if key is None:
        return None
    return tuple(
        t[: -len(".com")] if t.endswith(".com") and len(t) > len(".com") else t
        for t in key.split(" ")
    )


def _brands_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Equal, or one is a whole-word (token) prefix of the other unless that prefix is a generic head."""
    if a == b:
        return True
    short, long = (a, b) if len(a) < len(b) else (b, a)
    if len(short) == 1 and short[0] in GENERIC_HEADS:
        return False
    return long[: len(short)] == short


def title_key(title: str | None) -> str | None:
    """Lower-case, whitespace collapsed, trailing requisition ids stripped; None when nothing is left."""
    if not title:
        return None
    text = _WS.sub(" ", title).strip()
    while True:
        stripped = _TRAILING_REQ.sub("", text)
        if stripped == text:
            break
        text = stripped
    return text.lower() or None


def arrange(
    items: Sequence[Rankable],
    *,
    per_company: int = PER_COMPANY_TOP,
    cap: int = TITLE_MISS_CAP,
    spread_companies: bool = True,
) -> list[Arranged]:
    """C1 then C2 over an already-ordered sequence.

    C1: rows with the same title_key and a loosely matching company (`brand_key` tokens equal, or one a
    whole-word prefix of the other, see `_brands_match`) collapse to the first of them, which carries
    the others' ids. A row joins the earliest-created group whose REPRESENTATIVE's brand matches, so
    the result is order-dependent but deterministic: [Delta, Delta Dental, Delta Air Lines] is one
    row, [Delta Dental, Delta Air Lines, Delta] is two (Delta joins Delta Dental). Likewise
    [Amazon.com Services LLC, Amazon Web Services, Amazon] is two cards (Amazon joins the first).

    C2 (owner decision, plan review I-1): among the rows ABOVE the title-miss cap (`best_fit > cap`) only,
    a company's rows after its first `per_company` are moved behind the other above-cap rows; they are written
    back into the same positions the
    above-cap rows already occupied, so a deferred title match still precedes every row at or
    below the cap and every unscored row, and those rows keep their plain order exactly. Nothing is
    removed. A row with no company or no title is never collapsed, and a row with no company is
    never capped. With `spread_companies=False` only C1 runs.
    """
    # Representative positions, keyed with the title_key. `exact`: a representative's whole brand.
    # `prefix_of`: every proper token prefix of a representative's brand, earliest position kept.
    exact: dict[tuple[str, tuple[str, ...]], int] = {}
    prefix_of: dict[tuple[str, tuple[str, ...]], int] = {}
    order: list[int] = []
    also: dict[int, list[uuid.UUID]] = {}
    for position, item in enumerate(items):
        brand, title = brand_key(item.company), title_key(item.title)
        if brand is not None and title is not None:
            hits: list[int] = []
            if (pos := exact.get((title, brand))) is not None:
                hits.append(pos)
            single_generic = len(brand) == 1 and brand[0] in GENERIC_HEADS
            if not single_generic and (pos := prefix_of.get((title, brand))) is not None:
                hits.append(pos)  # this brand is a prefix of an existing representative's
            for i in range(1, len(brand)):  # an existing representative is a prefix of this brand
                if i == 1 and brand[0] in GENERIC_HEADS:
                    continue
                if (pos := exact.get((title, brand[:i]))) is not None:
                    hits.append(pos)
            if hits:
                also[min(hits)].append(item.id)
                continue
            exact[(title, brand)] = position
            for i in range(1, len(brand)):
                prefix_of.setdefault((title, brand[:i]), position)
        order.append(position)
        also[position] = []
    if spread_companies:
        slots = [
            slot
            for slot, position in enumerate(order)
            if (fit := items[position].best_fit) is not None and fit > cap
        ]
        seen: Counter[str] = Counter()
        front: list[int] = []
        back: list[int] = []
        for slot in slots:
            position = order[slot]
            company = company_key(items[position].company)
            if company is None:
                front.append(position)
                continue
            seen[company] += 1
            (front if seen[company] <= per_company else back).append(position)
        for slot, position in zip(slots, [*front, *back], strict=True):
            order[slot] = position
    return [Arranged(position, tuple(also[position])) for position in order]


def wants_collapse(*, ids_given: bool) -> bool:
    """`GET /jobs` collapses duplicate postings on every list, and NEVER for an `ids=` request:
    live search re-fetches its own results that way and must get every row it asked for."""
    return not ids_given


def wants_company_spread(*, sort: str, recommended: bool) -> bool:
    """The per-company cap (C2) applies to the Jobs page default (relevance) and the dashboard
    (recommended, which sorts by fit) only; newest and plain fit keep their strict order. Callers
    never reach this for an `ids=` request (see `wants_collapse`)."""
    return sort == "relevance" or recommended


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_MICRO = timedelta(microseconds=1)


class Scored(Protocol):
    @property
    def id(self) -> uuid.UUID: ...
    @property
    def best_fit(self) -> int | None: ...
    @property
    def posted_at(self) -> datetime | None: ...
    @property
    def discovered_at(self) -> datetime: ...


def relevance_key(job: Scored, now: datetime) -> tuple[bool, float, int, uuid.UUID]:
    """The sort key of `sort=relevance`, so the preview can order in-memory scores.

    Ascending order of this key is the SQL order in `db/repositories/jobs.py` (`list_jobs`):
    `best_fit - least(age_days, 90) * 0.2` descending with NULLs last, then
    `coalesce(posted_at, discovered_at)` descending, then `id`. The SQL stays the production path;
    `tests/unit/test_relevance_parity.py` fails if either side drifts.
    """
    moment = job.posted_at or job.discovered_at
    micros = (moment - _EPOCH) // _MICRO
    if job.best_fit is None:
        return (True, 0.0, -micros, job.id)
    age_days = (now - moment).total_seconds() / 86400.0
    decayed = job.best_fit - min(age_days, RECENCY_DECAY_CAP_DAYS) * RECENCY_DECAY
    return (False, -decayed, -micros, job.id)
