"use client";

import { StatTile } from "@/components/ui/stat-tile";
import type { ChipId } from "@/lib/applications-view";
import { tileHint } from "@/lib/dashboard-view";

type Counts = Record<ChipId, number>;

/**
 * The four hero tiles. To review links to the My resumes review tab; Applied, Interviewing and Offers are
 * toggles for the applications filter (pressing the one that is on turns the filter off).
 * `reviewCount` null: the dashboard failed to load, so it says so instead of showing an untrue 0.
 * `counts` null: the applications failed to load, same reason.
 */
export function DashboardTiles({
  reviewCount,
  counts,
  chip,
  onChip,
}: {
  reviewCount: number | null;
  counts: Counts | null;
  chip: ChipId;
  onChip: (chip: Exclude<ChipId, "all" | "closed">) => void;
}) {
  const n = (id: "applied" | "interviewing" | "offer") => counts?.[id] ?? null;
  const tile = (id: "applied" | "interviewing" | "offer", tone: "mint" | "blue" | "amber", label: string) => {
    const count = n(id);
    return (
      <StatTile
        tone={tone}
        value={count ?? "–"}
        label={label}
        hint={count === null ? "Couldn't load" : tileHint(id, count)}
        muted={!count}
        pressed={chip === id}
        onClick={() => onChip(id)}
      />
    );
  };
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        tone="peach"
        value={reviewCount ?? "–"}
        label="To review"
        hint={reviewCount === null ? "Couldn't load" : tileHint("review", reviewCount)}
        muted={!reviewCount}
        href="/resumes?tab=review"
      />
      {tile("applied", "mint", "Applied")}
      {tile("interviewing", "blue", "Interviewing")}
      {tile("offer", "amber", "Offers")}
    </div>
  );
}
