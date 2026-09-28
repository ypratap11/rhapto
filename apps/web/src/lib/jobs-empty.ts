import type { components } from "./api/schema";
import type { SearchState } from "./search-state";

/** The filters `GET /jobs/empty-reason` can blame, as the generated union. */
export type JobFilterId = NonNullable<components["schemas"]["JobsEmptyReasonOut"]["filter_id"]>;

export type JobsEmptyReason = components["schemas"]["JobsEmptyReasonOut"];

/** What a filter is called in a sentence a person reads. */
export const FILTER_LABEL: Record<JobFilterId, string> = {
  hidden: "hidden",
  search_id: "saved search",
  sources: "source",
  field: "field",
  posted_within: "date",
  recommended: "recommended",
  search: "keyword",
  track: "track",
  region: "region",
  bucket: "fit bucket",
};

/**
 * How to widen one filter, per filter.
 *
 * Typed `Record<JobFilterId, ...>` against the union generated from `openapi.json`, which is the
 * point: a new server-side filter becomes a missing-property COMPILE ERROR here, not an empty grid
 * with no explanation. `test_job_filter_registry.py` holds the Python end of the same guard
 * (`{f.id for f in JOB_FILTERS if f.blamable} == get_args(JobFilterId)`), so the two ends cannot
 * drift: the server cannot add a blamable filter the client has no case for.
 *
 * `apply: null` means this filter has no one-click widen, and the explanation renders without a
 * button rather than with one that does nothing. Five ids are null today because the Jobs page never
 * sends them to `GET /jobs` at all (see `toJobsQuery`, which sends only sort, ids, posted_within,
 * sources, field and hidden), so they are unreachable from this surface. Their entries still exist,
 * so making one reachable later is a deliberate decision here instead of a silent gap.
 */
export type Widen = {
  /** Worded from the current state, because widening `hidden` means the opposite thing depending on
   * which way the switch is set. */
  label: (state: SearchState) => string;
  apply: ((state: SearchState) => SearchState) | null;
  /** `search_id` lives in the URL, not in `SearchState`, so clearing it is a navigation. */
  clearsSavedSearch?: boolean;
};

export const WIDEN: Record<JobFilterId, Widen> = {
  hidden: {
    // Both directions are real: the default view hides what the user said no to (so the widen is
    // "show them"), and "Show hidden" shows only those (so the widen is "show the rest").
    label: (s) => (s.hidden ? "Show jobs you haven't hidden" : "Include hidden jobs"),
    apply: (s) => ({ ...s, hidden: !s.hidden }),
  },
  search_id: {
    label: () => "Show all jobs, not just this search",
    apply: (s) => s,
    clearsSavedSearch: true,
  },
  sources: {
    label: () => "Clear the source filter",
    apply: (s) => ({ ...s, sources: [] }),
  },
  field: {
    label: () => "Show all my tracks",
    apply: (s) => ({ ...s, field: null }),
  },
  posted_within: {
    label: () => "Any posting date",
    apply: (s) => ({ ...s, posted_within: "any" }),
  },
  // Not reachable from the Jobs page: `toJobsQuery` never sends these.
  recommended: { label: () => "Show every job", apply: null },
  search: { label: () => "Clear the keyword filter", apply: null },
  track: { label: () => "Clear the track filter", apply: null },
  region: { label: () => "Any region", apply: null },
  bucket: { label: () => "Any fit bucket", apply: null },
};

/** Everything the Jobs page sends to `GET /jobs`, cleared. Used by the `combination` cause, where no
 * single filter is to blame and so no single widen helps. */
export function clearAllFilters(state: SearchState): SearchState {
  return { ...state, sources: [], field: null, posted_within: "any", hidden: false, fit: "all" };
}

/** Is anything the Jobs page controls actually narrowing the result right now?
 *
 * Used only to decide whether "clear all filters" is worth offering. It is NOT a reimplementation of
 * the server's `active` predicates -- nothing here decides what was filtered or why. */
export function hasActiveFilters(state: SearchState): boolean {
  return (
    state.sources.length > 0 ||
    state.field !== null ||
    state.posted_within !== "any" ||
    state.hidden ||
    state.fit !== "all"
  );
}
