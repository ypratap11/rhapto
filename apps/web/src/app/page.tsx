"use client";

import { Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { AddJobDialog } from "@/components/queue/AddJobDialog";
import { FilterBar } from "@/components/queue/FilterBar";
import { JobList } from "@/components/queue/JobList";
import { NextUp } from "@/components/queue/NextUp";
import { PollNowButton } from "@/components/queue/PollNowButton";
import { RunsDrawer } from "@/components/queue/RunsDrawer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DEFAULT_REGION, invalidateDiscovery, useDiscoveryRuns, useJobs, useTracks, type JobFilters } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";

export default function QueuePage() {
  const [query, setQuery] = useState("");
  const [filters, setFilters] = useState<JobFilters>({ search: "", track: null, tab: "new", region: DEFAULT_REGION, sort: "fit" });
  // "Apply to these first" follows the Region choice too: a shortlist that leads with jobs you
  // have filtered out of the list below would send you somewhere you already said no to.
  const allFit = useJobs({ search: "", track: null, tab: "new", region: filters.region, sort: "fit" });
  const [open, setOpen] = useState(false);
  const [runsOpen, setRunsOpen] = useState(false);
  const queryClient = useQueryClient();
  const tracks = useTracks();
  const runs = useDiscoveryRuns();

  useEffect(() => {
    const t = setTimeout(() => setFilters((f) => ({ ...f, search: query.trim() })), 250);
    return () => clearTimeout(t);
  }, [query]);

  const runRows = runs.data ?? [];
  const lastRun = runRows[0];
  const newCount = runRows.reduce((sum, r) => sum + r.new, 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl">Jobs</h1>
        <div className="flex gap-2">
          <Input aria-label="Search jobs" placeholder="Search company, title, text" value={query} onChange={(e) => setQuery(e.target.value)} className="w-64" />
          <PollNowButton onFinished={() => invalidateDiscovery(queryClient)} />
          <Button onClick={() => setOpen(true)}>
            <Plus className="size-4" aria-hidden /> Add job
          </Button>
        </div>
      </div>
      <NextUp jobs={allFit.data ?? []} />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <FilterBar filters={filters} onChange={setFilters} tracks={(tracks.data ?? []).map((t) => ({ id: t.id, name: t.name }))} />
        <div className="text-sm text-muted-foreground">
          {runs.isLoading ? null : runs.error ? (
            "Could not load poll runs "
          ) : lastRun ? (
            <>
              Last poll {formatRelative(lastRun.finished_at ?? lastRun.started_at)} · {newCount} new{" "}
            </>
          ) : (
            "No polls yet "
          )}
          <button type="button" className="underline" onClick={() => setRunsOpen(true)}>
            Runs
          </button>
        </div>
      </div>
      <JobList filters={filters} />
      <AddJobDialog open={open} onOpenChange={setOpen} />
      <RunsDrawer open={runsOpen} onOpenChange={setRunsOpen} />
    </div>
  );
}
