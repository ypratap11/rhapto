export const APPLICATION_STATUSES = ["discovered", "queued", "applied", "screen", "interview", "offer", "closed"] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  discovered: "Discovered",
  queued: "Queued",
  applied: "Applied",
  screen: "Screening",
  interview: "Interviewing",
  offer: "Offer",
  closed: "Closed",
};

/** Status-pill tones, named for the token they paint with (spec §8: fit and primary tokens only). */
export type Tone = "neutral" | "muted" | "high" | "mid" | "primary" | "danger";

export function statusTone(status: string): Tone {
  switch (status) {
    case "applied":
      return "high";
    case "screen":
    case "interview":
      return "primary";
    case "offer":
      return "mid";
    case "closed":
      return "muted";
    default:
      return "neutral";
  }
}

export const PACKAGE_STATUS_TONE: Record<string, Tone> = { draft: "neutral", ready: "high", blocked: "mid" };
export const TASK_STATUS_TONE: Record<string, Tone> = { queued: "neutral", running: "primary", succeeded: "high", failed: "danger" };

/** Spec §4: a closed application always says why, so the Closed-reasons chart (§13) has data later. */
export const CLOSED_REASONS = ["rejected", "withdrew", "no_response", "filled"] as const;
export type ClosedReason = (typeof CLOSED_REASONS)[number];
export const CLOSED_REASON_LABEL: Record<ClosedReason, string> = {
  rejected: "Rejected",
  withdrew: "Withdrew",
  no_response: "No response",
  filled: "Position filled",
};

/** The five tabs the Pipeline groups by; `discovered`/`queued` never reach this page. */
export const PIPELINE_STATUSES = ["applied", "screen", "interview", "offer", "closed"] as const;
export type PipelineStatus = (typeof PIPELINE_STATUSES)[number];
