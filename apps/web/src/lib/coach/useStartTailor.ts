"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { useTailor, type JobOut } from "@/lib/api/queries";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { fireCoachEvent } from "@/lib/coach/events";

export type TailorStarter = {
  /** Starts a "tune" run for the job and goes to the coach. One at a time: a second call while one is running is ignored. */
  start: (job: JobOut) => Promise<void>;
  /** The job whose run is starting, or null. Buttons disable while this is set. */
  pickedId: string | null;
  /** Why the last start failed, in plain words, with the job it was for. */
  error: CoachError | null;
  failedJobId: string | null;
};

/**
 * The Tailor button's whole flow, shared: lock against a double tap, start the task, tell the coach, go to
 * /start?task=. The Dashboard calls this once and hands the result to both the next-step card and the
 * recommended rows, so the two can never start two runs at once.
 */
export function useStartTailor(): TailorStarter {
  const router = useRouter();
  const tailor = useTailor();
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [failed, setFailed] = useState<{ jobId: string; error: CoachError } | null>(null);
  const lock = useRef(false);

  async function start(job: JobOut) {
    if (lock.current) return; // one task per tap: a double click must not claim two runs
    lock.current = true;
    setPickedId(job.id);
    setFailed(null);
    try {
      const task = await tailor.mutateAsync({ jobId: job.id, body: { mode: "tune" } });
      void fireCoachEvent("tailor_started");
      router.push(`/start?task=${task.id}`);
    } catch (e) {
      setFailed({ jobId: job.id, error: describeCoachError(e, "tailor") });
      setPickedId(null);
      lock.current = false;
    }
  }

  return { start, pickedId, error: failed?.error ?? null, failedJobId: failed?.jobId ?? null };
}
