import { describe, expect, it } from "vitest";
import type { JobOut } from "@/lib/api/queries";
import { COACH_OFFER_PASTE_MS } from "./constants";
import { matchesState, type MatchesInput } from "./matches";

const job = (id: string) => ({ id, title: `Role ${id}`, company: "ExampleCo", best_fit: 70, scores: [] }) as unknown as JobOut;

const base: MatchesInput = { trackJobs: undefined, trackJobsFresh: true, ready: undefined, emptyCause: undefined, waitedMs: 0 };

describe("matchesState", () => {
  it("is loading until the track-filtered list has answered", () => {
    expect(matchesState(base)).toEqual({ kind: "loading", offerPaste: false });
  });

  it("shows_partial_rows_as_they_arrive_but_not_final: one chunk has hits, scoring is not done", () => {
    const state = matchesState({ ...base, trackJobs: [job("a")], ready: false });
    expect(state).toEqual({ kind: "ready", jobs: [job("a")], final: false });
  });

  it("rows_with_readiness_unanswered_are_not_final either", () => {
    expect(matchesState({ ...base, trackJobs: [job("a")], ready: undefined })).toMatchObject({ kind: "ready", final: false });
  });

  it("a ready flag over a list that has not been re-read since is not final (the list may still be the partial one)", () => {
    expect(matchesState({ ...base, trackJobs: [job("a")], ready: true, trackJobsFresh: false })).toMatchObject({ kind: "ready", final: false });
  });

  it("is_final_only_when_ready_and_the_list_is_fresh, capped at five", () => {
    const jobs = Array.from({ length: 8 }, (_, i) => job(`j${i}`));
    const state = matchesState({ ...base, trackJobs: jobs, ready: true });
    expect(state.kind === "ready" && state.final).toBe(true);
    expect(state.kind === "ready" && state.jobs).toHaveLength(5);
  });

  it("never_declares_no_matches_while_scoring_is_pending: an empty list is just 'not yet' for any cause but no_jobs", () => {
    for (const cause of [undefined, "filter", "combination", "nothing_matched", "field_without_tracks"]) {
      expect(matchesState({ ...base, trackJobs: [], ready: false, emptyCause: cause })).toEqual({ kind: "waiting", offerPaste: false });
      expect(matchesState({ ...base, trackJobs: [], ready: undefined, emptyCause: cause })).toEqual({ kind: "waiting", offerPaste: false });
    }
  });

  it("declares_empty_only_when_ready: ready and fresh and still empty is real", () => {
    expect(matchesState({ ...base, trackJobs: [], ready: true, emptyCause: "filter" })).toEqual({ kind: "none", reason: "no_strong_matches" });
    expect(matchesState({ ...base, trackJobs: [], ready: true, emptyCause: undefined })).toEqual({ kind: "none", reason: "no_strong_matches" });
  });

  it("an empty list read before the ready flag flipped is not yet real", () => {
    expect(matchesState({ ...base, trackJobs: [], ready: true, trackJobsFresh: false, emptyCause: "filter" })).toEqual({ kind: "waiting", offerPaste: false });
  });

  it("no_jobs_is_final_at_once: not ready, nothing to wait for", () => {
    expect(matchesState({ ...base, trackJobs: [], ready: false, emptyCause: "no_jobs" })).toEqual({ kind: "none", reason: "no_jobs" });
  });

  it("a partial list improves: the same track shows 1 row, then 3, then final", () => {
    const first = matchesState({ ...base, trackJobs: [job("a")], ready: false });
    const second = matchesState({ ...base, trackJobs: [job("a"), job("b"), job("c")], ready: false });
    const last = matchesState({ ...base, trackJobs: [job("a"), job("b"), job("c")], ready: true });
    expect([first, second, last].map((s) => s.kind === "ready" && [s.jobs.length, s.final])).toEqual([[1, false], [3, false], [3, true]]);
  });

  it("offers the paste option once the wait passes the threshold, while still waiting", () => {
    const waited = { ...base, waitedMs: COACH_OFFER_PASTE_MS };
    expect(matchesState(waited)).toEqual({ kind: "loading", offerPaste: true });
    expect(matchesState({ ...waited, trackJobs: [], ready: false, emptyCause: "filter" })).toEqual({ kind: "waiting", offerPaste: true });
    expect(matchesState({ ...base, waitedMs: COACH_OFFER_PASTE_MS - 1 })).toEqual({ kind: "loading", offerPaste: false });
  });
});
