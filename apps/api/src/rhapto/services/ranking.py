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


def company_key(company: str | None) -> str | None:
    """Lower-case, whitespace collapsed; None for a missing or blank company."""
    if not company:
        return None
    key = _WS.sub(" ", company).strip().lower()
    return key or None


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
) -> list[Arranged]:
    """C1 then C2 over an already-ordered sequence.

    C1: rows with the same normalised company and title collapse to the first of them, which
    carries the others' ids. C2 (owner decision, plan review I-1): among the rows ABOVE the
    title-miss cap (`best_fit > cap`) only, a company's rows after its first `per_company` are
    moved behind the other above-cap rows; they are written back into the same positions the
    above-cap rows already occupied, so a deferred title match still precedes every row at or
    below the cap and every unscored row, and those rows keep their plain order exactly. Nothing is
    removed. A row with no company or no title is never collapsed, and a row with no company is
    never capped.
    """
    first_of: dict[tuple[str, str], int] = {}
    order: list[int] = []
    also: dict[int, list[uuid.UUID]] = {}
    for position, item in enumerate(items):
        company, title = company_key(item.company), title_key(item.title)
        if company is not None and title is not None:
            representative = first_of.get((company, title))
            if representative is not None:
                also[representative].append(item.id)
                continue
            first_of[(company, title)] = position
        order.append(position)
        also[position] = []
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


def wants_arrangement(*, ids_given: bool, sort: str, recommended: bool) -> bool:
    """`GET /jobs` arranges for the Jobs page default (relevance) and the dashboard (recommended,
    which sorts by fit), and NEVER for an `ids=` request: live search re-fetches its own results
    that way and must get every row it asked for."""
    return not ids_given and (sort == "relevance" or recommended)


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
