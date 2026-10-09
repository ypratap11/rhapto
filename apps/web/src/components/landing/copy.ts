/** The number of free AI runs the server grants, from the build arg `NEXT_PUBLIC_TRIAL_RUNS` (compose
 * sources it from `RHAPTO_TRIAL_RUNS`, the variable the API reads, so the two cannot drift). Returns a
 * positive integer, or null when no honest number exists: unset, not a number, negative (the cap is
 * disabled) or 0 (this instance offers no free runs). The reference is a literal `process.env.X` so
 * Next inlines it at build time; tests set it with `vi.stubEnv`. */
export function freeRuns(): number | null {
  const raw = process.env.NEXT_PUBLIC_TRIAL_RUNS;
  if (raw === undefined || raw.trim() === "") return null;
  const n = Number(raw);
  return Number.isInteger(n) && n > 0 ? n : null;
}

function noFreeRuns(): boolean {
  const raw = process.env.NEXT_PUBLIC_TRIAL_RUNS;
  return raw !== undefined && raw.trim() !== "" && Number(raw) === 0;
}

export function pricingLine(hosted: boolean): string {
  if (!hosted) return "Free and open source (AGPL-3.0); you use your own AI key.";
  if (noFreeRuns()) return "Bring your own AI key. A paid plan with AI usage included is coming.";
  const n = freeRuns();
  const runs = n === null ? "a few AI runs" : `${n} AI runs`;
  return `Free during the beta: ${runs} on us (your first resume import is free), then use your own AI key. A paid plan with AI usage included is coming.`;
}

/** The muted line under the hero button. */
export function freeLimitLine(hosted: boolean): string {
  if (!hosted) return "Free and open source (AGPL-3.0); you use your own AI key.";
  if (noFreeRuns()) return "Bring your own AI key to use Rhapto.";
  const n = freeRuns();
  const runs = n === null ? "a few AI runs" : `${n} AI runs`;
  return `Free during the beta: your first resume import and ${runs} are on us, then you use your own AI key.`;
}
