"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useMe, useTracks, type JobOut } from "@/lib/api/queries";
import { locationTierLabel } from "@/lib/fit";
import { jobState, nextUp } from "@/lib/flow";
import { skipJob, unskipAll, useSkipped } from "@/lib/skipped";
import { FitBadge } from "./FitBadge";
import { JobActionButton } from "./JobActionButton";
import { SetUpProviderLink } from "./TailorButton";

export function NextUp({ jobs }: { jobs: JobOut[] }) {
  const skipped = useSkipped();
  const tracks = useTracks();
  const me = useMe();
  const ranked = nextUp(jobs, skipped, 5);
  // Only the rows whose action would start a tailoring task need a provider; a draft waiting for
  // review still wants its Review / Mark applied buttons.
  const needsProvider = me.data?.llm_configured === false;

  const trackName = (job: JobOut) => (job.best_track_id ? (tracks.data ?? []).find((t) => t.id === job.best_track_id)?.name ?? null : null);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Apply to these first</CardTitle>
        {skipped.length > 0 ? (
          <Button type="button" variant="ghost" size="sm" onClick={() => unskipAll()}>
            Show skipped
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {ranked.length === 0 ? (
          <p className="text-sm text-muted-foreground">Nothing to do: poll for jobs or add one.</p>
        ) : (
          <ol className="space-y-3">
            {ranked.map((job, i) => (
              <li key={job.id} className="flex flex-wrap items-center gap-3">
                <span className="inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-border text-xs">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{job.company ?? "Unknown company"}</span>
                    <FitBadge fit={job.best_fit ?? null} trackName={trackName(job)} minFit={null} />
                    {locationTierLabel(job.location_tier) ? <StatusBadge tone="muted">{locationTierLabel(job.location_tier)}</StatusBadge> : null}
                    {/* Which mode produced the draft waiting for review, so a mixed-mode queue is readable. */}
                    {job.latest_package ? <StatusBadge tone="muted">{job.latest_package.mode}</StatusBadge> : null}
                  </div>
                  <p className="truncate text-sm text-muted-foreground">{job.title ?? "Untitled role"}</p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {needsProvider && jobState(job) === "tailor" ? <SetUpProviderLink /> : <JobActionButton job={job} size="sm" />}
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`Skip ${job.title ?? "job"}`}
                    onClick={() => skipJob(job.id)}
                  >
                    Skip
                  </Button>
                </div>
              </li>
            ))}
          </ol>
        )}
      </CardContent>
    </Card>
  );
}
