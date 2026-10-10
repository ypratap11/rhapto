"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { EmptyJobsExplanation } from "@/components/jobs/EmptyJobsExplanation";
import { FilterChips } from "@/components/jobs/FilterChips";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { JobGrid } from "@/components/jobs/JobGrid";
import { MarkSearchViewed } from "@/components/jobs/MarkSearchViewed";
import { NoTrackPrompt } from "@/components/jobs/NoTrackPrompt";
import { PollNowButton } from "@/components/jobs/PollNowButton";
import { SaveSearchButton } from "@/components/jobs/SaveSearchButton";
import { SearchForm } from "@/components/jobs/SearchForm";
import { SourceReport } from "@/components/jobs/SourceReport";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { HeroBand } from "@/components/shell/HeroBand";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { invalidateJobs, useJobsEmptyReason, useJobsQuery, useLiveSearch, useSavedSearches, useSourceSettings, useTaxonomy, useTracks } from "@/lib/api/queries";
import { fieldsWithTracks } from "@/lib/fields";
import { decodeSearchState, encodeSearchState, passesFit, type SearchState } from "@/lib/search-state";

const SORT_LABEL: Record<SearchState["sort"], string> = {
  relevance: "Best match",
  fit: "Fit",
  newest: "Newest",
};

/** Three columns x eight rows at desktop width (Task 5b brief §1). Unlike Recommended Roles, Browse
 * has no page cap — every job the filters match must stay reachable. */
export const BROWSE_PAGE_SIZE = 24;

/** The `SearchState` fields whose change means the result set itself changed, as opposed to just the
 * page. Listed explicitly (rather than "everything but `page`") so a future field is opted in on
 * purpose, per the brief's own list (query, location, field, remote, date, source, fit, sort, hidden).
 * The `Record<Exclude<keyof SearchState, "page">, true>` type is what makes this safe: adding a field
 * to `SearchState` and forgetting it here is a compile error (missing property), not a silent gap —
 * and a typo'd key is an "excess property" error, not a field that quietly never resets. */
const RESULT_FIELDS_MAP: Record<Exclude<keyof SearchState, "page">, true> = {
  query: true,
  location: true,
  remote: true,
  field: true,
  posted_within: true,
  sources: true,
  fit: true,
  sort: true,
  hidden: true,
};
const RESULT_FIELDS = Object.keys(RESULT_FIELDS_MAP) as (keyof typeof RESULT_FIELDS_MAP)[];

function resultsChanged(a: SearchState, b: SearchState): boolean {
  return RESULT_FIELDS.some((key) => a[key] !== b[key]);
}

