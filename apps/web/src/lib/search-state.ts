import type { SearchBody } from "./api/portal";

export type Remote = "include" | "only" | "exclude";
export type PostedWithin = "24h" | "7d" | "30d" | "any";
export type FitFilter = "75" | "60" | "all";

/** Everything the search form and the filter chips hold between them. One object so the Jobs page,
 * the Dashboard card, the URL and "Save this search" all speak the same shape (spec §6). */
export type SearchState = {
  query: string;
  location: string;
  remote: Remote;
  /** Taxonomy field id, or null for "My tracks" — the default (spec §5). */
  field: string | null;
  posted_within: PostedWithin;
  sources: string[];
  /** Client-side only: the API has no fit filter, and an unscored job must stay visible. */
  fit: FitFilter;
  sort: "fit" | "newest";
  hidden: boolean;
};

export const DEFAULT_SEARCH_STATE: SearchState = {
  query: "",
  location: "",
  remote: "include",
  field: null,
  posted_within: "any",
  sources: [],
  fit: "all",
  sort: "fit",
  hidden: false,
};

export function toSearchBody(s: SearchState): SearchBody {
  return {
    query: s.query.trim(),
    ...(s.location.trim() ? { location: s.location.trim() } : {}),
    remote: s.remote,
    ...(s.field ? { field: s.field } : {}),
    ...(s.posted_within !== "any" ? { posted_within: s.posted_within } : {}),
    ...(s.sources.length > 0 ? { sources: s.sources } : {}),
  } as SearchBody;
}

/** GET /jobs takes comma-separated lists, not repeated keys. */
export function toJobsQuery(s: SearchState, ids?: string[]): Record<string, string> {
  return {
    sort: s.sort,
    ...(ids && ids.length > 0 ? { ids: ids.join(",") } : {}),
    ...(s.posted_within !== "any" ? { posted_within: s.posted_within } : {}),
    ...(s.sources.length > 0 ? { sources: s.sources.join(",") } : {}),
    ...(s.field ? { field: s.field } : {}),
    ...(s.hidden ? { hidden: "true" } : {}),
  };
}

export function passesFit(fit: number | null, filter: FitFilter): boolean {
  // A job that has not been scored yet is not a low-fit job: hiding it would empty the grid for
  // the three seconds between the search returning and the worker catching up (spec §6).
  if (filter === "all" || fit === null) return true;
  return fit >= Number(filter);
}

const REMOTE: Remote[] = ["include", "only", "exclude"];
const POSTED: PostedWithin[] = ["24h", "7d", "30d", "any"];
const FITS: FitFilter[] = ["75", "60", "all"];

function pick<T extends string>(value: string | null, allowed: T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback;
}

export function encodeSearchState(s: SearchState): URLSearchParams {
  const p = new URLSearchParams();
  if (s.query) p.set("q", s.query);
  if (s.location) p.set("location", s.location);
  if (s.remote !== "include") p.set("remote", s.remote);
  if (s.field) p.set("field", s.field);
  if (s.posted_within !== "any") p.set("posted", s.posted_within);
  if (s.sources.length > 0) p.set("sources", s.sources.join(","));
  if (s.fit !== "all") p.set("fit", s.fit);
  if (s.sort !== "fit") p.set("sort", s.sort);
  if (s.hidden) p.set("hidden", "true");
  return p;
}

export function decodeSearchState(p: URLSearchParams): SearchState {
  const sources = p.get("sources");
  return {
    query: p.get("q") ?? "",
    location: p.get("location") ?? "",
    remote: pick(p.get("remote"), REMOTE, "include"),
    field: p.get("field"),
    posted_within: pick(p.get("posted"), POSTED, "any"),
    sources: sources ? sources.split(",").filter(Boolean) : [],
    fit: pick(p.get("fit"), FITS, "all"),
    sort: p.get("sort") === "newest" ? "newest" : "fit",
    hidden: p.get("hidden") === "true",
  };
}
