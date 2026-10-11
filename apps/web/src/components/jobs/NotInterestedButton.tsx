"use client";

import { EyeOff } from "lucide-react";
import { cn } from "cn";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useHideJob, useUnhideJob, type JobOut } from "@/lib/api/queries";

/** Spec §4: every stage has a way out, and every way out is reversible for 8 seconds. */
export const UNDO_TOAST_MS = 8000;

/** `iconOnly`: just the eye icon, named for screen readers ("Not interested in <role>"), for tight rows. */
export function NotInterestedButton({
  job,
  size = "default",
  className,
  iconOnly = false,
}: {
  job: JobOut;
  size?: "sm" | "default";
  className?: string;
  iconOnly?: boolean;
}) {
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
    <Button
      variant="ghost"
      size={iconOnly ? "icon" : size}
      className={cn("max-md:min-h-11", className)}
      onClick={onHide}
      disabled={hide.isPending}
      aria-label={iconOnly ? `Not interested in ${job.title ?? "this job"}` : undefined}
      title={iconOnly ? "Not interested" : undefined}
    >
      <EyeOff className="size-4" aria-hidden />
      {iconOnly ? null : " Not interested"}
    </Button>
  );
}
