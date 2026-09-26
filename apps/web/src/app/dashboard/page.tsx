"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ActiveApplications } from "@/components/dashboard/ActiveApplications";
import { DashboardHero } from "@/components/dashboard/DashboardHero";
import { ProfileChecklist } from "@/components/dashboard/ProfileChecklist";
import { RecommendedRoles } from "@/components/dashboard/RecommendedRoles";
import { SavedSearchesRail } from "@/components/dashboard/SavedSearchesRail";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { SearchForm } from "@/components/jobs/SearchForm";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { HeroBand } from "@/components/shell/HeroBand";
import { useDashboard, useTaxonomy, useTracks } from "@/lib/api/queries";
import { fieldsWithTracks } from "@/lib/fields";
import { DEFAULT_SEARCH_STATE, encodeSearchState, type SearchState } from "@/lib/search-state";

// Layout: hero band, then a two-column body — 2fr of work, 1fr of context (spec §3.1). No
// Breadcrumbs here: the route is now /dashboard, not the root, but it is still the app's home
// surface for a signed-in person -- the TopBar logo and its first tab both point here -- so a
// breadcrumb reading just "Dashboard" with nothing above it to click back to would add clutter,
// not orientation.
export default function DashboardPage() {
  const router = useRouter();
  const [state, setState] = useState<SearchState>(DEFAULT_SEARCH_STATE);
  const dashboard = useDashboard();
  const tracksQuery = useTracks();
  const taxonomy = useTaxonomy();

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

  // A settled error (`dashboard.error`) isn't the only way this call never produces data: with no
  // network reachable, TanStack Query v5's default `networkMode: "online"` parks the query in
  // `fetchStatus: "paused"` instead — `status` stays "pending", so `isLoading` (`isPending &&
  // isFetching`) is false and `error` is null, the same shape a genuinely-empty dashboard has. From
  // the user's seat both are "something is wrong right now."
  //
  // But that's a different question from "do we have anything to show." A settled error or a pause
  // can happen on a *background refetch* — `providers.tsx` doesn't disable refetchOnWindowFocus or
  // reconnect refetches — after a prior fetch already populated `dashboard.data`. TanStack's query
  // reducer never clears `data` on an `error` or `pause` transition, so it's still sitting there,
  // valid, the moment this renders. Discarding it in favor of the panels' error branches would throw
  // away real numbers the user is already looking at just because the *next* refresh stumbled.
  //
  // So two separate questions, two separate booleans: `hasIssue` says something is wrong right now
  // (always shows the banner, additive context above the content) and `nothingToShow` says we have
  // no data to fall back on (gates the panels into their error branches — only when there's truly
  // nothing else to render). A background hiccup with cached data keeps showing that cached data,
  // stale but visible, with the banner making the staleness honest instead of silent.
  const hasIssue = Boolean(dashboard.error) || dashboard.isPaused;
  const nothingToShow = !dashboard.data && hasIssue;

  return (
    <>
      <HeroBand tone="peach" height="tall">
        <DashboardHero
          newFitCount={dashboard.data?.new_fit_count ?? 0}
          needsReviewCount={dashboard.data?.needs_review_count ?? 0}
          loading={dashboard.isLoading}
          error={nothingToShow}
        />
      </HeroBand>
      {hasIssue ? (
        <div className="mb-6">
          <ApiErrorBanner error={dashboard.error ?? "Can't reach Rhapto's API."} />
        </div>
      ) : null}
      <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
        <div className="space-y-8">
          <section aria-labelledby="search-heading" className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
            <h2 id="search-heading" className="font-sans text-base font-semibold">
              Find your next role
            </h2>
            {/* The Dashboard's search card does not run a live search: it hands the state to /jobs,
                which owns the result grid (spec §3.1). */}
            <SearchForm
              value={state}
              onChange={setState}
              onSubmit={() => router.push(`/jobs?${encodeSearchState(state).toString()}`)}
              fields={fields}
              pending={false}
            />
          </section>
          <RecommendedRoles tracks={tracks} />
          <ActiveApplications />
        </div>
        <aside className="space-y-8">
          <ProfileChecklist checklist={dashboard.data?.checklist ?? null} loading={dashboard.isLoading} error={nothingToShow} />
          <SavedSearchesRail searches={dashboard.data?.saved_searches ?? []} loading={dashboard.isLoading} error={nothingToShow} />
        </aside>
      </div>
    </>
  );
}
