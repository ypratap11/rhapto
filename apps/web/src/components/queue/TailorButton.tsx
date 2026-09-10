"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ApiError } from "@/lib/api/client";
import { invalidateJobs, useTailor, useTracks, type JobOut } from "@/lib/api/queries";
import { TaskProgress } from "./TaskProgress";

export function TailorButton({ job }: { job: JobOut }) {
  const tracks = useTracks();
  const tailor = useTailor();
  const queryClient = useQueryClient();
  const [trackId, setTrackId] = useState<string | undefined>(undefined);
  const [taskId, setTaskId] = useState<string | null>(null);
  const onFinished = useCallback(() => {
    setTaskId(null);
    invalidateJobs(queryClient);
  }, [queryClient]);

  async function start() {
    try {
      const task = await tailor.mutateAsync({ jobId: job.id, body: { track_id: trackId ?? null } });
      // Always route through TaskProgress, even when the mutation already returned a
      // finished task: the SSE endpoint replays the terminal `state` event and closes
      // for finished tasks, so this is the single path that surfaces the result.
      setTaskId(task.id);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not start tailoring");
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2">
        <Select value={trackId} onValueChange={(value: string | null) => setTrackId(value ?? undefined)}>
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
