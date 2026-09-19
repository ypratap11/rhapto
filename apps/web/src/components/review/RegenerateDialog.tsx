"use client";

import { useRouter } from "next/navigation";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { TaskProgress } from "@/components/jobs/TaskProgress";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useResumeDocument, useTailor, useTracks, type JobOut, type PackageOut } from "@/lib/api/queries";
import type { ProgressState } from "@/lib/task-progress";

export function RegenerateDialog({ job, pkg, open, onOpenChange }: { job: JobOut; pkg: PackageOut; open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const tailor = useTailor();
  const tracks = useTracks();
  const resumeDocument = useResumeDocument();
  const [feedback, setFeedback] = useState("");
  const [trackId, setTrackId] = useState(pkg.track_id);
  const [mode, setMode] = useState<"blocks" | "tune" | undefined>(undefined);
  // Default to tune mode whenever a resume document exists, even when the parent package was
  // built from blocks: regenerating an old package is how a user moves it onto their own
  // template. Without a document the parent's mode is the only one that can run.
  const hasResumeDocument = resumeDocument.data != null;
  const selectedMode = mode ?? (hasResumeDocument ? "tune" : pkg.mode);
  const [error, setError] = useState<string | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const onFinished = useCallback(
    (state: ProgressState) => {
      if (state.status === "succeeded" && state.packageId) {
        onOpenChange(false);
        router.push(`/jobs/${job.id}/packages/${state.packageId}`);
      }
      setTaskId(null);
    },
    [job.id, onOpenChange, router],
  );

  async function submit() {
    const text = feedback.trim();
    if (text.length < 10 || text.length > 500) {
      setError("Give at least 10 characters of feedback (500 max).");
      return;
    }
    setError(null);
    try {
      const task = await tailor.mutateAsync({ jobId: job.id, body: { feedback: text, parent_package_id: pkg.id, track_id: trackId, mode: selectedMode } });
      if (task.status === "succeeded" && task.result_ref) {
        onOpenChange(false);
        router.push(`/jobs/${job.id}/packages/${task.result_ref}`);
        return;
      }
      if (task.status === "failed") {
        setError(task.error ?? "Regeneration failed");
        return;
      }
      setTaskId(task.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not start regeneration");
      toast.error("Regeneration failed to start");
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Regenerate this package</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label htmlFor="feedback">Feedback</Label>
            <Textarea id="feedback" rows={4} value={feedback} onChange={(e) => setFeedback(e.target.value)} placeholder="e.g. lean harder on the migration work; drop the side project" />
          </div>
          <div className="space-y-1">
            <Label>Track</Label>
            <Select value={trackId} onValueChange={(v) => setTrackId(v ?? pkg.track_id)}>
              <SelectTrigger aria-label="Track">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(tracks.data ?? []).map((t) => (
                  <SelectItem key={t.id} value={t.id}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1">
            <Label>Mode</Label>
            <Select value={selectedMode} onValueChange={(value: string | null) => value && setMode(value as "blocks" | "tune")}>
              <SelectTrigger aria-label="Mode">
                <SelectValue>{(value: string | null) => (value === "tune" ? "Tune my resume" : "Build from blocks")}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tune" disabled={!hasResumeDocument}>
                  Tune my resume
                </SelectItem>
                <SelectItem value="blocks">Build from blocks</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          {taskId ? <TaskProgress taskId={taskId} jobId={job.id} onFinished={onFinished} /> : null}
          <div className="flex justify-end">
            <Button onClick={submit} disabled={tailor.isPending || taskId !== null}>
              Regenerate
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
