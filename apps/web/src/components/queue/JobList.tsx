"use client";

import { useState } from "react";
import { toast } from "sonner";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { useDeleteJob, useJobs, type JobOut } from "@/lib/api/queries";
import { JobCard } from "./JobCard";

export function JobList({ search }: { search: string }) {
  const jobs = useJobs(search);
  const remove = useDeleteJob();
  const [pending, setPending] = useState<JobOut | null>(null);

  if (jobs.isLoading) return <Skeleton className="h-32 w-full" />;
  if (jobs.error) return <ApiErrorBanner error={jobs.error} />;
  const items = jobs.data ?? [];
  if (items.length === 0) return <p className="text-muted-foreground">No jobs yet. Add one to start tailoring.</p>;

  return (
    <div className="space-y-4">
      {items.map((job) => (
        <div key={job.id} id={job.id}>
          <JobCard job={job} onDelete={setPending} />
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
                await remove.mutateAsync(pending.id);
                toast.success("Job deleted");
                setPending(null);
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
