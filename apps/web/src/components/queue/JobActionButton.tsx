"use client";

import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useMarkApplied, type JobOut } from "@/lib/api/queries";
import { jobState } from "@/lib/flow";
import { TailorButton } from "./TailorButton";

export function JobActionButton({ job, size = "default" }: { job: JobOut; size?: "sm" | "default" }) {
  const state = jobState(job);
  const mark = useMarkApplied();
  if (state === "tailor") return <TailorButton job={job} />;
  if (state === "applied") {
    return (
      <div className="flex items-center gap-2">
        <StatusBadge tone="green">Applied</StatusBadge>
        <Link href="/pipeline" className="text-sm underline">
          Pipeline
        </Link>
      </div>
    );
  }
  const pkg = job.latest_package!;

  async function onMarkApplied() {
    try {
      await mark.markApplied(job, pkg.id, null);
      toast.success("Marked as applied", {
        // Mirrors TaskProgress.tsx's toast-action navigation: this callback fires
        // outside React's render/commit cycle, so it uses the browser navigation
        // API rather than next/navigation's useRouter (which requires a mounted
        // App Router context that a toast action does not have).
        action: {
          label: "Open pipeline",
          onClick: () => {
            window.location.assign("/pipeline");
          },
        },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not mark as applied");
    }
  }

  return (
    <div className="flex items-center gap-2">
      <Button size={size} render={<Link href={`/jobs/${job.id}/packages/${pkg.id}`} />}>
        Review
      </Button>
      <Button size={size} variant="outline" onClick={onMarkApplied} disabled={mark.isPending}>
        Mark applied
      </Button>
    </div>
  );
}
