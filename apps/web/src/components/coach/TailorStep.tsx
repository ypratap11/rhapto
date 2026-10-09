"use client";

import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { readTaskEvents } from "@/lib/api/sse";
import { COACH_QUEUE_NOTICE_MS } from "@/lib/coach/constants";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { initialProgress, reduceTaskEvent, type ProgressState } from "@/lib/task-progress";
import { CoachErrorNote, CoachFrame, type TranscriptItem } from "./CoachFrame";

// The engine's step names are not for the tester (spec: no technical screen).
const WORDS: Record<string, string> = {
  extract: "Reading the job",
  tune: "Rewriting your resume for it",
  validate: "Checking every line against your resume",
  repair: "Fixing one thing the check caught",
  render: "Preparing your file",
};
const ORDER = ["extract", "tune", "validate", "repair", "render"] as const;

export function TailorStep({
  taskId,
  transcript,
  onDone,
  onRetry,
  onPickAnother,
  error = null,
}: {
  taskId: string;
  transcript?: TranscriptItem[];
  onDone: (packageId: string) => void;
  /** May return the start's promise: the button stays disabled until it settles. */
  onRetry: () => void | Promise<void>;
  onPickAnother: () => void;
  /** Why the last retry was refused (trial used up, no key, no access, offline), in plain words. */
  error?: CoachError | null;
}) {
  const [state, setState] = useState<ProgressState>(initialProgress);
  const [slow, setSlow] = useState(false);
  const [lost, setLost] = useState(false);
  // A retry claims a paid run, so a double tap must start one: the ref locks synchronously (two clicks
  // in one frame both see `retrying === false`), the state disables the button for everyone to see.
  const retryLock = useRef(false);
  const [retrying, setRetrying] = useState(false);
  async function retry() {
    if (retryLock.current) return;
    retryLock.current = true;
    setRetrying(true);
    try {
      await onRetry();
    } finally {
      retryLock.current = false;
      setRetrying(false);
    }
  }

  // `onDone` is read through a ref, so a parent that forgets `useCallback` cannot restart the stream.
  const done = useRef(onDone);
  useEffect(() => {
    done.current = onDone;
  });

  useEffect(() => {
    const controller = new AbortController();
    let current = initialProgress;
    let handedOn = false;
    const timer = setTimeout(() => setSlow(true), COACH_QUEUE_NOTICE_MS);
    readTaskEvents(
      taskId,
      (event) => {
        current = reduceTaskEvent(current, event);
        setState(current);
      },
      controller.signal,
    )
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        current = { ...current, status: "failed", error: error instanceof Error ? error.message : String(error) };
        setState(current);
      })
      .finally(() => {
        if (controller.signal.aborted) return;
        if (current.status === "succeeded" && current.packageId && !handedOn) {
          handedOn = true;
          done.current(current.packageId);
        } else if (current.status === "running" || current.status === "idle") {
          setLost(true); // the stream ended with no verdict; the task id is in the URL, so a reload re-attaches
        }
      });
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [taskId]);

  const active = state.step ? ORDER.indexOf(state.step as (typeof ORDER)[number]) : -1;
  const showQueue = slow && state.step === null && state.status !== "failed";

  return (
    <CoachFrame title="Tailoring your resume" hint="This usually takes under a minute." transcript={transcript}>
      <ol aria-live="polite" className="space-y-1 text-sm">
        {ORDER.filter((s) => s !== "repair" || state.step === "repair").map((step) => {
          const index = ORDER.indexOf(step);
          const isDone = state.status === "succeeded" || (active > index);
          const isActive = active === index && state.status === "running";
          return (
            <li key={step} className={isActive ? "font-medium text-foreground" : isDone ? "text-muted-foreground line-through" : "text-muted-foreground"}>
              {WORDS[step]}
            </li>
          );
        })}
      </ol>
      {showQueue ? <p role="status" className="text-sm text-muted-foreground">Still working, others are ahead of you</p> : null}
      {lost ? <p className="text-sm text-muted-foreground">We lost the connection. Reload this page to pick up where you left off.</p> : null}
      {state.status === "failed" ? (
        <>
          <CoachErrorNote error={error ?? describeCoachError(new Error(state.error ?? "The run failed"), "tailor")} />
          <div className="flex flex-wrap gap-3">
            <Button type="button" disabled={retrying} onClick={() => void retry()}>Try again</Button>
            <Button type="button" variant="outline" onClick={onPickAnother}>Pick another job</Button>
          </div>
        </>
      ) : null}
    </CoachFrame>
  );
}
