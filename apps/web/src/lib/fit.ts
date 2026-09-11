import type { Tone } from "./status";

export function fitTone(fit: number | null, minFit: number | null): Tone {
  if (fit === null || minFit === null) return "slate";
  if (fit >= 75) return "green";
  if (fit >= minFit) return "amber";
  return "slate";
}

export function formatFit(fit: number | null): string {
  return fit === null ? "—" : String(fit);
}

export const SOURCE_LABEL: Record<string, string> = {
  manual: "Pasted",
  url: "URL",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  remoteok: "RemoteOK",
  "hn-hiring": "HN",
};
