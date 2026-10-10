"use client";

import { Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { CoachErrorNote } from "@/components/coach/CoachFrame";
import { MatchChip } from "@/components/coach/MatchChip";
import { NotInterestedButton } from "@/components/jobs/NotInterestedButton";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useRecommendedJobs, useTailor, useTracks, type JobOut } from "@/lib/api/queries";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";
import { matchLabel } from "@/lib/coach/labels";
import { PICKER_MIN_FIT } from "@/lib/taxonomy";
import { cn } from "cn";

const SHOWN = 5;

export function RecommendedShort() {
  const router = useRouter();
  const query = useRecommendedJobs(0);
  const tracks = useTracks();
  const tailor = useTailor();
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [error, setError] = useState<CoachError | null>(null);
  const lock = useRef(false);
  const jobs = (query.data ?? []).slice(0, SHOWN);
  const hasIssue = Boolean(query.error) || query.isPaused;
  const minFit = (job: JobOut) => tracks.data?.find((t) => t.id === job.best_track_id)?.min_fit ?? PICKER_MIN_FIT;

  async function startTailor(job: JobOut) {
    if (lock.current) return; // one task per tap: a double click must not claim two runs
    lock.current = true;
    setPickedId(job.id);
    setError(null);
    try {
      const task = await tailor.mutateAsync({ jobId: job.id, body: { mode: "tune" } });
      void fireCoachEvent("tailor_started");
      router.push(`/start?task=${task.id}`);
    } catch (e) {
      setError(describeCoachError(e, "tailor"));
      setPickedId(null);
      lock.current = false;
    }
  }

  return (
    <section aria-labelledby="recommended-heading" className="space-y-3">
      <h2 id="recommended-heading" className="font-sans text-base font-semibold">
        Recommended for you
      </h2>
      {hasIssue && jobs.length > 0 ? <ApiErrorBanner error={query.error ?? "Can't reach Rhapto's API."} /> : null}
      <CoachErrorNote error={error} />
      {query.isLoading ? (
        <Skeleton className="h-40 w-full rounded-card" />
      ) : jobs.length === 0 && !hasIssue ? (
        <div className="flex flex-col items-center gap-3 rounded-card border border-dashed border-border px-6 py-8 text-center">
          <Sparkles className="size-6 text-muted-foreground" aria-hidden />
          <p className="text-sm text-muted-foreground">We&apos;re finding jobs that fit you. New jobs arrive through the day.</p>
          <Link href="/start" className={cn(buttonVariants({ variant: "outline", size: "sm" }), "max-md:min-h-11")}>
            Paste a job instead
          </Link>
        </div>
      ) : jobs.length > 0 ? (
        <ul className="divide-y divide-border rounded-card border border-border bg-surface">
          {jobs.map((job) => (
            <li key={job.id} className="flex flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center">
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{job.title ?? "Untitled role"}</p>
                <p className="truncate text-sm text-muted-foreground">
                  {[job.company ?? "Unknown company", job.location, job.salary_text].filter(Boolean).join(" · ")}
                </p>
                <p className="mt-1">
                  <MatchChip label={matchLabel(job.best_fit, minFit(job))} />
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button type="button" variant="outline" className="max-md:min-h-11" disabled={pickedId !== null} onClick={() => void startTailor(job)}>
                  {pickedId === job.id ? "Starting…" : "Tailor"}
                </Button>
                <NotInterestedButton job={job} size="sm" className="max-md:min-h-11" />
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-sm">
        <Link href="/jobs" className="inline-flex min-h-11 items-center text-muted-foreground underline underline-offset-4 hover:text-foreground">
          See all matching jobs →
        </Link>
      </p>
    </section>
  );
}