function JobsPageInner() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const searchParams = useSearchParams();
  const [state, setState] = useState<SearchState>(() => decodeSearchState(searchParams));
  const searchId = searchParams.get("search_id");

  // Every change also rewrites the URL, so the current search is shareable and "Save this search"
  // always has the latest filters to save (spec §6). Any change to the fields that shape the result
  // set sends the user back to page 0 — landing on "page 12 of 3 results" is the bug this guards
  // against (Task 5b brief §5). This is the filter/sort/query path: it uses `replace`, not `push`, so
  // typing in the search box doesn't fill up the Back history with one entry per keystroke. Paging
  // uses `goToPage` below, which pushes instead — see its comment for why.
  function updateState(next: SearchState) {
    const resolved = resultsChanged(state, next) ? { ...next, page: 0 } : next;
    setState(resolved);
    router.replace(`/jobs?${encodeSearchState(resolved).toString()}`);
  }

  const live = useLiveSearch();
  // The band's Search button switches the grid from the stored jobs to the live result.
  const browse = useJobsQuery(state, { enabled: live.status === "idle", searchId });
  const tracksQuery = useTracks();
  // Only a settled, empty answer is a verdict: while the tracks load (or fail) there is nothing to say.
  const noTracks = Array.isArray(tracksQuery.data) && tracksQuery.data.length === 0;
  const taxonomy = useTaxonomy();
  const sourceSettings = useSourceSettings();
  const savedSearches = useSavedSearches();

  const tracks = useMemo(() => {
    const map: Record<string, TrackInfo> = {};
    for (const t of tracksQuery.data ?? []) map[t.id] = { name: t.name, min_fit: t.min_fit };
    return map;
  }, [tracksQuery.data]);

  // Only fields the user has a track in: the rest can only ever return an empty list.
  const fields = useMemo(
    () =>
      fieldsWithTracks(
        (taxonomy.data?.fields ?? []).map((f) => ({ id: f.id, name: f.name })),
        tracksQuery.data,
      ),
    [taxonomy.data, tracksQuery.data],
  );

  // Controller ruling: FilterChips takes { source, label }, but SourceSettingOut names the field
  // `id`, not `source` — mapped here rather than changing FilterChips's decoupled prop shape.
  const sources = useMemo(() => (sourceSettings.data ?? []).map((s) => ({ source: s.id, label: s.label })), [sourceSettings.data]);

  const saved = savedSearches.data?.some((s) => s.name.toLowerCase() === state.query.trim().toLowerCase()) ?? false;

  const rawJobs = live.status === "idle" ? (browse.data ?? []) : live.jobs;
  const jobs = rawJobs.filter((j) => passesFit(j.best_fit ?? null, state.fit));
  const loading = live.status === "idle" ? browse.isLoading : live.status === "searching";
  const error = live.status === "idle" ? browse.error : live.status === "error" ? live.error : null;
  // Same gap app/dashboard/page.tsx's hasIssue/nothingToShow closes for the Dashboard: TanStack Query v5's
  // default networkMode "online" parks an unreachable `browse` query at fetchStatus "paused" —
  // isLoading false, error null, data undefined, the same shape a genuinely empty result set has.
  // hasIssue always shows the banner; nothingToShow only swaps the grid's empty-state copy when
  // there is truly nothing cached to fall back on (a background pause/error with jobs already on
  // screen keeps showing them, banner and all).
  const hasIssue = live.status === "idle" ? Boolean(browse.error) || browse.isPaused : live.status === "error";
  const nothingToShow = jobs.length === 0 && hasIssue;

  // Which layer is responsible for an empty grid, and therefore which layer explains it.
  //
  // `fit` is applied HERE, by `passesFit`, and the API has no equivalent — so when the API returned
  // rows and none survived, this page already knows the answer and must not ask the server. The count
  // comes from `passesFit`'s own output (rawJobs vs jobs), not from a second implementation of it.
  const fitHiddenCount = rawJobs.length > 0 && jobs.length === 0 ? rawJobs.length : null;
  // Otherwise the server decides the cause, and only when the grid really is empty: never while
  // loading (the answer would describe a request still in flight) and never when `hasIssue` is set
  // (the error banner already explains the emptiness — a diagnosis would contradict it). A live
  // search's zero is explained by SourceReport/per_source, so it bypasses diagnosis entirely.
  const diagnose = live.status === "idle" && rawJobs.length === 0 && !loading && !hasIssue;
  const emptyReason = useJobsEmptyReason(state, { enabled: diagnose, searchId });

  // Client-side paging over the already-fetched, already-filtered set (Task 5b brief §3): no
  // server-side offset/limit. `pageCount` is clamped to at least 1 so an (unusual) stale `page` from
  // the URL — e.g. Back to a page that no longer has that many results — never slices past the end.
  //
  // The current page is read from `searchParams`, not from `state.page`: `state` is local component
  // state that only reflects the URL at mount and whenever *this* component calls `router.replace`/
  // `push` — it does not observe a browser Back/Forward that lands on an earlier `push`. Next's
  // `useSearchParams()` does re-render on Back/Forward, so deriving from it (rather than an effect
  // that copies it into `state`) keeps the label and the sliced grid correct after Back without an
  // extra render pass or a setState-in-effect.
  const pageCount = Math.max(1, Math.ceil(jobs.length / BROWSE_PAGE_SIZE));
  const currentPage = Math.min(decodeSearchState(searchParams).page, pageCount - 1);
  const pageJobs = jobs.slice(currentPage * BROWSE_PAGE_SIZE, currentPage * BROWSE_PAGE_SIZE + BROWSE_PAGE_SIZE);
  const showPager = !loading && jobs.length > 0 && pageCount > 1;

  // Deliberately `push`, not `replace` (unlike `updateState`): a page step is a navigation the user
  // means to undo with Back, one step at a time (brief §4, "the browser Back button works"). `replace`
  // would overwrite the previous page's history entry, so Next -> Next -> Back would skip the whole
  // paging sequence instead of landing on the page before.
  function goToPage(page: number) {
    const resolved = { ...state, page };
    setState(resolved);
    router.push(`/jobs?${encodeSearchState(resolved).toString()}`);
  }

  return (
    <div className="space-y-6">
      {searchId ? <MarkSearchViewed searchId={searchId} /> : null}
      <HeroBand tone="mint">
        <h1 className="font-serif text-[32px] font-medium">Find your next role</h1>
        <SearchForm value={state} onChange={updateState} onSubmit={() => live.run(state)} fields={fields} pending={live.status === "searching"} />
        <SaveSearchButton state={state} saved={saved} />
      </HeroBand>
      <FilterChips value={state} onChange={updateState} sources={sources} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="font-sans text-lg font-semibold">Browse jobs</h2>
        <div className="flex flex-wrap items-center gap-4">
          <PollNowButton onFinished={() => invalidateJobs(queryClient)} />
          <Select value={state.sort} onValueChange={(v) => v && updateState({ ...state, sort: v as SearchState["sort"] })}>
            <SelectTrigger aria-label="Sort" size="sm">
              <SelectValue>{(v: string | null) => SORT_LABEL[(v as SearchState["sort"]) ?? "relevance"]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              {/* Default: fit decayed by age, so a strong match posted today leads a stronger
                  one from three months ago. "Fit" and "Newest" remain for either alone. */}
              <SelectItem value="relevance">Best match</SelectItem>
              <SelectItem value="fit">Fit</SelectItem>
              <SelectItem value="newest">Newest</SelectItem>
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2">
            <Switch aria-labelledby="show-hidden-label" checked={state.hidden} onCheckedChange={(v) => updateState({ ...state, hidden: v === true })} />
            <label
              id="show-hidden-label"
              className="cursor-pointer text-sm font-medium select-none"
              onClick={() => updateState({ ...state, hidden: !state.hidden })}
            >
              Show hidden
            </label>
          </div>
        </div>
      </div>
      <SourceReport perSource={live.perSource} />
      {hasIssue ? <ApiErrorBanner error={error ?? "Can't reach Rhapto's API."} /> : null}
      {noTracks ? <NoTrackPrompt /> : null}
      <JobGrid
        jobs={pageJobs}
        tracks={tracks}
        loading={loading}
        empty={
          nothingToShow ? (
            <EmptyState icon={Search} title="Couldn&rsquo;t load jobs" description="Try refreshing the page." />
          ) : (
            <EmptyJobsExplanation
              reason={emptyReason.data}
              loading={diagnose && emptyReason.isLoading}
              fitHiddenCount={fitHiddenCount}
              state={state}
              onChange={updateState}
              // `search_id` is a URL parameter, not part of `SearchState`, so clearing it is a
              // navigation rather than a state change.
              onClearSavedSearch={() => router.replace(`/jobs?${encodeSearchState(state).toString()}`)}
            />
          )
        }
      />
      {showPager ? (
        <nav aria-label="Browse jobs pages" className="flex items-center justify-center gap-3">
          <Button variant="outline" size="sm" onClick={() => goToPage(currentPage - 1)} disabled={currentPage === 0}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground" aria-live="polite">
            Page {currentPage + 1} of {pageCount}
          </span>
          <Button variant="outline" size="sm" onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= pageCount - 1}>
            Next
          </Button>
        </nav>
      ) : null}
    </div>
  );
}

export default function JobsPage() {
  return (
    <Suspense fallback={<div className="h-64 animate-pulse rounded-card bg-surface-muted" aria-hidden="true" />}>
      <JobsPageInner />
    </Suspense>
  );
}
