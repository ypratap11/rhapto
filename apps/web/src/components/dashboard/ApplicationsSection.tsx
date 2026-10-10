"use client";

import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import { ApplicationSheet } from "@/components/pipeline/ApplicationSheet";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { ApplicationOut } from "@/lib/api/queries";
import { CHIP_IDS, CHIP_LABEL, type ChipId, chipCounts, lastChange, rowsForChip, statusWords } from "@/lib/applications-view";
import { formatDate } from "@/lib/format";
import { statusTone } from "@/lib/status";
import { cn } from "cn";

const PAGE = 10;

export function ApplicationsSection({ rows }: { rows: ApplicationOut[] }) {
  const [chip, setChip] = useState<ChipId>("all");
  const [showAll, setShowAll] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const counts = useMemo(() => chipCounts(rows), [rows]);
  const visible = useMemo(() => rowsForChip(rows, chip), [rows, chip]);
  const shown = showAll ? visible : visible.slice(0, PAGE);
  const selected = rows.find((r) => r.id === selectedId) ?? null;

  return (
    <section aria-labelledby="applications-heading" className="space-y-3">
      <h2 id="applications-heading" className="font-sans text-base font-semibold">
        Your applications
      </h2>
      <div role="group" aria-label="Filter applications" className="flex flex-wrap gap-2">
        {CHIP_IDS.map((id) => (
          <button
            key={id}
            type="button"
            aria-pressed={chip === id}
            onClick={() => {
              setChip(id);
              setShowAll(false);
            }}
            className={cn(
              "inline-flex min-h-11 items-center gap-1.5 rounded-full border px-3 text-sm md:min-h-9",
              chip === id ? "border-primary bg-primary/10 text-foreground" : "border-border bg-surface hover:bg-muted",
              counts[id] === 0 && chip !== id ? "text-muted-foreground" : "",
            )}
          >
            {CHIP_LABEL[id]}
            <span className="tabular-nums text-muted-foreground">{counts[id]}</span>
          </button>
        ))}
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
