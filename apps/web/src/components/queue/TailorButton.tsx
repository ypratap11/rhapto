"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import { invalidateJobs, useTailor, useTracks, type JobOut } from "@/lib/api/queries";
import { startTailoring, stopTailoring } from "@/lib/tailoring";
import { TaskProgress } from "./TaskProgress";

export function TailorButton({ job }: { job: JobOut }) {
  const tracks = useTracks();
  const tailor = useTailor();
  const queryClient = useQueryClient();
  const [trackId, setTrackId] = useState<string | undefined>(undefined);
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

  async function start() {
    try {
      const task = await tailor.mutateAsync({ jobId: job.id, body: { track_id: selectedTrackId ?? null } });
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
        <Button onClick={start} disabled={tailor.isPending || taskId !== null}>
          {taskId ? "Tailoring…" : "Tailor"}
        </Button>
      </div>
      {taskId ? <TaskProgress taskId={taskId} jobId={job.id} onFinished={onFinished} /> : null}
    </div>
  );
}
