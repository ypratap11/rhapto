"use client";

import { Sparkles } from "lucide-react";
import { useState } from "react";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { JobGrid } from "@/components/jobs/JobGrid";
import { NoTrackPrompt } from "@/components/jobs/NoTrackPrompt";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { RECOMMENDED_MAX_PAGES, RECOMMENDED_PAGE_SIZE, useRecommendedJobs } from "@/lib/api/queries";

/** Spec §3.1: fit-ranked jobs with no resume and no application, ten per page, five pages max. */
export function RecommendedRoles({ tracks, noTracks = false }: { tracks: Record<string, TrackInfo>; noTracks?: boolean }) {
  const [page, setPage] = useState(0);
  const query = useRecommendedJobs(page);
  const jobs = query.data ?? [];
  const onLastPage = page >= RECOMMENDED_MAX_PAGES - 1;
  // A page shorter than the page size is the last page of real data, hard cap or not.
  const morePagesLeft = jobs.length === RECOMMENDED_PAGE_SIZE;
  // Same gap app/dashboard/page.tsx's hasIssue/nothingToShow closes: a query that can't reach the network
  // parks at fetchStatus "paused" (isLoading false, error null, data undefined) rather than
  // settling into `error` — indistinguishable from a genuinely empty page without this.
  const hasIssue = Boolean(query.error) || query.isPaused;
  const nothingToShow = jobs.length === 0 && hasIssue;

  return (
    <section aria-labelledby="recommended-heading" className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <h2 id="recommended-heading" className="font-sans text-base font-semibold">
          Recommended roles
        </h2>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0}>
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setPage((p) => Math.min(RECOMMENDED_MAX_PAGES - 1, p + 1))}
            disabled={onLastPage || !morePagesLeft}
          >
            Next
          </Button>
        </div>
      </div>
      {hasIssue ? <ApiErrorBanner error={query.error ?? "Can't reach Rhapto's API."} /> : null}
      {noTracks ? <NoTrackPrompt /> : null}
      <JobGrid
        jobs={jobs}
        tracks={tracks}
        loading={query.isLoading}
        empty={
          nothingToShow ? (
            <EmptyState icon={Sparkles} title="Couldn&rsquo;t load recommended roles" description="Try refreshing the page." />
          ) : (
            <EmptyState icon={Sparkles} title="Nothing to recommend yet" />
          )
        }
      />
    </section>
  );
}
