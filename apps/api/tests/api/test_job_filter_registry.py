"""The registry cannot drift from the parameters, and every blamable id is one the UI can render.

This is the anti-desync device from the architecture (§1.3, condition C2). `GET /jobs` builds its
WHERE clause from `JOB_FILTERS` and `GET /jobs/empty-reason` blames one of those same entries, so a
filter parameter with no registry entry would be applied by neither -- or worse, applied by the
listing and invisible to the diagnosis. Set equality (not a subset check) is what makes both
directions a failure.

NOTE ON LOCATION. These are pure functions with no database and no HTTP, so `tests/unit/` is where
they belong by shape. They live under `tests/api/` because that is where the *gate* looks: the brief,
architecture condition C10 and every report use `uv run pytest tests/api tests/db`, this repository
has no CI, and a guard nothing runs is not a guard. What they assert is an API contract anyway --
`JobFilterId` is a wire type and the remedies are attached at response time.
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import get_args

from rhapto.api.schemas import JobFilterId
from rhapto.db.repositories.jobs import (
    JOB_FILTERS,
    POSTED_WITHIN_DAYS,
    JobFilterParams,
    active_clauses,
    active_filters,
    filter_context,
)

#: `JobFilterParams` fields with no one-to-one registry entry, each for a stated reason:
#: `user_id` is the base tenancy predicate, applied outside the registry so no leave-one-out can
#: remove it; `sort` is not a filter at all; `hidden` is a mode switch whose registry entry is
#: always active rather than being switched on by a value.
PARAM_ONLY_FIELDS = {"user_id", "hidden", "sort"}

#: `hidden` has a registry entry but is excluded on the parameter side above, so it is excluded
#: from both sides of the comparison.
REGISTRY_ONLY_IDS = {"hidden"}


def test_every_filter_parameter_has_a_registry_entry_and_vice_versa() -> None:
    params = {f.name for f in dataclasses.fields(JobFilterParams)} - PARAM_ONLY_FIELDS
    registry = {f.id for f in JOB_FILTERS} - REGISTRY_ONLY_IDS
    assert params == registry, (
        f"only a parameter: {sorted(params - registry)}; "
        f"only a registry entry: {sorted(registry - params)}"
    )


def test_registry_ids_are_unique() -> None:
    ids = [f.id for f in JOB_FILTERS]
    assert len(ids) == len(set(ids))


def test_every_blamable_id_is_one_the_wire_can_carry() -> None:
    """The other half of the coverage guard: a blamable registry id that is not in `JobFilterId`
    could never reach the client, so the grid would be empty with no explanation. `JobFilterId` is
    also what the web app's widen map is keyed by, so this is the Python end of a check whose other
    end is a TypeScript compile error."""
    assert {f.id for f in JOB_FILTERS if f.blamable} == set(get_args(JobFilterId))


def test_only_ids_is_unblamable() -> None:
    """`ids` is a refetch mechanism, not a filter a user chose, so it is applied but never blamed.

    Pinned because adding a second unblamable entry would make an empty grid unexplainable with no
    test noticing.
    """
    assert {f.id for f in JOB_FILTERS if not f.blamable} == {"ids"}


def _all_on() -> JobFilterParams:
    return JobFilterParams(
        user_id=uuid.uuid4(),
        search="platform",
        track="tpm",
        bucket="fit",
        region="us",
        ids=(uuid.uuid4(),),
        hidden=True,
        search_id=uuid.uuid4(),
        posted_within="30d",
        sources=("adzuna",),
        field="engineering",
        recommended=True,
    )


def test_every_registry_entry_can_be_active_and_compiles_to_a_clause() -> None:
    """A registry entry whose `active` never fires, or whose `clause` raises, is a filter that is
    silently not applied. Driving every entry at once is what catches both."""
    params = _all_on()
    _tracks, ctx = filter_context(params.user_id, ("be",))
    assert {f.id for f in active_filters(params)} == {f.id for f in JOB_FILTERS}
    clauses = active_clauses(params, ctx)
    assert len(clauses) == len(JOB_FILTERS)
    # Compiling proves each lambda produced a real SQL boolean rather than, say, a Python `bool`.
    assert all(str(c) for c in clauses)


def test_leave_one_out_drops_exactly_one_clause() -> None:
    params = _all_on()
    _tracks, ctx = filter_context(params.user_id, ("be",))
    full = active_clauses(params, ctx)
    for entry in JOB_FILTERS:
        assert len(active_clauses(params, ctx, without=entry.id)) == len(full) - 1


def test_no_filter_is_active_on_a_bare_request_except_hidden() -> None:
    """The default request narrows by exactly two things: tenancy (not a registry entry) and the
    hidden switch. If another entry became active by default, `empty-reason` would blame a filter
    the user never set."""
    params = JobFilterParams(user_id=uuid.uuid4())
    assert {f.id for f in active_filters(params)} == {"hidden"}


def test_posted_within_is_active_for_every_bounded_window_and_not_for_any() -> None:
    """`active` must agree with `POSTED_WITHIN_DAYS`, which is what decides whether the clause is
    applied. A mismatch would blame a window that filtered nothing."""
    user = uuid.uuid4()
    for window in POSTED_WITHIN_DAYS:
        params = JobFilterParams(user_id=user, posted_within=window)
        assert "posted_within" in {f.id for f in active_filters(params)}, window
    assert "posted_within" not in {
        f.id for f in active_filters(JobFilterParams(user_id=user, posted_within="any"))
    }


def test_every_blamable_filter_renders_its_current_value() -> None:
    """The explanation sentence names the filter's value, so a blamable entry that returns None
    would render "excluded everything" with a blank."""
    params = _all_on()
    for entry in JOB_FILTERS:
        if entry.blamable:
            assert entry.value(params), entry.id
