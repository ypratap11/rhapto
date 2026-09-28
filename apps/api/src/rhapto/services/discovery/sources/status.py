"""Is a job source actually able to bring anything in, and is it currently being refused?

Two questions the Settings page and the dashboard checklist both ask, answered in one place so they
cannot disagree about what "ready" means. `GET /settings/sources`' `runnable` field and
`ChecklistOut.job_sources` are the same function.

Both functions here are pure: no I/O, no session. The callers do the reading.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from datetime import datetime
from typing import Protocol

from rhapto.services.discovery.poller import PAUSED_MESSAGE
from rhapto.services.discovery.sources.base import SourceInfo

__all__ = ["PAUSED_MESSAGE", "SourceRow", "paused_as_of_last_run", "usable_source_ids"]


class SourceRow(Protocol):
    """The one field `usable_source_ids` reads off an `aggregators` row.

    A Protocol rather than the `Aggregator` model, so this module stays free of any database
    import and remains a pure function the checklist and the Settings page can both call.
    """

    @property
    def enabled(self) -> bool: ...


def usable_source_ids(
    rows: Mapping[str, SourceRow],
    credentialled: Collection[str],
    registry: Iterable[SourceInfo],
) -> set[str]:
    """Which sources could actually return a posting on the next poll.

    Follows the POLLER's rule, not the Settings page's display default, and the difference is a live
    defect this pass found rather than a nicety:

    - `GET /settings/sources` shows `enabled = KEYLESS_DEFAULT_ENABLED and not needs_key` for a user
      with **no** `aggregators` row at all.
    - `poller.build_specs` takes `enabled = [a for a in list_aggregators(...) if a.enabled]` and
      **returns early with board specs only when that list is empty**. A user with zero
      `aggregators` rows therefore polls no aggregators whatsoever.

    So a row must EXIST (`rows.get(name) is not None`), not merely default to on. That is why this
    reports `runnable = False` and `job_sources = False` for an account that has never opened
    Settings, which is the honest answer about what that account's next poll will fetch. Changing
    `build_specs` to honour the display default would start calling four external APIs for every
    such account, which is the owner's decision and is recorded in
    `docs/portal-backend-followups.md`, not made here.

    The credential check is the `resume_template` lesson applied to sources: a keyed source with no
    stored credentials is a row that says "enabled" describing something that cannot run -- the
    poller writes `NO_API_KEY_MESSAGE` and nothing can ever arrive.

    Deliberately excludes pause. Pause is scoped per `(source, board, search_id)`, so one boolean
    per source is lossy, and it needs the run history. This function answers "is setup done"; the
    Settings row's `paused` answers "is it working right now". A stated boundary, not a silent proxy.
    """
    usable = set()
    for info in registry:
        row = rows.get(info.name)
        if row is None or not row.enabled:
            continue
        if info.needs_key and info.name not in credentialled:
            continue
        usable.add(info.name)
    return usable


def paused_as_of_last_run(
    latest_errors: Iterable[tuple[str | None, datetime]], entry_updated_at: datetime | None
) -> bool:
    """Whether the poller is currently refusing this source, read from what the poller wrote.

    There is no `paused` column. Pause is decided at poll time by `poller._is_paused` from
    `consecutive_failures(...) >= PAUSE_AFTER` plus `entry_updated_at <= last.started_at`, scoped per
    `(user_id, source, board, search_id)`. This does NOT reimplement that streak rule, and it must
    not call `build_specs` to ask -- `build_specs` calls `derive_searches`, which WRITES saved
    searches, so a GET that invoked it would create rows.

    Instead it reads the poller's own output: when the poller refuses a paused spec it still records
    a run, `finish_run(run, found=0, new=0, error=PAUSED_MESSAGE)`. `PAUSED_MESSAGE` is imported
    from `poller` rather than restated, so a change to the wording moves both sides at once.

    The second clause is the same one `_is_paused` uses, and it is what removes a stale pause after
    a resume: re-saving the row (or `POST /settings/sources/{source}/resume`) bumps `updated_at`, so
    a PAUSED_MESSAGE run that started before that moment no longer counts.

    `latest_errors` is `(error, started_at)` for the newest run of each of this source's scopes. A
    source reads paused when ANY scope is being refused, because that is what the Resume control
    fixes: bumping `aggregators.updated_at` lifts every scope's pause at once.

    One documented inaccuracy: between the third failure and the next poll cycle no PAUSED_MESSAGE
    row exists yet, so a scope that *will* be refused reads as not paused. The lag is one cycle and
    self-correcting, and the row still shows the failing `last_run.error`. Hence the field's name:
    paused as of the last run.
    """
    if entry_updated_at is None:
        # No `aggregators` row behind this source, so there is nothing a human could save to lift a
        # pause -- and nothing polls it at all (see `usable_source_ids`).
        return False
    return any(
        error == PAUSED_MESSAGE and entry_updated_at <= started_at
        for error, started_at in latest_errors
    )
