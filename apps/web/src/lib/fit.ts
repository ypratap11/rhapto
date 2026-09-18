import type { Tone } from "./status";

export function fitTone(fit: number | null, minFit: number | null): Tone {
  if (fit === null || minFit === null) return "neutral";
  if (fit >= 75) return "high";
  if (fit >= minFit) return "mid";
  return "neutral";
}

export function formatFit(fit: number | null): string {
  return fit === null ? "—" : String(fit);
}

// The chip shown on a job row for its location tier. "unknown" is deliberately absent: a tier the
// scorer could not read is not worth a chip, and neither is a job that has not been scored yet.
export const LOCATION_TIER_LABEL: Record<string, string> = {
  preferred: "Preferred area",
  remote: "Remote",
  country: "US",
  abroad: "Abroad",
};

export function locationTierLabel(tier: string | null | undefined): string | null {
  return (tier && LOCATION_TIER_LABEL[tier]) || null;
}

export const REGION_LABEL = {
  preferred: "Preferred area",
  us: "US and remote",
  any: "Anywhere",
} as const;

export const SOURCE_LABEL: Record<string, string> = {
  manual: "Pasted",
  url: "URL",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  remoteok: "RemoteOK",
  "hn-hiring": "HN",
  themuse: "The Muse",
  remotive: "Remotive",
  adzuna: "Adzuna",
  jooble: "Jooble",
  jsearch: "JSearch",
  workday: "Workday",
};
