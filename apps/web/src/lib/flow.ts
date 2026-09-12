import type { JobOut } from "./api/queries";

export const APPLIED_STATUSES = ["applied", "screen", "interview", "offer", "closed"] as const;
export type JobState = "tailor" | "review" | "applied";
export const FLOW_STEPS = ["Find", "Tailor", "Review", "Apply"] as const;

export function jobState(job: Pick<JobOut, "latest_package" | "application_status">): JobState {
  if (job.application_status && (APPLIED_STATUSES as readonly string[]).includes(job.application_status)) return "applied";
  return job.latest_package ? "review" : "tailor";
}

export function nextUp(jobs: JobOut[], skipped: string[], limit = 5): JobOut[] {
  const skip = new Set(skipped);
  return jobs
    .filter((j) => j.best_fit !== null && !skip.has(j.id) && jobState(j) !== "applied")
    .sort((a, b) => (b.best_fit ?? 0) - (a.best_fit ?? 0) || b.discovered_at.localeCompare(a.discovered_at))
    .slice(0, limit);
}

export function stepForPath(pathname: string, tailoring: boolean): 0 | 1 | 2 | 3 {
  if (pathname.startsWith("/pipeline")) return 3;
  if (/^\/jobs\/[^/]+\/packages\//.test(pathname)) return 2;
  return tailoring ? 1 : 0;
}

export function flowPrompt(input: { needsReview: number; next: JobOut | null }): { text: string; href: string } | null {
  if (input.needsReview > 0) {
    const n = input.needsReview;
    return { text: `${n} package${n === 1 ? "" : "s"} ready to review`, href: "/packages?filter=review" };
  }
  if (input.next) {
    const j = input.next;
    return { text: `Next: tailor ${j.company ?? "Unknown company"}, ${j.title ?? "Untitled role"} (fit ${j.best_fit ?? 0})`, href: `/#job-${j.id}` };
  }
  return null;
}
