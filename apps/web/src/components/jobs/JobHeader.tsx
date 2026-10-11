"use client";

import Link from "next/link";
import { useMemo } from "react";
import { toast } from "sonner";
import { TailorButton } from "@/components/jobs/TailorButton";
import { Button, buttonVariants } from "@/components/ui/button";
import { FitRing } from "@/components/ui/fit-ring";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useApplications, type JobOut } from "@/lib/api/queries";
import { markApplyOpened } from "@/lib/apply-prompt";
import { safeHttpUrl } from "@/lib/links";
import { downloadPackage } from "@/lib/download";
import { locationTierLabel, SOURCE_LABEL } from "@/lib/fit";
import { STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";
import type { TrackInfo } from "./JobCard";
import { NotInterestedButton } from "./NotInterestedButton";

/** The job page's header: title, chips (same row `JobCard` uses), a fit ring against the best
 * track, and a primary action that follows the job's state (spec §3.3) — Tailor with no package,
 * Review/Fix guardrails with one in progress, Apply once it's ready, or the application's status
 * once one exists. An existing application always wins: once applied, Apply has nothing to offer. */
export function JobHeader({ job, track }: { job: JobOut; track: TrackInfo | null }) {
  const applications = useApplications();
  const application = useMemo(() => {
    const columns = applications.data?.columns ?? {};
    return Object.values(columns).flat().find((a) => a.job.id === job.id) ?? null;
  }, [applications.data, job.id]);

  const company = job.company ?? "Unknown company";
  const title = job.title ?? "Untitled role";
  const tier = locationTierLabel(job.location_tier);
  const latest = job.latest_package;

  // Same try/catch-then-toast shape as PackageActions.downloadFile: a failed download here is
  // worse than a failed download from the review page, since Apply has already sent the user off
  // to the employer's tab — silence would mean they apply with no resume and never know it.
  async function onApply() {
    if (!latest) return;
    markApplyOpened(job.id);
    const postingUrl = safeHttpUrl(job.url);
    if (postingUrl) window.open(postingUrl, "_blank", "noopener");
    try {
      await downloadPackage(latest.id, "pdf");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not download the resume");
    }
  }

  const primary = (() => {
    if (application) {
      return (
        <div className="flex items-center gap-2">
          <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
          <Link href="/dashboard" className={buttonVariants({ variant: "outline", size: "sm" })}>
            Dashboard
          </Link>
        </div>
      );
    }
    if (!latest) return <TailorButton job={job} />;
    if (latest.status === "blocked") {
      return (
        <Link href={`/jobs/${job.id}/packages/${latest.id}`} className={buttonVariants({ size: "sm" })}>
          Fix guardrails
        </Link>
      );
    }
    if (latest.status === "ready") {
      return (
        <Button size="sm" onClick={() => void onApply()}>
          Apply
        </Button>
      );
    }
    return (
      <Link href={`/jobs/${job.id}/packages/${latest.id}`} className={buttonVariants({ size: "sm" })}>
        Review
      </Link>
    );
  })();

  return (
    <div className="flex flex-col gap-4 rounded-card border border-border bg-surface p-4 shadow-card sm:flex-row sm:items-start sm:justify-between">
      <div className="flex min-w-0 items-start gap-4">
        <div className="flex shrink-0 flex-col items-center gap-1">
          <FitRing fit={job.best_fit ?? null} size={56} />
          {track ? <p className="text-xs text-muted-foreground">against {track.name}</p> : null}
        </div>
        <div className="min-w-0 space-y-2">
          <div>
            <h1 className="text-2xl font-semibold">{title}</h1>
            <p className="text-sm text-muted-foreground">{company}</p>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {track ? <StatusBadge tone="primary">{track.name}</StatusBadge> : null}
            <StatusBadge tone="muted">{SOURCE_LABEL[job.source] ?? job.source}</StatusBadge>
            {tier ? <StatusBadge tone="muted">{tier}</StatusBadge> : null}
            {job.repost_of ? <StatusBadge tone="mid">Reposted</StatusBadge> : null}
            {job.unlisted_at ? <StatusBadge tone="muted">No longer listed</StatusBadge> : null}
            {job.search_name ? <StatusBadge tone="muted">{`via ${job.search_name}`}</StatusBadge> : null}
          </div>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {primary}
        <NotInterestedButton job={job} size="sm" />
      </div>
    </div>
  );
}
