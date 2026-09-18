"use client";

import Link from "next/link";
import { toast } from "sonner";
import { Button, buttonVariants } from "@/components/ui/button";
import { UNDO_TOAST_MS } from "@/components/jobs/NotInterestedButton";
import { ApiError } from "@/lib/api/client";
import { useArchivePackage, useHideJob, useMarkPackageReady, useUnhideJob, type PackageListItem } from "@/lib/api/queries";

/** Review / Mark ready (or Fix, once blocked) / Regenerate / Skip — the row-level actions on the
 * Resumes table (spec §3.4). Skip mirrors DidYouApplyPrompt's Skip: archive the package, hide the
 * job, and give 8 seconds to undo before the job is really gone from view. */
export function ResumeRowActions({ row }: { row: PackageListItem }) {
  const markReady = useMarkPackageReady();
  const archive = useArchivePackage();
  const hide = useHideJob();
  const unhide = useUnhideJob();

  const label = `${row.company ?? "Unknown company"} · ${row.title ?? "Untitled role"}`;
  const reviewHref = `/jobs/${row.job_id}/packages/${row.id}`;
  const blocked = row.status === "blocked";

  async function onMarkReady() {
    try {
      await markReady.mutateAsync(row.id);
      toast.success(`Marked ${label} ready`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not mark this resume ready");
    }
  }

  async function onSkip() {
    try {
      await archive.mutateAsync(row.id);
      await hide.mutateAsync(row.job_id);
      toast.success(`Skipped ${label}`, {
        duration: UNDO_TOAST_MS,
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await unhide.mutateAsync(row.job_id);
            } catch (e) {
              toast.error(e instanceof ApiError ? e.message : "Could not bring the job back");
            }
          },
        },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not skip this resume");
    }
  }

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <Link href={reviewHref} className={buttonVariants({ size: "sm", variant: "outline" })}>
        Review
      </Link>
      {blocked ? (
        <Link href={reviewHref} className={buttonVariants({ size: "sm" })}>
          Fix
        </Link>
      ) : row.status === "draft" ? (
        <Button size="sm" onClick={() => void onMarkReady()} disabled={markReady.isPending}>
          Mark ready
        </Button>
      ) : null}
      <Link href={`${reviewHref}?regenerate=1`} className={buttonVariants({ size: "sm", variant: "ghost" })}>
        Regenerate
      </Link>
      <Button size="sm" variant="ghost" onClick={() => void onSkip()} disabled={archive.isPending || hide.isPending}>
        Skip
      </Button>
    </div>
  );
}
