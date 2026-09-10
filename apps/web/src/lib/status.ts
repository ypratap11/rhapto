export const APPLICATION_STATUSES = ["discovered", "queued", "applied", "screen", "interview", "offer", "closed"] as const;
export type ApplicationStatus = (typeof APPLICATION_STATUSES)[number];

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  discovered: "Discovered",
  queued: "Queued",
  applied: "Applied",
  screen: "Screen",
  interview: "Interview",
  offer: "Offer",
  closed: "Closed",
};

export type Tone = "slate" | "amber" | "green" | "zinc" | "red" | "indigo";

export function statusTone(status: string): Tone {
  switch (status) {
    case "applied":
      return "green";
    case "screen":
    case "interview":
      return "indigo";
    case "offer":
      return "amber";
    case "closed":
      return "zinc";
    default:
      return "slate";
  }
}

export const PACKAGE_STATUS_TONE: Record<string, Tone> = { draft: "slate", blocked: "amber" };
export const TASK_STATUS_TONE: Record<string, Tone> = { queued: "slate", running: "indigo", succeeded: "green", failed: "red" };
