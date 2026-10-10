"use client";

import { EyeOff } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useHideJob, useUnhideJob, type JobOut } from "@/lib/api/queries";

/** Spec §4: every stage has a way out, and every way out is reversible for 8 seconds. */
export const UNDO_TOAST_MS = 8000;

export function NotInterestedButton({ job, size = "default", className }: { job: JobOut; size?: "sm" | "default"; className?: string }) {
  const hide = useHideJob();
  const unhide = useUnhideJob();
  const label = `${job.company ?? "Unknown company"} · ${job.title ?? "Untitled role"}`;

  async function onHide() {
    try {
      await hide.mutateAsync(job.id);
      toast.success(`Hidden ${label}`, {
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
      toast.error(e instanceof ApiError ? e.message : "Could not hide the job");
    }
  }

  return (
    <Button variant="ghost" size={size} className={className} onClick={onHide} disabled={hide.isPending}>
      <EyeOff className="size-4" aria-hidden /> Not interested
    </Button>
  );
}
