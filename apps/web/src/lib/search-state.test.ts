import { describe, expect, it } from "vitest";
import { DEFAULT_SEARCH_STATE, decodeSearchState, encodeSearchState, passesFit, toJobsQuery, toSearchBody } from "./search-state";

describe("search state", () => {
  it("sends only the fields the API takes, dropping empties", () => {
    expect(toSearchBody({ ...DEFAULT_SEARCH_STATE, query: "program manager" })).toEqual({
      query: "program manager",
      remote: "include",
    });
    expect(
      toSearchBody({ ...DEFAULT_SEARCH_STATE, query: "tpm", location: "Austin, TX", field: "engineering", posted_within: "7d", sources: ["themuse", "adzuna"] }),
    ).toEqual({ query: "tpm", location: "Austin, TX", remote: "include", field: "engineering", posted_within: "7d", sources: ["themuse", "adzuna"] });
  });

  it("serialises GET /jobs filters as comma-separated lists", () => {
    expect(toJobsQuery({ ...DEFAULT_SEARCH_STATE, sources: ["a", "b"], posted_within: "24h", sort: "newest", hidden: true, field: "design" })).toEqual({
      sort: "newest",
      posted_within: "24h",
      sources: "a,b",
      field: "design",
      hidden: "true",
    });
    expect(toJobsQuery(DEFAULT_SEARCH_STATE, ["j1", "j2"])).toEqual({ sort: "newest", ids: "j1,j2" });
  });

  it("round-trips through the URL", () => {
    const state = { ...DEFAULT_SEARCH_STATE, query: "data", location: "Remote", remote: "only" as const, fit: "60" as const, sources: ["jooble"] };
    expect(decodeSearchState(encodeSearchState(state))).toEqual(state);
    expect(decodeSearchState(new URLSearchParams())).toEqual(DEFAULT_SEARCH_STATE);
  });

  it("round-trips the new defaults (90d posted_within, newest sort) through the URL", () => {
    expect(DEFAULT_SEARCH_STATE.posted_within).toBe("90d");
    expect(DEFAULT_SEARCH_STATE.sort).toBe("newest");
    // Both are the defaults, so encoding the untouched default state omits them from the URL,
    // same as every other default field.
    expect(encodeSearchState(DEFAULT_SEARCH_STATE).toString()).toBe("");
    expect(decodeSearchState(new URLSearchParams())).toEqual(DEFAULT_SEARCH_STATE);
    // An explicit choice of the *old* defaults still round-trips, now as a non-default value.
    const explicitOld = { ...DEFAULT_SEARCH_STATE, posted_within: "any" as const, sort: "fit" as const };
    expect(decodeSearchState(encodeSearchState(explicitOld))).toEqual(explicitOld);
  });

  it("filters fit client-side and keeps unscored jobs visible", () => {
    expect(passesFit(80, "75")).toBe(true);
    expect(passesFit(74, "75")).toBe(false);
    expect(passesFit(60, "60")).toBe(true);
    expect(passesFit(null, "75")).toBe(true);
  });

  it("defaults page to 0", () => {
    expect(DEFAULT_SEARCH_STATE.page).toBe(0);
  });

  it("round-trips a non-zero page through the URL, but omits page 0", () => {
    const state = { ...DEFAULT_SEARCH_STATE, page: 3 };
    const encoded = encodeSearchState(state);
    expect(encoded.get("page")).toBe("3");
    expect(decodeSearchState(encoded)).toEqual(state);
    expect(encodeSearchState(DEFAULT_SEARCH_STATE).has("page")).toBe(false);
    expect(decodeSearchState(new URLSearchParams())).toEqual(DEFAULT_SEARCH_STATE);
  });

  it("falls back to page 0 for a garbage page param", () => {
    expect(decodeSearchState(new URLSearchParams("page=-1")).page).toBe(0);
    expect(decodeSearchState(new URLSearchParams("page=abc")).page).toBe(0);
    expect(decodeSearchState(new URLSearchParams("page=1.5")).page).toBe(0);
  });
});
