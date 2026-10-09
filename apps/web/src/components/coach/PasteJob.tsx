"use client";

import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useCreateJob } from "@/lib/api/queries";
import { describeCoachError, type CoachError } from "@/lib/coach/errors";
import { CoachErrorNote, CoachFrame, type TranscriptItem } from "./CoachFrame";

const MIN_CHARS = 50; // the API's own floor for jd_text

export function PasteJob({
  transcript,
  error: parentError,
  onJob,
  onCancel,
}: {
  transcript?: TranscriptItem[];
  /** A refusal from starting the tailor (the parent swallows it so double-tap guards unlock). */
  error?: CoachError | null;
  onJob: (jobId: string) => Promise<void>;
  onCancel: () => void;
}) {
  const create = useCreateJob();
  const [text, setText] = useState("");
  const [error, setError] = useState<CoachError | null>(null);
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);

  async function submit() {
    if (lock.current) return;
    const jd = text.trim();
    if (jd.length < MIN_CHARS) {
      setError({ message: "Paste the whole job description (at least 50 characters).", next: "paste" });
      return;
    }
    lock.current = true;
    setBusy(true);
    setError(null);
    try {
      let id: string;
      try {
        id = (await create.mutateAsync({ jd_text: jd })).id;
      } catch (e) {
        // The same description was added before: use that job instead of failing.
        const existing = e instanceof ApiError && e.status === 409 ? e.problem?.existing_job_id : undefined;
        if (typeof existing !== "string") throw e;
        id = existing;
      }
      await onJob(id);
    } catch (e) {
      setError(describeCoachError(e, "jobs"));
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  return (
    <CoachFrame title="Paste a job" hint="Paste the full text of the job description." transcript={transcript}>
      <CoachErrorNote error={error ?? parentError ?? null} />
      <label htmlFor="coach-jd" className="text-sm font-medium">
        Job description
      </label>
      <textarea
        id="coach-jd"
        rows={10}
        value={text}
        onChange={(event) => setText(event.target.value)}
        className="w-full rounded-control border border-border bg-background p-3 text-sm"
      />
      <div className="flex gap-3">
        <Button type="button" disabled={busy} onClick={() => void submit()}>
          Use this job
        </Button>
        <Button type="button" variant="outline" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </CoachFrame>
  );
}
