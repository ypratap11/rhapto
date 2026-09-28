"""Is a job source actually able to bring anything in, and is it currently being refused?

Two questions the Settings page and the dashboard checklist both ask, answered in one place so they
cannot disagree about what "set up" means. `usable_source_ids` backs BOTH
`GET /settings/sources`' `configured` field and `ChecklistOut.job_sources` -- one function, two
surfaces. It is not what backs `runnable`, which is `configured and not paused` and is therefore a
claim about the next poll rather than about setup (architecture §12.1).

Both functions here are pure: no I/O, no session. The callers do the reading.
"""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from datetime import datetime
from typing import Protocol

from rhapto.services.discovery.poller import PAUSED_MESSAGE
from rhapto.services.discovery.sources import aggregator_sources
from rhapto.services.discovery.sources.base import SourceInfo

__all__ = [
    "PAUSED_MESSAGE",
    "SourceRow",
    "keyless_source_names",
    "paused_as_of_last_run",
    "usable_source_ids",
]


def keyless_source_names() -> tuple[str, ...]:
    """Aggregator sources that need no credentials, so they can be switched on for a new account.

    The seed list for `services.accounts.ensure_account`. Derived from the registry rather than
    written down, so a keyless source added to `aggregator_sources()` is seeded for new accounts
    without anyone remembering to update a list -- and a source that starts needing a key drops out of
    it on the same edit that sets `needs_key`.
    """
    return tuple(info.name for info in aggregator_sources() if not info.needs_key)


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
    """Which sources are set up well enough to return a posting on the next poll.

    Follows the POLLER's rule: a row must EXIST (`rows.get(name) is not None`) and be enabled, because
    `poller.build_specs` builds its work list only from `aggregators` rows that exist and are enabled.

    That used to disagree with what the Settings page displayed. `GET /settings/sources` defaulted a
    keyless source to `enabled = true` when the user had no row, so a new account saw four sources
    switched on and polled none of them — and on the live instance the second real account had zero
    rows and had been polling no aggregators at all. Both halves are now fixed rather than merely
    reported: `services.accounts.ensure_account` seeds enabled rows for the keyless sources at account
    creation, and the display no longer defaults, so what it shows is the row the poller reads. Absent
    row means off on both sides, which is why they can no longer disagree even if a seed is missed.

    The credential check is the `resume_template` lesson applied to sources: a keyed source with no
    stored credentials is a row that says "enabled" describing something that cannot run -- the
    poller writes `NO_API_KEY_MESSAGE` and nothing can ever arrive.

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
