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
import { DEFAULT_SEARCH_STATE, encodeSearchState, type SearchState } from "@/lib/search-state";

// Layout: hero band, then a two-column body — 2fr of work, 1fr of context (spec §3.1). No
// Breadcrumbs here: the Dashboard is the root, so the layout's static "Rhapto" title stands as-is.
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

  const fields = useMemo(() => (taxonomy.data?.fields ?? []).map((f) => ({ id: f.id, name: f.name })), [taxonomy.data]);

  return (
    <>
      <HeroBand tone="peach" height="tall">
        <DashboardHero
          newFitCount={dashboard.data?.new_fit_count ?? 0}
          needsReviewCount={dashboard.data?.needs_review_count ?? 0}
          loading={dashboard.isLoading}
        />
      </HeroBand>
      {dashboard.error ? (
        <div className="mb-6">
          <ApiErrorBanner error={dashboard.error} />
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
          <ProfileChecklist checklist={dashboard.data?.checklist ?? null} loading={dashboard.isLoading} />
          <SavedSearchesRail searches={dashboard.data?.saved_searches ?? []} loading={dashboard.isLoading} />
        </aside>
      </div>
    </>
  );
}
