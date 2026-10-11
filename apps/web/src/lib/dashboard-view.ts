import type { ApplicationOut, JobOut, PackageListItem } from "@/lib/api/queries";
import type { ChipId } from "@/lib/applications-view";
import { matchLabel } from "@/lib/coach/labels";
import { PICKER_MIN_FIT } from "@/lib/taxonomy";

/** How many recommended jobs the dashboard shows. "Strong matches" counts these rows, nothing else. */
export const RECOMMENDED_SHOWN = 5;

/** First word of the person's name, or "" when there is none. */
export function firstName(name: string | null | undefined): string {
  return name?.trim().split(/\s+/)[0] ?? "";
}

/** Before 12 morning, before 18 afternoon, else evening. Pure on purpose: the caller reads the clock.
 * The dashboard is never server-rendered (TokenGate renders nothing on the server), so reading the
 * browser's hour at render cannot cause a hydration mismatch. */
export function greeting(hour: number, name: string | null | undefined): string {
  const first = firstName(name);
  if (!first) return "Welcome back";
  const part = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "evening";
  return `Good ${part}, ${first}`;
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** Built only from counts that are true. `null` means "not known yet or failed to load": that clause is left out. */
export function summaryLine({ strong, review }: { strong: number | null; review: number | null }): string {
  const s = strong && strong > 0 ? `${strong} strong ${plural(strong, "match is", "matches are")} waiting` : null;
  const r = review && review > 0 ? `${review} ${plural(review, "resume is", "resumes are")} ready for your review` : null;
  if (s && r) return `${s}, and ${r}.`;
  if (s || r) return `${s ?? r}.`;
  return "Here's where your search stands.";
}

type TrackFit = { id: string; min_fit: number };

/** Strong matches among the rows actually shown, by each job's own track `min_fit` (same rule as `matchLabel`).
 * `null` until the tracks have loaded, so the fallback threshold never flashes a different number. */
export function strongMatchCount(jobs: JobOut[], tracks: TrackFit[] | undefined): number | null {
  if (!tracks) return null;
  return jobs
    .slice(0, RECOMMENDED_SHOWN)
    .filter((j) => matchLabel(j.best_fit, tracks.find((t) => t.id === j.best_track_id)?.min_fit ?? PICKER_MIN_FIT) === "Strong match").length;
}

/** Found within the last 24 hours (23 h yes, 24 h no). */
export function isNewToday(discoveredAt: string, now: Date = new Date()): boolean {
  const age = now.getTime() - new Date(discoveredAt).getTime();
  return age >= 0 && age < 24 * 3_600_000; // a timestamp in the future is not "new today"
}

const WEEK_MS = 7 * 86_400_000;

/** The one application worth asking about: still just "applied", sent a week or more ago, no follow-up date.
 * Oldest first. Null when nothing qualifies, so the tip never shows untrue. */
export function followUpTip(rows: ApplicationOut[], now: Date = new Date()): ApplicationOut | null {
  const due = rows
    .filter((r) => r.status === "applied" && r.applied_at && !r.follow_up_at && now.getTime() - new Date(r.applied_at).getTime() >= WEEK_MS)
    .sort((a, b) => (a.applied_at ?? "").localeCompare(b.applied_at ?? ""));
  return due[0] ?? null;
}

type Counts = Record<ChipId, number>;

export const BAR_ORDER = ["applied", "interviewing", "offer", "closed"] as const;
export type BarId = (typeof BAR_ORDER)[number];

export function barSegments(counts: Counts): { id: BarId; count: number; percent: number }[] {
  const total = BAR_ORDER.reduce((n, id) => n + counts[id], 0);
  if (total === 0) return [];
  return BAR_ORDER.filter((id) => counts[id] > 0).map((id) => ({ id, count: counts[id], percent: (counts[id] / total) * 100 }));
}

export function barLabel(counts: Counts): string {
  return `${counts.applied} applied, ${counts.interviewing} interviewing, ${counts.offer} ${plural(counts.offer, "offer", "offers")}, ${counts.closed} closed`;
}

export type TileId = "review" | "applied" | "interviewing" | "offer";

/** One plain line under each tile's number. */
export function tileHint(tile: TileId, n: number): string {
  switch (tile) {
    case "review":
      return n > 0 ? "Tailored, not sent yet" : "Nothing waiting";
    case "applied":
      return n > 0 ? "Waiting to hear back" : "Nothing sent yet";
    case "interviewing":
      return n > 0 ? `${n} in progress` : "Nothing scheduled";
    case "offer":
      return n > 0 ? "Congratulations" : "Keep going";
  }
}

type LoadState = "loading" | "error" | "ready";
export type NextDraft = Pick<PackageListItem, "id" | "job_id" | "company" | "title" | "best_fit">;
export type NextFollowUp = { applicationId: string; company: string | null; title: string | null };

export type NextStep =
  | { kind: "loading" }
  | { kind: "review"; draft: NextDraft }
  | { kind: "review-list" }
  | ({ kind: "followup" } & NextFollowUp)
  | { kind: "tailor"; job: JobOut }
  | null;

/** The first step that applies: 1 review the newest draft, 2 a due follow-up, 3 tailor the top job, 4 none.
 * While what a higher step needs is still loading it answers "loading" rather than dropping to a lower step,
 * so a wrong card never flashes. */
export function pickNextStep(i: {
  dashboard: LoadState;
  reviewCount: number;
  drafts: LoadState;
  newestDraft: NextDraft | undefined;
  dueFollowUp: NextFollowUp | null;
  jobs: LoadState;
  topJob: JobOut | undefined;
}): NextStep {
  if (i.dashboard === "loading") return { kind: "loading" };
  if (i.dashboard === "ready" && i.reviewCount > 0) {
    if (i.drafts === "loading") return { kind: "loading" };
    if (i.drafts === "ready" && i.newestDraft) return { kind: "review", draft: i.newestDraft };
    return { kind: "review-list" };
  }
  if (i.dueFollowUp) return { kind: "followup", ...i.dueFollowUp };
  if (i.jobs === "loading") return { kind: "loading" };
  if (i.topJob) return { kind: "tailor", job: i.topJob };
  return null;
}
