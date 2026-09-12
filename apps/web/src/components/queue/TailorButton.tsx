"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import { invalidateJobs, useResumeDocument, useTailor, useTracks, type JobOut } from "@/lib/api/queries";
import { startTailoring, stopTailoring } from "@/lib/tailoring";
import { TaskProgress } from "./TaskProgress";

const MODE_LABEL: Record<"tune" | "blocks", string> = { tune: "Tune my resume", blocks: "Build from blocks" };

export function TailorButton({ job }: { job: JobOut }) {
  const tracks = useTracks();
  const tailor = useTailor();
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
      toast.error(error instanceof ApiError ? error.message : "Could not start tailoring");
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2">
        <Select value={selectedTrackId} onValueChange={(value: string | null) => setTrackId(value ?? undefined)}>
          <SelectTrigger className="w-44" aria-label="Track">
            <SelectValue placeholder={tracks.data?.[0]?.name ?? "Track"} />
          </SelectTrigger>
          <SelectContent>
            {(tracks.data ?? []).map((t) => (
              <SelectItem key={t.id} value={t.id}>
                {t.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={selectedMode} onValueChange={(value: string | null) => value && setMode(value as "blocks" | "tune")}>
          <SelectTrigger className="w-44" aria-label="Mode">
            <SelectValue placeholder="Mode">{(value: string | null) => (value ? (MODE_LABEL[value as "tune" | "blocks"] ?? value) : "Mode")}</SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              value="tune"
              disabled={!hasResumeDocument}
              title={documentLoaded && !hasResumeDocument ? "Upload a resume document in the Profile tab to enable tune mode." : undefined}
            >
              Tune my resume
            </SelectItem>
            <SelectItem value="blocks">Build from blocks</SelectItem>
          </SelectContent>
        </Select>
        <Button onClick={start} disabled={tailor.isPending || taskId !== null}>
          {taskId ? "Tailoring…" : "Tailor"}
        </Button>
      </div>
      {taskId ? <TaskProgress taskId={taskId} jobId={job.id} onFinished={onFinished} /> : null}
    </div>
  );
}
