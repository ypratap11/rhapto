"use client";

import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ApplicationOut } from "@/lib/api/queries";
import { CHIP_LABEL, type ChipId, chipCounts, lastChange, rowsForChip, statusWords } from "@/lib/applications-view";
import { barLabel, barSegments, followUpTip, type BarId } from "@/lib/dashboard-view";
import { formatDate, formatDaysAgo } from "@/lib/format";
import { statusTone } from "@/lib/status";
import { cn } from "cn";

const PAGE = 6;

const BAR_COLOR: Record<BarId, string> = {
  applied: "bg-fit-high",
  interviewing: "bg-tone-blue",
  offer: "bg-fit-mid",
  closed: "bg-muted-foreground",
};
const LEGEND: Record<BarId, string> = { applied: "Applied", interviewing: "Interviewing", offer: "Offer", closed: "Closed" };

/** "Applied 29 Sep 2026 · 12 days ago", or "Updated ..." when there is no applied date. */
function dateLine(a: ApplicationOut, now: Date): string {
  if (a.applied_at) return `Applied ${formatDate(a.applied_at)} · ${formatDaysAgo(a.applied_at, now)}`;
  const at = lastChange(a);
  return `Updated ${formatDate(at)} · ${formatDaysAgo(at, now)}`;
}

/**
 * The right column: a stacked bar of where applications stand, the list (six rows, then all), and a tip
 * only when a reply is probably due. The filter (`chip`) and the open application are the page's, so the
 * hero tiles and the next-step card can drive them: `onChipChange` sets the filter, `onSelect` opens the
 * one application sheet the page keeps.
 * `rows`: real applications only. `dueIds`: application ids whose follow-up is due today or overdue.
 */
export function ApplicationsSection({
  rows,
  dueIds,
  chip,
  onChipChange,
  onSelect,
}: {
  rows: ApplicationOut[];
  dueIds?: ReadonlySet<string>;
  chip: ChipId;
  onChipChange: (chip: ChipId) => void;
  onSelect: (id: string) => void;
}) {
  // "Show all" belongs to the filter it was pressed under; changing the filter folds the list again.
  const [expandedFor, setExpandedFor] = useState<ChipId | null>(null);
  const counts = useMemo(() => chipCounts(rows), [rows]);
  const segments = useMemo(() => barSegments(counts), [counts]);
  const visible = useMemo(() => rowsForChip(rows, chip), [rows, chip]);
  const showAll = expandedFor === chip;
  const shown = showAll ? visible : visible.slice(0, PAGE);
  const now = new Date();
  const tip = followUpTip(rows, now);

  return (
    <section aria-labelledby="applications-heading" className="space-y-3">
      <h2 id="applications-heading" className="font-serif text-xl font-semibold">
        Your applications
      </h2>
      <div className="rounded-2xl border border-border bg-surface p-4">
        <div role="img" aria-label={barLabel(counts)} className="mb-3.5 flex h-2 overflow-hidden rounded-full bg-muted">
          {segments.map((s) => (
            <span key={s.id} className={cn("block h-full", BAR_COLOR[s.id])} style={{ width: `${s.percent}%` }} />
          ))}
        </div>
        <ul aria-hidden className="flex flex-wrap gap-x-3 gap-y-1 text-[0.8rem] text-muted-foreground">
          {(["applied", "interviewing", "offer", "closed"] as const).map((id) => (
            <li key={id} className="flex items-center gap-1.5">
              <span className={cn("size-2 rounded-[2px]", BAR_COLOR[id])} />
              {LEGEND[id]} {counts[id]}
            </li>
          ))}
        </ul>
        {chip !== "all" ? (
          <p className="mt-3 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            Showing: <span className="font-medium text-foreground">{CHIP_LABEL[chip]}</span> ·
            <Button type="button" variant="link" aria-label="Show all applications" className="px-0 max-md:min-h-11" onClick={() => onChipChange("all")}>
              Show all
            </Button>
          </p>
        ) : null}
        {shown.length === 0 ? (
          <p className="mt-3 rounded-card border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">Nothing here yet.</p>
        ) : (
          <ul className="mt-3 divide-y divide-border">
            {shown.map((a) => (
              <li key={a.id}>
                <button
                  type="button"
                  onClick={() => onSelect(a.id)}
                  className="flex min-h-14 w-full items-center gap-3 rounded-control py-3 text-left outline-none hover:bg-surface-muted focus-visible:ring-3 focus-visible:ring-ring/50"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-semibold">{a.job.company ?? "Unknown company"}</span>
                    <span className="block truncate text-sm text-muted-foreground">{a.job.title ?? "Untitled role"}</span>
                    <span className="block text-xs text-muted-foreground">{dateLine(a, now)}</span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1">
                    {dueIds?.has(a.id) ? <StatusBadge tone="mid">Follow up</StatusBadge> : null}
                    <StatusBadge tone={statusTone(a.status)}>{statusWords(a)}</StatusBadge>
                  </span>
                  <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        {!showAll && visible.length > PAGE ? (
          <Button type="button" variant="ghost" className="mt-2 max-md:min-h-11" onClick={() => setExpandedFor(chip)}>
            Show all {visible.length}
          </Button>
        ) : null}
      </div>
      {tip ? (
        <div className="rounded-2xl bg-band-mint p-4 text-foreground">
          <p className="font-semibold">Heard back from {tip.job.company ?? "this company"}?</p>
          <p className="text-sm text-muted-foreground">Mark the reply so your dashboard stays current.</p>
          <button
            type="button"
            onClick={() => onSelect(tip.id)}
            className="mt-1 inline-flex min-h-11 items-center rounded-control font-semibold text-fit-high underline underline-offset-4 outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            Update status →
          </button>
        </div>
      ) : null}
    </section>
  );
}
