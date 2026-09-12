"use client";

import { ExternalLink, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useRescueJob, type JobOut } from "@/lib/api/queries";
import { SOURCE_LABEL } from "@/lib/fit";
import { formatRelative, truncate } from "@/lib/format";
import { PACKAGE_STATUS_TONE, STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";
import { FitBadge } from "./FitBadge";
import { JobActionButton } from "./JobActionButton";

export type TrackInfo = { name: string; min_fit: number };

export function JobCard({ job, onDelete, tracks }: { job: JobOut; onDelete: (job: JobOut) => void; tracks: Record<string, TrackInfo> }) {
  const pkg = job.latest_package;
  const rescue = useRescueJob();
  const track = job.best_track_id ? tracks[job.best_track_id] : undefined;

  async function onRescue() {
    try {
      await rescue.mutateAsync(job.id);
      toast.success("Moved to the fit list");
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not rescue the job");
    }
  }

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-5 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <FitBadge fit={job.best_fit ?? null} trackName={track?.name ?? null} minFit={track?.min_fit ?? null} />
            <StatusBadge tone="zinc">{SOURCE_LABEL[job.source] ?? job.source}</StatusBadge>
            {job.repost_of ? <StatusBadge tone="zinc">Re-post</StatusBadge> : null}
            <span className="font-medium">{job.company ?? "Unknown company"}</span>
            {pkg ? <StatusBadge tone={PACKAGE_STATUS_TONE[pkg.status] ?? "slate"}>{`v${pkg.version} · ${pkg.status}`}</StatusBadge> : null}
            {job.application_status ? (
              <StatusBadge tone={statusTone(job.application_status)}>{STATUS_LABEL[job.application_status as ApplicationStatus] ?? job.application_status}</StatusBadge>
            ) : null}
          </div>
          <h2 className="font-sans text-lg">{job.title ?? "Untitled role"}</h2>
          <p className="text-sm text-muted-foreground">
            {job.location ? `${job.location} · ` : ""}added {formatRelative(job.discovered_at)}
          </p>
          <p className="text-sm text-muted-foreground">{truncate(job.jd_text, 160)}</p>
          <div className="flex gap-3 pt-1 text-sm">
            {job.url ? (
              <a href={job.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 underline">
                Open posting <ExternalLink className="size-3" aria-hidden />
              </a>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <JobActionButton job={job} />
          {job.bucket === "low" ? (
            <Button variant="ghost" size="sm" onClick={onRescue} disabled={rescue.isPending}>
              Rescue
            </Button>
          ) : null}
          <Button variant="ghost" size="sm" onClick={() => onDelete(job)} aria-label={`Delete ${job.title ?? "job"}`}>
            <Trash2 className="size-4" aria-hidden />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
