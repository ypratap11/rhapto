"use client";

import { toast } from "sonner";
import { UNDO_TOAST_MS } from "@/components/jobs/NotInterestedButton";
import { ApiError } from "@/lib/api/client";
import { useArchivePackage, useHideJob, useUnhideJob } from "@/lib/api/queries";

/** Archive a package, hide its job, and give 8 seconds to undo before the job is really gone from
 * view. Mirrors DidYouApplyPrompt's Skip. Resolves true when both calls succeeded. */
export function useArchiveAndHide(): {
  archiveAndHide: (args: { packageId: string; jobId: string; label: string }) => Promise<boolean>;
  isPending: boolean;
} {
  const archive = useArchivePackage();
  const hide = useHideJob();
  const unhide = useUnhideJob();

  async function archiveAndHide({ packageId, jobId, label }: { packageId: string; jobId: string; label: string }): Promise<boolean> {
    try {
      await archive.mutateAsync(packageId);
      await hide.mutateAsync(jobId);
      toast.success(`Archived ${label}`, {
        duration: UNDO_TOAST_MS,
        action: {
          label: "Undo",
          onClick: async () => {
            try {
              await unhide.mutateAsync(jobId);
            } catch (e) {
              toast.error(e instanceof ApiError ? e.message : "Could not bring the job back");
            }
          },
        },
      });
      return true;
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not archive this resume");
      return false;
    }
  }

  return { archiveAndHide, isPending: archive.isPending || hide.isPending };
}
