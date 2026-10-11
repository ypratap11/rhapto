"use client";

import { useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import { invalidateJobs, useMe, useResumeDocument, useTailor, useTracks, type JobOut } from "@/lib/api/queries";
import { startTailoring, stopTailoring } from "@/lib/tailoring";
import { TaskProgress } from "./TaskProgress";

/** The tailor endpoint's two "your LLM is not usable" conflicts, both fixed on the Settings page. */
const LLM_SETUP_CODES = new Set(["llm_not_configured", "llm_key_unreadable"]);

export function SetUpProviderLink() {
  return (
    <Link href="/settings" className="text-sm underline">
      Add an AI key in Settings
    </Link>
  );
}

export function TailorButton({ job }: { job: JobOut }) {
  const tracks = useTracks();
  const tailor = useTailor();
  const me = useMe();
  const router = useRouter();
  const resumeDocument = useResumeDocument();
  const queryClient = useQueryClient();
  const [trackId, setTrackId] = useState<string | undefined>(undefined);
  const [mode, setMode] = useState<"blocks" | "tune" | undefined>(undefined);
  const [taskId, setTaskId] = useState<string | null>(null);
  // Tracks whether the tailoring store currently counts this job as running,
  // so the unmount cleanup below only stops it if it was never finished.
  const started = useRef(false);
  const onFinished = useCallback(() => {
    started.current = false;
    stopTailoring(job.id);
    setTaskId(null);
    invalidateJobs(queryClient);
  }, [queryClient, job.id]);

  // If this button unmounts (e.g. the job leaves the list) while a task is
  // still running, make sure the tailoring count doesn't leak: TaskProgress's
  // own cleanup aborts the stream without calling onFinished in that case.
  useEffect(() => {
    return () => {
      if (started.current) {
        started.current = false;
        stopTailoring(job.id);
      }
    };
  }, [job.id]);

  // Preselect the job's best-fit track (falling back to the first loaded track)
  // until the user makes an explicit choice, which then wins from then on. Derived
  // from props/query data rather than synced via an effect, per the lint rule
  // against synchronous setState in effects.
  const selectedTrackId = trackId ?? job.best_track_id ?? tracks.data?.[0]?.id;
  // Same derived-not-effect pattern as the track select: default to tune mode once a resume
  // document exists, but let an explicit user choice win from then on.
  //
  // Until the document query settles we know nothing, so we resolve no default at all: the
  // mode select shows a placeholder and `start()` sends `mode: null`, which lets the API apply
  // its own "tune when a document exists" default. Guessing "blocks" here would override that
  // and spend three LLM calls on the wrong mode for anyone who clicks Tailor straight away.
  const documentLoaded = !resumeDocument.isPending && resumeDocument.data !== undefined;
  const hasResumeDocument = documentLoaded && resumeDocument.data != null;
  const selectedMode = mode ?? (documentLoaded ? (hasResumeDocument ? "tune" : "blocks") : null);

  async function start() {
    try {
      const task = await tailor.mutateAsync({ jobId: job.id, body: { track_id: selectedTrackId ?? null, mode: selectedMode } });
      // Always route through TaskProgress, even when the mutation already returned a
      // finished task: the SSE endpoint replays the terminal `state` event and closes
      // for finished tasks, so this is the single path that surfaces the result.
      setTaskId(task.id);
      started.current = true;
      startTailoring(job.id);
    } catch (error) {
      // A missing or unreadable key is fixable, and only on the Settings page: say so and go there.
      if (error instanceof ApiError && error.status === 409 && LLM_SETUP_CODES.has(String(error.problem?.code))) {
        toast.error(error.problem?.detail ?? error.message, {
          action: { label: "Open settings", onClick: () => router.push("/settings") },
        });
        return;
      }
      toast.error(error instanceof ApiError ? error.message : "Could not start tailoring");
    }
  }

  // Starting a task without a provider can only fail, so send the user to Settings instead of
  // offering the button. `undefined` (still loading) is not "not configured": leave the button.
  if (me.data?.llm_configured === false) return <SetUpProviderLink />;

  const tuneHint = documentLoaded && !hasResumeDocument ? "Upload a resume document in the Profile tab to enable tune mode." : null;
  const trackList = tracks.data ?? [];

  return (
    <div className="space-y-2">
      <Button className="max-sm:w-full min-h-11" onClick={start} disabled={tailor.isPending || taskId !== null}>
        {taskId ? "Tailoring\u2026" : "Tailor my resume for this job"}
      </Button>
      <details className="text-sm">
        <summary className="flex min-h-11 cursor-pointer items-center text-muted-foreground">Options</summary>
        <div className="space-y-3 pb-2">
          <fieldset className="space-y-1">
            <legend className="sr-only">How to tailor</legend>
            <label className="flex min-h-11 items-center gap-2">
              <input
                type="radio"
                name={`tailor-mode-${job.id}`}
                checked={selectedMode === "tune"}
                disabled={!hasResumeDocument}
                onChange={() => setMode("tune")}
              />
              Light touch (keep my wording, change little)
            </label>
            {tuneHint ? <p className="text-xs text-muted-foreground">{tuneHint}</p> : null}
            <label className="flex min-h-11 items-center gap-2">
              <input type="radio" name={`tailor-mode-${job.id}`} checked={selectedMode === "blocks"} onChange={() => setMode("blocks")} />
              Full rewrite (rebuild from my experience)
            </label>
          </fieldset>
          {trackList.length > 1 ? (
            <Select value={selectedTrackId} onValueChange={(value: string | null) => setTrackId(value ?? undefined)}>
              <SelectTrigger className="min-h-11 w-full sm:w-56" aria-label="Goal">
                <SelectValue placeholder={trackList[0]?.name ?? "Goal"} />
              </SelectTrigger>
              <SelectContent>
                {trackList.map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : null}
        </div>
      </details>
      {taskId ? <TaskProgress taskId={taskId} jobId={job.id} onFinished={onFinished} /> : null}
    </div>
  );
}
