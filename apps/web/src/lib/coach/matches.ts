import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { apiClient, unwrap } from "@/lib/api/client";
import type { JobOut } from "@/lib/api/queries";
import { COACH_OFFER_PASTE_MS, COACH_POLL_MS, COACH_TOP_N } from "./constants";

export type MatchesState =
  | { kind: "loading"; offerPaste: boolean }
  | { kind: "waiting"; offerPaste: boolean }
  | { kind: "ready"; jobs: JobOut[]; final: boolean }
  | { kind: "none"; reason: "no_jobs" | "no_strong_matches" };

export type MatchesInput = {
  trackJobs: JobOut[] | undefined;
  /** False while the rows on screen are the previous poll's (kept to avoid a flicker). */
  trackJobsFresh: boolean;
  /** `GET /coach/readiness`: undefined until it has answered (and while it errors). */
  ready: boolean | undefined;
  emptyCause: string | undefined;
  waitedMs: number;
};

/** Spec 3.3. A rescore commits every SCORE_CHUNK jobs, so rows (and `track=` matches) appear long
 * before scoring is done. Rows are shown as they arrive, marked not-final; the list is final only when
 * the server says the track is ready AND the list was re-read after that; "no strong matches" needs the
 * same. `no_jobs` is the one answer that needs no readiness. */
export function matchesState(i: MatchesInput): MatchesState {
  const offerPaste = i.waitedMs >= COACH_OFFER_PASTE_MS;
  const ready = i.ready === true;
  if (i.trackJobs !== undefined && i.trackJobs.length > 0) {
    return { kind: "ready", jobs: i.trackJobs.slice(0, COACH_TOP_N), final: ready && i.trackJobsFresh };
  }
  if (i.trackJobs === undefined) return { kind: "loading", offerPaste };
  if (i.emptyCause === "no_jobs") return { kind: "none", reason: "no_jobs" };
  if (ready && i.trackJobsFresh) return { kind: "none", reason: "no_strong_matches" };
  return { kind: "waiting", offerPaste };
}

export function useCoachMatches(trackId: string, options: { pollMs?: number } = {}): { state: MatchesState } {
  const pollMs = options.pollMs ?? COACH_POLL_MS;
  const [startedAt] = useState(() => Date.now());
  const [waitedMs, setWaitedMs] = useState(0);

  const readiness = useQuery({
    queryKey: ["coach", "readiness", trackId],
    queryFn: () => unwrap(apiClient().GET("/api/v1/coach/readiness", { params: { query: { track: trackId } } })),
    refetchInterval: (query) => (query.state.data?.ready ? false : pollMs),
    retry: false,
    gcTime: 0,
  });
  const ready = readiness.data?.ready;

  // The key carries the ready flag, so the flip re-reads the list once (the final answer) instead of
  // trusting rows fetched mid-rescore. `placeholderData` keeps the partial rows on screen meanwhile.
  const trackJobs = useQuery({
    queryKey: ["coach", "matches", trackId, ready === true],
    queryFn: () => unwrap(apiClient().GET("/api/v1/jobs", { params: { query: { sort: "fit", recommended: true, track: trackId } } })),
    refetchInterval: ready === true ? false : pollMs,
    placeholderData: (previous) => previous,
    gcTime: 0, // coming back for "Try another" starts from a fresh answer, not a cached top 5
  });
  const empty = trackJobs.data !== undefined && trackJobs.data.length === 0;

  const emptyReason = useQuery({
    queryKey: ["coach", "empty-reason", trackId],
    queryFn: () => unwrap(apiClient().GET("/api/v1/jobs/empty-reason", { params: { query: { sort: "fit", recommended: true, track: trackId } } })),
    enabled: empty,
    refetchInterval: ready === true ? false : pollMs,
    gcTime: 0,
  });

  const settled = ready === true && !trackJobs.isPlaceholderData && trackJobs.data !== undefined;
  useEffect(() => {
    if (settled) return;
    const timer = setInterval(() => setWaitedMs(Date.now() - startedAt), 1000);
    return () => clearInterval(timer);
  }, [settled, startedAt]);

  return {
    state: matchesState({
      trackJobs: trackJobs.data,
      trackJobsFresh: !trackJobs.isPlaceholderData,
      ready,
      emptyCause: emptyReason.data?.cause,
      waitedMs,
    }),
  };
}
