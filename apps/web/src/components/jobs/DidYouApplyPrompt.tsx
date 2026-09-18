"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useArchivePackage, useHideJob, useMarkApplied, useUnhideJob, type JobOut, type PackageSummary } from "@/lib/api/queries";
import { clearApplyOpened, useApplyPrompt } from "@/lib/apply-prompt";
import { UNDO_TOAST_MS } from "./NotInterestedButton";

/**
 * Shown once the user comes back to this tab after Apply sent them to the employer's posting
 * (spec §3.3). Rhapto never submits (CLAUDE.md rule 1) — this is the only way the pipeline learns
 * what happened out there, so it asks rather than guessing.
 */
export function DidYouApplyPrompt({ job, pkg }: { job: JobOut; pkg: PackageSummary }) {
  const show = useApplyPrompt(job.id);
  const router = useRouter();
  const { markApplied, isPending: applying } = useMarkApplied();
  const archive = useArchivePackage();
  const hide = useHideJob();
  const unhide = useUnhideJob();

  if (!show) return null;

  const label = `${job.company ?? "Unknown company"} · ${job.title ?? "Untitled role"}`;

  async function onYes() {
    try {
      // This prompt only appears right after Apply sent the user out for the newest ready
      // package, before any application for this job exists yet, so there is nothing to look up.
      await markApplied({ id: job.id }, pkg.id, null);
      clearApplyOpened(job.id);
      toast.success("Added to your pipeline", {
        action: { label: "Open pipeline", onClick: () => router.push("/pipeline") },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not record the application");
    }
  }

  function onNotYet() {
    clearApplyOpened(job.id);
  }

  async function onSkip() {
    try {
      await archive.mutateAsync(pkg.id);
      await hide.mutateAsync(job.id);
      clearApplyOpened(job.id);
      toast.success(`Skipped ${label}`, {
        duration: UNDO_TOAST_MS,
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await unhide.mutateAsync(job.id);
            } catch (e) {
              toast.error(e instanceof ApiError ? e.message : "Could not bring the job back");
            }
          },
        },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not skip this job");
    }
  }

  return (
    <div className="space-y-3 rounded-card border border-primary/40 bg-band-peach p-4">
      <div>
        <h3 className="font-sans text-base font-semibold">Did you apply?</h3>
        <p className="text-sm text-muted-foreground">Rhapto never submits for you — tell it what happened so the pipeline stays honest.</p>
      </div>
      <div className="flex items-center gap-2">
        <Button onClick={() => void onYes()} disabled={applying}>
          Yes
        </Button>
        <Button variant="outline" onClick={onNotYet}>
          Not yet
        </Button>
        <Button variant="ghost" onClick={() => void onSkip()} disabled={archive.isPending || hide.isPending}>
          Skip
        </Button>
      </div>
    </div>
  );
}
