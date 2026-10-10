"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useQueryClient } from "@tanstack/react-query";
import { isSettingsSentence } from "@/lib/coach/errors";
import { readTaskEvents } from "@/lib/api/sse";
import { invalidateJobs } from "@/lib/api/queries";
import { POLL_STEPS, initialProgress, pipelineSteps, reduceTaskEvent, resolvePackageStatus, type ProgressState } from "@/lib/task-progress";

export function TaskProgress({
  taskId,
  jobId,
  onFinished,
  kind = "tailor",
}: {
  taskId: string;
  jobId: string;
  onFinished: (state: ProgressState) => void;
  kind?: "tailor" | "poll";
}) {
  const [state, setState] = useState<ProgressState>(initialProgress);
  const finished = useRef(false);
  const queryClient = useQueryClient();

  useEffect(() => {
    const controller = new AbortController();
    let current = initialProgress;
    let aborted = false;
    readTaskEvents(
      taskId,
      (event) => {
        current = reduceTaskEvent(current, event);
        setState(current);
      },
      controller.signal,
    )
      .catch((error: unknown) => {
        if (aborted || controller.signal.aborted || (error instanceof DOMException && error.name === "AbortError")) return;
        current = { ...current, status: "failed", error: error instanceof Error ? error.message : String(error) };
        setState(current);
      })
      .finally(async () => {
        if (aborted) return;
        if (finished.current) return;
        finished.current = true;
        if (kind === "poll") {
          if (current.status === "succeeded") {
            if (current.newJobs === null) {
              // Neither a "done" event nor a parsable state-replay result_ref gave a
              // count — don't claim zero when we don't actually know.
              toast.success("Poll finished");
            } else {
              toast.success(current.newJobs > 0 ? `Poll finished: ${current.newJobs} new jobs` : "Poll finished: no new jobs");
            }
          } else if (current.status === "failed") {
            toast.error(current.error ?? "Poll failed");
          } else if (current.status === "running") {
            // The stream ended without a terminal ("done"/"error") event.
            toast.error("Poll was interrupted; refresh to check for new jobs");
          }
        } else if (current.status === "succeeded" && current.packageId) {
          let packageStatus = current.packageStatus;
          if (packageStatus === null) {
            // The task was already finished when the SSE request landed: the API
            // replayed a bare "state" event (a TaskOut, with no package status)
            // and closed the stream. Resolve the real status before toasting so a
            // blocked package is never announced as ready.
            invalidateJobs(queryClient);
            packageStatus = await resolvePackageStatus(current.packageId);
            if (aborted) return;
            current = { ...current, packageStatus };
            setState(current);
          }
          const action = { label: "Review", onClick: () => window.location.assign(`/jobs/${jobId}/packages/${current.packageId}`) };
          if (packageStatus === "blocked") {
            toast.success("Package blocked by guardrails", { action });
          } else if (packageStatus) {
            toast.success("Package ready", { action });
          } else {
            // Neither the SSE event nor the fallback fetch could confirm the
            // package's guardrail status — don't claim it's clean.
            toast.success("Package created — open the review", { action });
          }
        } else if (current.status === "failed") {
          if (current.error && isSettingsSentence(current.error)) {
            toast.error(current.error, { action: { label: "Open Settings", onClick: () => window.location.assign("/settings") } });
          } else {
            toast.error(current.error ?? "Tailoring failed");
          }
        } else if (current.status === "running") {
          // The stream ended without a terminal ("done"/"error") event.
          toast.error("Tailoring was interrupted; refresh to check the job");
        }
        onFinished(current);
      });
    return () => {
      aborted = true;
      controller.abort();
    };
  }, [taskId, jobId, onFinished, queryClient, kind]);

  const steps: readonly string[] = kind === "poll" ? POLL_STEPS : pipelineSteps(state.mode);
  const activeIndex = state.step ? steps.indexOf(state.step) : -1;
  return (
    <div className="mt-3 space-y-2" aria-live="polite">
      <ol className="flex flex-wrap gap-2 text-xs">
        {steps.map((step, i) => {
          const done = state.status === "succeeded" || i < activeIndex;
          const active = i === activeIndex && state.status === "running";
          return (
            <li key={step} className={`rounded-full border px-2 py-0.5 ${done ? "border-fit-high/40 bg-fit-high-bg text-fit-high" : active ? "border-accent bg-accent/10 text-fit-high" : "border-border text-muted-foreground"}`}>
              {step}
            </li>
          );
        })}
      </ol>
      {state.status === "failed" ? (
        <p className="text-sm text-destructive">
          {state.error}
          {state.error && isSettingsSentence(state.error) ? (
            <>
              {" "}
              <Link href="/settings" className="underline">Open Settings</Link>
            </>
          ) : null}
        </p>
      ) : null}
      {kind === "tailor" && state.status === "succeeded" && state.packageId ? (
        <Link href={`/jobs/${jobId}/packages/${state.packageId}`} className="text-sm text-fit-high underline">
          Open package {state.packageStatus === "blocked" ? "(blocked)" : ""}
        </Link>
      ) : null}
    </div>
  );
}
