"use client";

import { FileQuestion } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo } from "react";
import { DidYouApplyPrompt } from "@/components/jobs/DidYouApplyPrompt";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { JobHeader } from "@/components/jobs/JobHeader";
import { RepostNotice } from "@/components/jobs/RepostNotice";
import { GuardrailPanel } from "@/components/review/GuardrailPanel";
import { JdPane } from "@/components/review/JdPane";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { useJob, usePackage, useTracks } from "@/lib/api/queries";

function JobPageSkeleton({ label }: { label: string }) {
  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Jobs", href: "/jobs" }, { label }]} />
      <Skeleton className="h-32 w-full rounded-card" />
      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <Skeleton className="h-72 w-full rounded-card" />
        <Skeleton className="h-72 w-full rounded-card" />
      </div>
    </div>
  );
}

export default function JobPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const job = useJob(jobId);
  const tracksQuery = useTracks();

  const latest = job.data?.latest_package ?? null;
  const blocked = latest?.status === "blocked";
  // Called unconditionally (Rules of Hooks) with `enabled` gating the actual fetch: no package, or
  // one that isn't blocked, has nothing for the guardrail panel to show.
  const pkg = usePackage(latest?.id ?? "", blocked);

  const tracks = useMemo(() => {
    const map: Record<string, TrackInfo> = {};
    for (const t of tracksQuery.data ?? []) map[t.id] = { name: t.name, min_fit: t.min_fit };
    return map;
  }, [tracksQuery.data]);
  const track = (job.data?.best_track_id && tracks[job.data.best_track_id]) || null;

  // A404 is a real, distinct outcome (assumption A10 doesn't cover it, but the brief calls it out
  // explicitly): a deleted or mistyped job id is not "something is wrong," it's "there's nothing
  // here." It gets its own empty state rather than the generic error banner below.
  const notFound = job.error instanceof ApiError && job.error.status === 404;

  // Same two-boolean shape as the Dashboard (app/page.tsx): a paused fetch (API unreachable) settles
  // with `isLoading` false and `error` null, which looks like "empty" rather than "loading" or
  // "failed" unless checked for explicitly. `hasIssue` gates the banner (shown even alongside stale
  // cached data from a prior successful fetch); `nothingToShow` gates falling back to that banner
  // instead of content, only when there truly is no cached job to render.
  const hasIssue = !notFound && (Boolean(job.error) || job.isPaused);
  const nothingToShow = !job.data && hasIssue;

  if (notFound) {
    return (
      <>
        <Breadcrumbs items={[{ label: "Jobs", href: "/jobs" }, { label: "Job not found" }]} />
        <EmptyState
          icon={FileQuestion}
          title="This job doesn't exist"
          description="It may have been removed, or the link is wrong."
          action={
            <Link href="/jobs" className={buttonVariants({ size: "sm" })}>
              Back to Jobs
            </Link>
          }
        />
      </>
    );
  }

  if (nothingToShow) {
    return (
      <>
        <Breadcrumbs items={[{ label: "Jobs", href: "/jobs" }, { label: "Job" }]} />
        <ApiErrorBanner error={job.error ?? "Can't reach Rhapto's API."} />
      </>
    );
  }

  if (!job.data) {
    // Loading, and a paused fetch that hasn't resolved yet, both land here: a shape-matched
    // skeleton rather than a spinner, and never the empty/not-found state above.
    return <JobPageSkeleton label="Job" />;
  }

  const crumbLabel = `${job.data.company ?? "Unknown company"} · ${job.data.title ?? "Untitled role"}`;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Jobs", href: "/jobs" }, { label: crumbLabel }]} />
      {hasIssue ? <ApiErrorBanner error={job.error ?? "Can't reach Rhapto's API."} /> : null}
      <JobHeader job={job.data} track={track} />
      {job.data.repost_of ? <RepostNotice job={job.data} /> : null}
      {latest && latest.status === "ready" ? <DidYouApplyPrompt job={job.data} pkg={latest} /> : null}
      <div className="grid gap-6 lg:grid-cols-[1.2fr_1fr]">
        <JdPane job={job.data} />
        <div className="space-y-4">
          {blocked ? (
            pkg.data ? (
              <GuardrailPanel report={pkg.data.guardrail_report} onSelect={() => router.push(`/jobs/${job.data.id}/packages/${latest.id}`)} />
            ) : (
              <Skeleton className="h-40 w-full rounded-card" />
            )
          ) : null}
          {latest ? (
            <section className="space-y-1 rounded-card border border-border bg-surface p-4 shadow-card text-sm">
              <p className="font-sans text-base font-semibold">Resume v{latest.version}</p>
              <p className="text-muted-foreground capitalize">{latest.status}</p>
              <Link href={`/jobs/${job.data.id}/packages/${latest.id}`} className="inline-block text-primary underline-offset-4 hover:underline">
                Review →
              </Link>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
