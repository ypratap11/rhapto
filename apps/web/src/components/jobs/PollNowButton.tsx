"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { usePollNow } from "@/lib/api/queries";
import { TaskProgress } from "./TaskProgress";

export function PollNowButton({ onFinished }: { onFinished: () => void }) {
  const poll = usePollNow();
  const [taskId, setTaskId] = useState<string | null>(null);

  async function start() {
    try {
      const task = await poll.mutateAsync();
      // Always route through TaskProgress, even when the mutation already returned a
      // finished task: the SSE endpoint replays the terminal `state` event and closes
      // for finished tasks, so this is the single path that surfaces the result.
      setTaskId(task.id);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not start polling");
    }
  }

  function finished() {
    setTaskId(null);
    onFinished();
  }

  return (
    <div>
      <Button variant="outline" className="max-md:min-h-11" onClick={start} disabled={poll.isPending || taskId !== null}>
        Poll now
      </Button>
      {taskId ? <TaskProgress taskId={taskId} jobId="" onFinished={finished} kind="poll" /> : null}
    </div>
  );
}
