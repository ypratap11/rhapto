"use client";

import { useState } from "react";
import { useSubmitFeedback } from "@/lib/api/queries";
import type { PageArea } from "@/lib/feedback";

/** The fixed text that marks a request in the feedback table, so the owner can count them. Pricing
 * waits on this number; there is no way to pay yet, so nothing on this control promises more runs. */
export const WANT_MORE_RUNS_TEXT = "Wants more resumes after the free runs (prompt at the cap)";

/** One tap at the free-run cap: records that this person wanted more. Reuses the insert-only feedback route. */
export function WantMoreRuns({ area }: { area: PageArea }) {
  const submit = useSubmitFeedback();
  const [state, setState] = useState<"idle" | "sent" | "failed">("idle");

  async function send() {
    try {
      await submit.mutateAsync({ form: "quick", page_area: area, answers: { kind: "idea", text: WANT_MORE_RUNS_TEXT } });
      setState("sent");
    } catch {
      setState("failed");
    }
  }

  if (state === "sent") {
    return <p role="status" className="mt-1 text-sm text-muted-foreground">Thanks. We&apos;ve noted that you&apos;d like more.</p>;
  }
  return (
    <p className="mt-1 text-sm">
      <button
        type="button"
        onClick={() => void send()}
        disabled={submit.isPending}
        className="inline-flex min-h-11 items-center text-primary underline underline-offset-4 disabled:opacity-60"
      >
        Want more resumes? Tell us
      </button>
      {state === "failed" ? <span role="alert" className="ml-2 text-muted-foreground">That didn&apos;t send. Try again in a moment.</span> : null}
    </p>
  );
}
