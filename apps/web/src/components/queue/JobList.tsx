"use client";

import { useMemo, useState } from "react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { ApiError } from "@/lib/api/client";
import { useDeleteJob, useJobs, useTracks, type JobFilters, type JobOut } from "@/lib/api/queries";
import { JobCard, type TrackInfo } from "./JobCard";

export function JobList({ filters }: { filters: JobFilters }) {
  const jobs = useJobs(filters);
  const tracksQuery = useTracks();
  const remove = useDeleteJob();
  const [pending, setPending] = useState<JobOut | null>(null);

  const tracks = useMemo(() => {
    const map: Record<string, TrackInfo> = {};
    for (const t of tracksQuery.data ?? []) map[t.id] = { name: t.name, min_fit: t.min_fit };
    return map;
  }, [tracksQuery.data]);

  if (jobs.isLoading) return <Skeleton className="h-32 w-full" />;
  if (jobs.error) return <ApiErrorBanner error={jobs.error} />;
  const all = jobs.data ?? [];
  const items =
    filters.tab === "low" ? all : all.filter((job) => (filters.tab === "tailored" ? job.latest_package !== null : job.latest_package === null));
  if (items.length === 0) return <p className="text-muted-foreground">No jobs yet. Add one to start tailoring.</p>;

  return (
    <div className="space-y-4">
      {items.map((job) => (
        <div key={job.id} id={`job-${job.id}`}>
          <JobCard job={job} onDelete={setPending} tracks={tracks} />
        </div>
      ))}
      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this job?</AlertDialogTitle>
            <AlertDialogDescription>All its packages and its application record will be removed.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={async () => {
                if (!pending) return;
                try {
                  await remove.mutateAsync(pending.id);
                  toast.success("Job deleted");
                  setPending(null);
                } catch (error) {
                  toast.error(error instanceof ApiError ? error.message : "Could not delete the job.");
                }
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
