"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { readTaskEvents } from "@/lib/api/sse";
import { PIPELINE_STEPS, initialProgress, reduceTaskEvent, type ProgressState } from "@/lib/task-progress";

export function TaskProgress({ taskId, jobId, onFinished }: { taskId: string; jobId: string; onFinished: (state: ProgressState) => void }) {
  const [state, setState] = useState<ProgressState>(initialProgress);
  const finished = useRef(false);

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
      .finally(() => {
        if (aborted) return;
        if (finished.current) return;
        finished.current = true;
        if (current.status === "succeeded" && current.packageId) {
          toast.success(current.packageStatus === "blocked" ? "Package created, but guardrails blocked it" : "Package ready", {
            action: { label: "Review", onClick: () => window.location.assign(`/jobs/${jobId}/packages/${current.packageId}`) },
          });
        } else if (current.status === "failed") {
          toast.error(current.error ?? "Tailoring failed");
        }
        onFinished(current);
      });
    return () => {
      aborted = true;
      controller.abort();
    };
  }, [taskId, jobId, onFinished]);

  const activeIndex = state.step ? PIPELINE_STEPS.indexOf(state.step as (typeof PIPELINE_STEPS)[number]) : -1;
  return (
    <div className="mt-3 space-y-2" aria-live="polite">
      <ol className="flex flex-wrap gap-2 text-xs">
        {PIPELINE_STEPS.map((step, i) => {
          const done = state.status === "succeeded" || i < activeIndex;
          const active = i === activeIndex && state.status === "running";
          return (
            <li key={step} className={`rounded-full border px-2 py-0.5 ${done ? "border-green-300 bg-green-50 text-green-800" : active ? "border-accent bg-accent/10 text-accent" : "border-border text-muted-foreground"}`}>
              {step}
            </li>
          );
        })}
      </ol>
      {state.status === "failed" ? <p className="text-sm text-red-700">{state.error}</p> : null}
      {state.status === "succeeded" && state.packageId ? (
        <Link href={`/jobs/${jobId}/packages/${state.packageId}`} className="text-sm text-accent underline">
          Open package {state.packageStatus === "blocked" ? "(blocked)" : ""}
        </Link>
      ) : null}
    </div>
  );
}
