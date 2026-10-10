import type { ApplicationOut } from "@/lib/api/queries";
import { CLOSED_REASON_LABEL, STATUS_LABEL, type ApplicationStatus, type ClosedReason } from "@/lib/status";

export const CHIP_IDS = ["applied", "interviewing", "offer", "closed", "all"] as const;
export type ChipId = (typeof CHIP_IDS)[number];

export const CHIP_LABEL: Record<ChipId, string> = {
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  closed: "Closed",
  all: "All",
};

const CHIP_OF: Record<string, Exclude<ChipId, "all">> = {
  applied: "applied",
  screen: "applied",
  interview: "interviewing",
  offer: "offer",
  closed: "closed",
};

const CHIPS = new Map<string, Exclude<ChipId, "all">>(Object.entries(CHIP_OF));
// `noUncheckedIndexedAccess` is on; a Map also has no prototype keys ("constructor").
const chipOf = (status: string): Exclude<ChipId, "all"> | null => CHIPS.get(status) ?? null;

/** `discovered` and `queued` are jobs, not applications. */
export const isApplication = (a: Pick<ApplicationOut, "status">): boolean => chipOf(a.status) !== null;

/** When the status last changed. `updated_at` also moves when notes are edited, so prefer the history. */
export function lastChange(a: Pick<ApplicationOut, "updated_at" | "status_history">): string {
  const times = (a.status_history ?? []).map((h) => h.at);
  // The API appends, but taking the latest does not depend on that.
  return times.length > 0 ? times.reduce((x, y) => (y > x ? y : x)) : a.updated_at;
}

export function chipCounts(rows: ApplicationOut[]): Record<ChipId, number> {
  const counts: Record<ChipId, number> = { applied: 0, interviewing: 0, offer: 0, closed: 0, all: 0 };
  for (const r of rows) {
    const chip = chipOf(r.status);
    if (chip) {
      counts[chip] += 1;
      counts.all += 1;
    }
  }
  return counts;
}

export function rowsForChip(rows: ApplicationOut[], chip: ChipId): ApplicationOut[] {
  return rows
    .filter((r) => chip === "all" || chipOf(r.status) === chip)
    .sort((a, b) => lastChange(b).localeCompare(lastChange(a)));
}

export function statusWords(a: Pick<ApplicationOut, "status" | "closed_reason">): string {
  if (a.status === "closed" && a.closed_reason && a.closed_reason in CLOSED_REASON_LABEL) {
    return CLOSED_REASON_LABEL[a.closed_reason as ClosedReason];
  }
  return STATUS_LABEL[a.status as ApplicationStatus] ?? a.status;
}
