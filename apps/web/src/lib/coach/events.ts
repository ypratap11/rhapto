import { apiUrl, authHeaders } from "@/lib/api/client";

export type CoachEventStep = "started" | "resume_in" | "role_confirmed" | "jobs_shown" | "tailor_started" | "downloaded";

/** Fire and forget. Counts only, server-side idempotent per (user, step, UTC day), and a failure here
 * must never reach the tester: this never rejects. */
export async function fireCoachEvent(step: CoachEventStep): Promise<void> {
  try {
    await fetch(apiUrl("/api/v1/coach/events"), {
      method: "POST",
      headers: { ...authHeaders(), "content-type": "application/json" },
      body: JSON.stringify({ step }),
    });
  } catch {
    /* an event we could not send is a data point we lose, not an error to show */
  }
}
