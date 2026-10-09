"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiClient, unwrap } from "@/lib/api/client";
import { useDashboard, useTracks, type JobOut } from "@/lib/api/queries";
import type { CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";
import { matchLabel, runsLeftLine } from "@/lib/coach/labels";
import { COACH_TOP_N } from "@/lib/coach/constants";
import { useCoachMatches } from "@/lib/coach/matches";
import { PICKER_MIN_FIT } from "@/lib/taxonomy";
import { CoachErrorNote, CoachFrame, type TranscriptItem } from "./CoachFrame";

function JobChoices({
  jobs,
  minFit,
  pickedId,
  disabled,
  onPick,
}: {
  jobs: JobOut[];
  minFit: (job: JobOut) => number;
  pickedId: string | null;
  disabled: boolean;
  onPick: (job: JobOut) => void;
}) {
  return (
    <ul className="space-y-3">
      {jobs.map((job) => (
        <li key={job.id} className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-background p-4">
          <div className="min-w-0">
            <p className="font-medium">{job.title ?? "Untitled role"}</p>
            <p className="truncate text-sm text-muted-foreground">{job.company ?? "Unknown company"}</p>
            <p className="mt-1 text-xs font-medium text-primary">{matchLabel(job.best_fit, minFit(job))}</p>
          </div>
          <Button type="button" disabled={disabled} onClick={() => onPick(job)}>
            {pickedId === job.id ? "Starting..." : "Tailor this one"}
          </Button>
        </li>
      ))}
    </ul>
  );
}

export function MatchesStep({
  trackId,
  roleName,
  transcript,
  error,
  onTailor,
  onPaste,
}: {
  trackId: string;
  roleName: string;
  transcript?: TranscriptItem[];
  error: CoachError | null;
  onTailor: (job: JobOut) => Promise<void>;
  onPaste: () => void;
}) {
  const { state } = useCoachMatches(trackId);
  const tracks = useTracks();
  const dashboard = useDashboard();
  const [showOther, setShowOther] = useState(false);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const lock = useRef(false);
  const shown = useRef(false);

  const myMinFit = tracks.data?.find((t) => t.id === trackId)?.min_fit ?? PICKER_MIN_FIT;
  const minFitFor = (job: JobOut) => tracks.data?.find((t) => t.id === job.best_track_id)?.min_fit ?? PICKER_MIN_FIT;
  const runsLine = runsLeftLine(dashboard.data?.checklist.trial_runs_left);

  const other = useQuery({
    queryKey: ["coach", "other-jobs"],
    queryFn: () => unwrap(apiClient().GET("/api/v1/jobs", { params: { query: { sort: "fit", recommended: true } } })),
    enabled: showOther,
    gcTime: 0,
  });

  useEffect(() => {
    if (state.kind === "ready" && !shown.current) {
      shown.current = true;
      void fireCoachEvent("jobs_shown");
    }
  }, [state.kind]);

  // One task per tap. The ref blocks the second event of a double click before state can update;
  // `disabled` covers the rest. The parent resolves (never rejects) so this always unlocks.
  async function pick(job: JobOut) {
    if (lock.current) return;
    lock.current = true;
    setPickedId(job.id);
    try {
      await onTailor(job);
    } finally {
      lock.current = false;
      setPickedId(null);
    }
  }

  const pasteLink = (label: string) => (
    <button type="button" className="text-primary underline underline-offset-4" onClick={onPaste}>
      {label}
    </button>
  );

  if (state.kind === "none") {
    const noJobs = state.reason === "no_jobs";
    return (
      <CoachFrame title={noJobs ? "We don't have any jobs to show yet" : `No strong matches for ${roleName} yet`} transcript={transcript}>
        <CoachErrorNote error={error} />
        <p className="text-sm text-muted-foreground">
          {noJobs ? "New jobs arrive every day. In the meantime you can tailor your resume to a job you found yourself." : "Check back soon, or tailor your resume to a job you found yourself."}
        </p>
        <div className="flex flex-wrap gap-3">
          <Button type="button" onClick={onPaste}>Paste a job</Button>
          {!noJobs ? (
            <Button type="button" variant="outline" onClick={() => setShowOther(true)}>
              Show other jobs
            </Button>
          ) : null}
        </div>
        {showOther && other.data ? (
          <JobChoices jobs={other.data.slice(0, COACH_TOP_N)} minFit={minFitFor} pickedId={pickedId} disabled={pickedId !== null} onPick={(j) => void pick(j)} />
        ) : null}
      </CoachFrame>
    );
  }

  if (state.kind !== "ready") {
    return (
      <CoachFrame title="Finding your best matches…" transcript={transcript}>
        <CoachErrorNote error={error} />
        <p role="status" className="text-sm text-muted-foreground">
          Scoring jobs against {roleName}. This can take a minute or two.
        </p>
        {state.offerPaste ? (
          <p className="text-sm">
            Taking longer than usual. {pasteLink("Paste a job you like instead")}. We keep looking in the background.
          </p>
        ) : null}
      </CoachFrame>
    );
  }

  return (
    <CoachFrame title={`Your top matches for ${roleName}`} transcript={transcript}>
      <CoachErrorNote error={error} />
      {state.final ? null : (
        <p role="status" className="text-sm text-muted-foreground">
          Still finding more matches for you. These are the best so far.
        </p>
      )}
      <JobChoices jobs={state.jobs} minFit={() => myMinFit} pickedId={pickedId} disabled={pickedId !== null} onPick={(j) => void pick(j)} />
      {runsLine ? <p className="text-sm text-muted-foreground">{runsLine}</p> : null}
      <p className="text-sm">{pasteLink("Paste a job instead")}</p>
    </CoachFrame>
  );
}
