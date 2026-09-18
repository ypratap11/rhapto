"use client";

import { Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { FilterChips } from "@/components/jobs/FilterChips";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { JobGrid } from "@/components/jobs/JobGrid";
import { MarkSearchViewed } from "@/components/jobs/MarkSearchViewed";
import { SaveSearchButton } from "@/components/jobs/SaveSearchButton";
import { SearchForm } from "@/components/jobs/SearchForm";
import { SourceReport } from "@/components/jobs/SourceReport";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { HeroBand } from "@/components/shell/HeroBand";
import { EmptyState } from "@/components/ui/empty-state";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useJobsQuery, useLiveSearch, useSavedSearches, useSourceSettings, useTaxonomy, useTracks } from "@/lib/api/queries";
import { decodeSearchState, encodeSearchState, passesFit, type SearchState } from "@/lib/search-state";

const SORT_LABEL: Record<SearchState["sort"], string> = { fit: "Fit", newest: "Newest" };

function JobsPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [state, setState] = useState<SearchState>(() => decodeSearchState(searchParams));
  const searchId = searchParams.get("search_id");

  // Every change also rewrites the URL, so the current search is shareable and "Save this search"
  // always has the latest filters to save (spec §6).
  function updateState(next: SearchState) {
    setState(next);
    router.replace(`/jobs?${encodeSearchState(next).toString()}`);
  }

  const live = useLiveSearch();
  // The band's Search button switches the grid from the stored jobs to the live result.
  const browse = useJobsQuery(state, { enabled: live.status === "idle", searchId });
  const tracksQuery = useTracks();
  const taxonomy = useTaxonomy();
  const sourceSettings = useSourceSettings();
  const savedSearches = useSavedSearches();

  const tracks = useMemo(() => {
    const map: Record<string, TrackInfo> = {};
    for (const t of tracksQuery.data ?? []) map[t.id] = { name: t.name, min_fit: t.min_fit };
    return map;
  }, [tracksQuery.data]);

  const fields = useMemo(() => (taxonomy.data?.fields ?? []).map((f) => ({ id: f.id, name: f.name })), [taxonomy.data]);

  // Controller ruling: FilterChips takes { source, label }, but SourceSettingOut names the field
  // `id`, not `source` — mapped here rather than changing FilterChips's decoupled prop shape.
  const sources = useMemo(() => (sourceSettings.data ?? []).map((s) => ({ source: s.id, label: s.label })), [sourceSettings.data]);

  const saved = savedSearches.data?.some((s) => s.name.toLowerCase() === state.query.trim().toLowerCase()) ?? false;

  const rawJobs = live.status === "idle" ? (browse.data ?? []) : live.jobs;
  const jobs = rawJobs.filter((j) => passesFit(j.best_fit ?? null, state.fit));
  const loading = live.status === "idle" ? browse.isLoading : live.status === "searching";
  const error = live.status === "idle" ? browse.error : live.status === "error" ? live.error : null;

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
          <Select value={state.sort} onValueChange={(v) => v && updateState({ ...state, sort: v as SearchState["sort"] })}>
            <SelectTrigger aria-label="Sort" size="sm">
              <SelectValue>{(v: string | null) => SORT_LABEL[(v as SearchState["sort"]) ?? "fit"]}</SelectValue>
            </SelectTrigger>
            <SelectContent>
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
      <ApiErrorBanner error={error} />
      <JobGrid
        jobs={jobs}
        tracks={tracks}
        loading={loading}
        empty={<EmptyState icon={Search} title="No jobs yet" description="Search above, or let your saved searches fill this in." />}
      />
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
