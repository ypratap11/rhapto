"use client";

import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

export type ProfileCardId = "resume-template" | "tracks" | "blocks" | "bases" | "answers" | "guardrails" | "location" | "watchlist";

/**
 * One tile of the Profile page's summary grid: a title, a one-line summary of the current state,
 * and an Edit button that opens `children` (the existing tab component) in a right-hand sheet.
 *
 * The sheet's open state is lifted to the page rather than owned here, so `?card=<id>` can open a
 * specific card's sheet on load and the page can know which card is open (spec §4).
 */
export function ProfileSummaryCard({
  id,
  title,
  summary,
  open,
  onOpenChange,
  children,
}: {
  id: ProfileCardId;
  title: string;
  summary: React.ReactNode;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
}) {
  return (
    <div data-card-id={id} className="rounded-card border border-border bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <h2 className="font-sans text-base font-semibold">{title}</h2>
        <Button variant="outline" size="sm" onClick={() => onOpenChange(true)} aria-label={`Edit ${title}`}>
          Edit
        </Button>
      </div>
      <div className="mt-2 text-sm text-muted-foreground">{summary}</div>
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-[520px] space-y-3 overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{title}</SheetTitle>
          </SheetHeader>
          {children}
        </SheetContent>
      </Sheet>
    </div>
  );
}
