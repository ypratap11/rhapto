"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { CoachErrorNote } from "@/components/coach/CoachFrame";
import { NotInterestedButton } from "@/components/jobs/NotInterestedButton";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button, buttonVariants } from "@/components/ui/button";
import { JobRow } from "@/components/ui/job-row";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useRecommendedJobs } from "@/lib/api/queries";
import { useStartTailor, type TailorStarter } from "@/lib/coach/useStartTailor";
import { isNewToday, RECOMMENDED_SHOWN } from "@/lib/dashboard-view";
import { formatSalary } from "@/lib/format";
import { cn } from "cn";

/**
 * The left column: up to five fit-ranked jobs with a Tailor button each. `starter` is the page's shared
 * tailor flow (so this and the next-step card share one lock); alone, the section makes its own.
 * `hideErrorFor`: a failed start for this job is already shown elsewhere (the next-step card).
 */
export function RecommendedShort({ starter, hideErrorFor }: { starter?: TailorStarter; hideErrorFor?: string | null }) {
  const own = useStartTailor();
  const { start, pickedId, error, failedJobId } = starter ?? own;
  const query = useRecommendedJobs(0);
  const jobs = query.data.slice(0, RECOMMENDED_SHOWN);
  const hasIssue = Boolean(query.error) || query.isPaused;
  const now = new Date();
  const showError = error && !(hideErrorFor && failedJobId === hideErrorFor);

  return (
    <section aria-labelledby="recommended-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="recommended-heading" className="font-serif text-xl font-semibold">
          Recommended for you
        </h2>
        <Link href="/jobs" className="inline-flex min-h-11 items-center text-sm font-medium text-primary underline-offset-4 hover:underline">
          See all matching jobs →
        </Link>
      </div>
      {hasIssue && jobs.length > 0 ? <ApiErrorBanner error={query.error ?? "Can't reach Rhapto's API."} /> : null}
      {showError ? <CoachErrorNote error={error} /> : null}
      {query.isLoading ? (
        <div className="space-y-2.5" aria-hidden>
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[84px] w-full rounded-2xl" />
          ))}
        </div>
      ) : jobs.length === 0 && !hasIssue ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border border-dashed border-border px-6 py-8 text-center">
          <Sparkles className="size-6 text-muted-foreground" aria-hidden />
          <p className="text-sm text-muted-foreground">We&apos;re finding jobs that fit you. New jobs arrive through the day.</p>
          <Link href="/start" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "max-md:min-h-11")}>
            Paste a job instead
          </Link>
        </div>
      ) : jobs.length === 0 && query.error ? (
        <p className="flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
          We couldn&apos;t load recommended jobs right now.
          <Button type="button" variant="outline" size="sm" className="max-md:min-h-11" onClick={() => void query.refetch()}>
            Try again
          </Button>
        </p>
      ) : jobs.length > 0 ? (
        <ul className="space-y-2.5">
          {jobs.map((job) => {
            const salary = formatSalary(job.salary_text, job.source);
            return (
              <JobRow
                key={job.id}
                fit={job.best_fit ?? null}
                title={job.title ?? "Untitled role"}
                meta={
                  <>
                    <span>{job.company ?? "Unknown company"}</span>
                    {job.location ? <span>{job.location}</span> : null}
                    {salary ? <StatusBadge tone="neutral">{salary}</StatusBadge> : null}
                    {isNewToday(job.discovered_at, now) ? <StatusBadge tone="primary">New today</StatusBadge> : null}
                  </>
                }
                actions={
                  <>
                    <Button type="button" variant="outline" className="max-md:min-h-11" disabled={pickedId !== null} onClick={() => void start(job)}>
                      {pickedId === job.id ? "Starting…" : "Tailor"}
                    </Button>
                    <NotInterestedButton job={job} iconOnly />
                  </>
                }
              />
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}
