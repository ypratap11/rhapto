/** How often step 3 asks again while a rescore is pending. */
export const COACH_POLL_MS = 3000;
/** After this long without a result, offer "Paste a job you like instead" (and keep polling).
 * Measured on a scratch restore (Task 12, timing-report.md): the coach's answers-then-track
 * sequence took a median 105 s (max 109 s) to a final list on the largest account; median + 10 s,
 * rounded up to 5 s. */
export const COACH_OFFER_PASTE_MS = 115_000;
export const COACH_TOP_N = 5;
/** A tailor task that has not reported a step after this long is probably queued behind others
 * (the worker runs two jobs at a time). */
export const COACH_QUEUE_NOTICE_MS = 20_000;
