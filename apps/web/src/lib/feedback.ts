import type { components } from "@/lib/api/schema";

export type FeedbackIn = components["schemas"]["FeedbackIn"];
export type FeedbackQuickAnswers = components["schemas"]["QuickAnswers"];
export type PageArea = NonNullable<FeedbackIn["page_area"]>;

/** Where the shell feedback button stays out of the way: the pitch pages and the survey itself. */
export const FEEDBACK_HIDDEN_ROUTES: ReadonlySet<string> = new Set(["/", "/about", "/feedback"]);

const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
const CONTEXT = new RegExp(`^/jobs/(${UUID})(?:/packages/(${UUID}))?(?:/|$)`, "i");

function normalise(pathname: string): string {
  return pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
}

// First match wins, so the longer review route is listed before /jobs/{id}.
const AREA_RULES: ReadonlyArray<readonly [RegExp, PageArea]> = [
  [/^\/dashboard$/, "dashboard"],
  [/^\/jobs$/, "jobs"],
  [/^\/jobs\/[^/]+\/packages\/[^/]+$/, "review"],
  [/^\/jobs\/[^/]+$/, "job_detail"],
  [/^\/resumes$/, "resumes"],
  [/^\/pipeline(?:\/board)?$/, "pipeline"],
  [/^\/profile$/, "profile"],
  [/^\/settings$/, "settings"],
];

export function areaForPath(pathname: string): PageArea {
  const path = normalise(pathname);
  for (const [re, area] of AREA_RULES) if (re.test(path)) return area;
  return "other";
}

/** Ids of the job and package a page is showing; only well-formed UUID segments count. */
export function contextForPath(pathname: string): { job_id?: string; package_id?: string } {
  const m = CONTEXT.exec(normalise(pathname));
  if (!m) return {};
  return m[2] ? { job_id: m[1], package_id: m[2] } : { job_id: m[1] };
}
