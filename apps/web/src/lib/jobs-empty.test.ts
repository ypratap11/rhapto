import { describe, expect, it } from "vitest";
import { clearAllFilters, FILTER_LABEL, hasActiveFilters, WIDEN, type JobFilterId } from "./jobs-empty";
import { DEFAULT_SEARCH_STATE, type SearchState } from "./search-state";

/**
 * The client half of the registry-coverage guard.
 *
 * `WIDEN` and `FILTER_LABEL` are typed `Record<JobFilterId, ...>` against the union generated from
 * `openapi.json`, so a new server-side filter is a missing-property compile error — that half is
 * enforced by `tsc`, not by a test. What these tests add is that every entry is usable: a label that
 * says something, and a widen that actually changes the state it claims to widen. A map that
 * type-checks while holding an identity function for every entry would compile and explain nothing.
 *
 * The Python end is `tests/unit/test_job_filter_registry.py`, which asserts the blamable registry ids
 * equal `get_args(JobFilterId)` — so the server cannot add a blamable filter this map has no case for.
 */
const IDS = Object.keys(WIDEN) as JobFilterId[];

describe("the widen map", () => {
  it("covers exactly the same ids as the label map", () => {
    expect(new Set(Object.keys(FILTER_LABEL))).toEqual(new Set(IDS));
  });

  it("gives every filter a label that is not its own id", () => {
    for (const id of IDS) {
      expect(FILTER_LABEL[id].length).toBeGreaterThan(0);
      expect(WIDEN[id].label(DEFAULT_SEARCH_STATE).length).toBeGreaterThan(0);
      expect(WIDEN[id].label(DEFAULT_SEARCH_STATE)).not.toBe(id);
    }
  });

  it("actually changes the state for every filter the Jobs page can send", () => {
    // The five ids `toJobsQuery` really puts on the wire. Each must widen to a different state --
    // an entry that returned its input would render a button that does nothing.
    const narrowed: SearchState = {
      ...DEFAULT_SEARCH_STATE,
      sources: ["adzuna"],
      field: "engineering",
      posted_within: "24h",
      hidden: true,
    };
    for (const id of ["sources", "field", "posted_within", "hidden"] as const) {
      const apply = WIDEN[id].apply;
      expect(apply, id).not.toBeNull();
      expect(apply!(narrowed), id).not.toEqual(narrowed);
    }
  });

  it("widens the saved search by navigation rather than by a state change", () => {
    // `search_id` is a URL parameter, not part of `SearchState`, so there is nothing in the state to
    // change; the flag is what tells the caller to navigate instead.
    expect(WIDEN.search_id.clearsSavedSearch).toBe(true);
    expect(WIDEN.search_id.apply!(DEFAULT_SEARCH_STATE)).toEqual(DEFAULT_SEARCH_STATE);
  });

  it("offers no widen for the filters this page cannot send", () => {
    // Recorded rather than left ambiguous: `toJobsQuery` never sends these, so a button would be a
    // lie. The entries exist so making one reachable later is a decision taken here.
    for (const id of ["recommended", "search", "track", "region", "bucket"] as const) {
      expect(WIDEN[id].apply, id).toBeNull();
    }
  });

  it("widens the hidden switch in whichever direction is currently narrowing", () => {
    expect(WIDEN.hidden.apply!({ ...DEFAULT_SEARCH_STATE, hidden: false }).hidden).toBe(true);
    expect(WIDEN.hidden.apply!({ ...DEFAULT_SEARCH_STATE, hidden: true }).hidden).toBe(false);
    // And the label follows, because "include hidden jobs" is wrong in one of the two directions.
    expect(WIDEN.hidden.label({ ...DEFAULT_SEARCH_STATE, hidden: false })).not.toBe(
      WIDEN.hidden.label({ ...DEFAULT_SEARCH_STATE, hidden: true }),
    );
  });
});

describe("clearAllFilters", () => {
  it("clears everything the Jobs page narrows by, including the client-side fit", () => {
    const narrowed: SearchState = {
      ...DEFAULT_SEARCH_STATE,
      sources: ["adzuna", "themuse"],
      field: "engineering",
      posted_within: "24h",
      hidden: true,
      fit: "75",
    };
    expect(clearAllFilters(narrowed)).toEqual({
      ...narrowed,
      sources: [],
      field: null,
      posted_within: "any",
      fit: "all",
    });
  });

  it("leaves the hidden MODE alone, because clearing it picks a side rather than removing it", () => {
    // The API has no tri-state for `hidden`, so `hidden: false` is the exclude-hidden view, not the
    // absence of the constraint. For a corpus that is entirely hidden, "clear all filters" that also
    // set `hidden: false` left the grid exactly as empty with exactly the same message.
    expect(clearAllFilters({ ...DEFAULT_SEARCH_STATE, hidden: true }).hidden).toBe(true);
    expect(clearAllFilters({ ...DEFAULT_SEARCH_STATE, hidden: false }).hidden).toBe(false);
  });

  it("leaves the query, location, remote, sort and page alone", () => {
    // Those are not filters `GET /jobs` applies, and silently resetting them would lose the user's
    // place for no gain.
    const state: SearchState = { ...DEFAULT_SEARCH_STATE, query: "pm", location: "Remote", sort: "newest", page: 3 };
    const cleared = clearAllFilters(state);
    expect(cleared.query).toBe("pm");
    expect(cleared.location).toBe("Remote");
    expect(cleared.sort).toBe("newest");
    expect(cleared.page).toBe(3);
  });
});

describe("hasActiveFilters", () => {
  it("counts the default 90-day window, because the server really does apply it", () => {
    // Not a quirk: `posted_within` defaults to "90d", and `GET /jobs` filters on it. A corpus
    // entirely older than 90 days is empty under the default view with nothing "set", so offering
    // "clear all filters" there is correct — claiming no filter is active would be the lie.
    expect(DEFAULT_SEARCH_STATE.posted_within).toBe("90d");
    expect(hasActiveFilters(DEFAULT_SEARCH_STATE)).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_SEARCH_STATE, posted_within: "any" })).toBe(false);
  });

  it("is true once anything else narrows, from an otherwise unfiltered state", () => {
    const wide: SearchState = { ...DEFAULT_SEARCH_STATE, posted_within: "any" };
    expect(hasActiveFilters(wide)).toBe(false);
    expect(hasActiveFilters({ ...wide, sources: ["adzuna"] })).toBe(true);
    expect(hasActiveFilters({ ...wide, field: "engineering" })).toBe(true);
    expect(hasActiveFilters({ ...wide, hidden: true })).toBe(true);
    expect(hasActiveFilters({ ...wide, fit: "75" })).toBe(true);
  });

  it("is true for every individually narrowing field", () => {
    expect(hasActiveFilters({ ...DEFAULT_SEARCH_STATE, sources: ["adzuna"] })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_SEARCH_STATE, field: "engineering" })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_SEARCH_STATE, posted_within: "24h" })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_SEARCH_STATE, hidden: true })).toBe(true);
    expect(hasActiveFilters({ ...DEFAULT_SEARCH_STATE, fit: "75" })).toBe(true);
  });
});
