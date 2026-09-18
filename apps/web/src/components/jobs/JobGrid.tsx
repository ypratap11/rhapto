import { Skeleton } from "@/components/ui/skeleton";
import type { JobOut } from "@/lib/api/queries";
import { JobCard, type TrackInfo } from "./JobCard";

const SKELETON_COUNT = 6;

/** One placeholder shaped like a `JobCard` (spec §3: skeletons match the card/row shapes they
 * replace), rather than reusing the row-shaped `TableSkeleton`. */
function JobCardSkeleton() {
  return (
    <div className="flex h-56 flex-col gap-3 rounded-card border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-3">
        <Skeleton className="size-9 rounded-control" />
        <Skeleton className="size-9 shrink-0 rounded-full" />
      </div>
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-3 w-1/3" />
      <Skeleton className="mt-auto h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
    </div>
  );
}

/** Three-per-row down to one on a phone: `md:` (768px) then `lg:` (1024px), Tailwind's own
 * breakpoints rather than a bespoke 1100px cut. */
export function JobGrid({
  jobs,
  tracks,
  loading,
  empty,
}: {
  jobs: JobOut[];
  tracks: Record<string, TrackInfo>;
  loading: boolean;
  empty: React.ReactNode;
}) {
  if (loading) {
    return (
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3" aria-hidden="true" data-slot="job-grid-skeleton">
        {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
          <JobCardSkeleton key={i} />
        ))}
      </div>
    );
  }

  if (jobs.length === 0) return <>{empty}</>;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {jobs.map((job) => (
        <JobCard key={job.id} job={job} track={(job.best_track_id && tracks[job.best_track_id]) || null} />
      ))}
    </div>
  );
}
