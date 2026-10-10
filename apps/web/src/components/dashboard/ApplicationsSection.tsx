"use client";

import { ChevronRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { ApplicationSheet } from "@/components/pipeline/ApplicationSheet";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ApplicationOut } from "@/lib/api/queries";
import { CHIP_IDS, CHIP_LABEL, type ChipId, chipCounts, lastChange, rowsForChip, statusWords } from "@/lib/applications-view";
import { formatDate } from "@/lib/format";
import { statusTone } from "@/lib/status";
import { cn } from "cn";

const PAGE = 10;

/** `dueIds`: application ids whose follow-up is due today or overdue (from the dashboard's due_followups). */
export function ApplicationsSection({ rows, dueIds }: { rows: ApplicationOut[]; dueIds?: ReadonlySet<string> }) {
  const [chip, setChip] = useState<ChipId>("all");
  const [showAll, setShowAll] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const counts = useMemo(() => chipCounts(rows), [rows]);
  const dueRows = useMemo(() => rows.filter((r) => dueIds?.has(r.id)), [rows, dueIds]);
  const [dueOnly, setDueOnly] = useState(false);
  const visible = useMemo(() => (dueOnly && dueRows.length > 0 ? dueRows : rowsForChip(rows, chip)), [rows, chip, dueOnly, dueRows]);
  const shown = showAll ? visible : visible.slice(0, PAGE);
  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const rowRef = useRef<HTMLDivElement>(null);

  const mounted = useRef(false);
  useEffect(() => {
    // Only a user's change moves the row; on load it stays at scrollLeft 0.
    if (!mounted.current) {
      mounted.current = true;
      return;
    }
    const row = rowRef.current;
    const active = row?.querySelector<HTMLElement>('[aria-pressed="true"]');
    if (!row || !active) return;
    row.scrollLeft = Math.max(0, active.offsetLeft - (row.clientWidth - active.offsetWidth) / 2);
  }, [chip, dueOnly]);

  return (
    <section aria-labelledby="applications-heading" className="space-y-3">
      <h2 id="applications-heading" className="font-sans text-base font-semibold">
        Your applications
      </h2>
      {/* One horizontally scrollable row, never wrapped. The active chip is brought into view by moving
          this row's scrollLeft only: scrollIntoView would also scroll the page. */}
      <div
        ref={rowRef}
        role="group"
        aria-label="Filter applications"
        className="relative -mx-4 flex flex-nowrap gap-2 overflow-x-auto px-4 [scrollbar-width:none] md:mx-0 md:px-0 [&::-webkit-scrollbar]:hidden"
      >
        {CHIP_IDS.map((id) => {
          const pressed = !dueOnly && chip === id;
          return (
            <button
              key={id}
              type="button"
              aria-pressed={pressed}
              onClick={() => {
                setChip(id);
                setDueOnly(false);
                setShowAll(false);
              }}
              className={cn(
                "inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3 text-sm md:min-h-9",
                pressed ? "border-primary bg-primary/10 text-foreground" : "border-border bg-surface hover:bg-muted",
                counts[id] === 0 && !pressed ? "text-muted-foreground" : "",
              )}
            >
              {CHIP_LABEL[id]}
              <span className="tabular-nums text-muted-foreground">{counts[id]}</span>
            </button>
          );
        })}
        {dueRows.length > 0 ? (
          <button
            type="button"
            aria-pressed={dueOnly}
            onClick={() => {
              setDueOnly((v) => !v);
              setShowAll(false);
            }}
            className={cn(
              "inline-flex min-h-11 shrink-0 items-center whitespace-nowrap rounded-full border px-3 text-sm md:min-h-9",
              dueOnly ? "border-primary bg-primary/10 text-foreground" : "border-border bg-surface hover:bg-muted",
            )}
          >
            {dueRows.length} follow-up{dueRows.length === 1 ? "" : "s"} due
          </button>
        ) : null}
      </div>
      {shown.length === 0 ? (
        <p className="rounded-card border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">Nothing here yet.</p>
      ) : (
        <ul className="space-y-2">
          {shown.map((a) => (
            <li key={a.id}>
              <button
                type="button"
                onClick={() => setSelectedId(a.id)}
                className="hover-lift flex min-h-14 w-full items-center gap-3 rounded-card border border-border bg-surface px-4 py-3 text-left"
              >
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{a.job.company ?? "Unknown company"}</span>
                  <span className="block truncate text-sm text-muted-foreground">{a.job.title ?? "Untitled role"}</span>
                  <span className="block text-xs text-muted-foreground">{formatDate(lastChange(a))}</span>
                </span>
                {dueIds?.has(a.id) ? <StatusBadge tone="mid">Follow up</StatusBadge> : null}
                <StatusBadge tone={statusTone(a.status)}>{statusWords(a)}</StatusBadge>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      {!showAll && visible.length > PAGE ? (
        <Button type="button" variant="ghost" className="max-md:min-h-11" onClick={() => setShowAll(true)}>
          Show all {visible.length}
        </Button>
      ) : null}
      <ApplicationSheet application={selected} open={selected !== null} onOpenChange={(open) => !open && setSelectedId(null)} />
    </section>
  );
}
