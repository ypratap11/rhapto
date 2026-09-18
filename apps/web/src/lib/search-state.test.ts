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
    expect(toJobsQuery(DEFAULT_SEARCH_STATE, ["j1", "j2"])).toEqual({ sort: "fit", ids: "j1,j2" });
  });

  it("round-trips through the URL", () => {
    const state = { ...DEFAULT_SEARCH_STATE, query: "data", location: "Remote", remote: "only" as const, fit: "60" as const, sources: ["jooble"] };
    expect(decodeSearchState(encodeSearchState(state))).toEqual(state);
    expect(decodeSearchState(new URLSearchParams())).toEqual(DEFAULT_SEARCH_STATE);
  });

  it("filters fit client-side and keeps unscored jobs visible", () => {
    expect(passesFit(80, "75")).toBe(true);
    expect(passesFit(74, "75")).toBe(false);
    expect(passesFit(60, "60")).toBe(true);
    expect(passesFit(null, "75")).toBe(true);
  });
});
