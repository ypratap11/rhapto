"use client";

import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { useDiscoveryRuns } from "@/lib/api/queries";
import { SOURCE_LABEL } from "@/lib/fit";
import { formatRelative } from "@/lib/format";

export function RunsDrawer({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const runs = useDiscoveryRuns();
  const rows = runs.data ?? [];

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Poll runs</SheetTitle>
        </SheetHeader>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 pb-4">
          {runs.isLoading ? <Skeleton className="h-24 w-full" /> : null}
          {runs.error ? <ApiErrorBanner error={runs.error} /> : null}
          {!runs.isLoading && !runs.error && rows.length === 0 ? <p className="text-sm text-muted-foreground">No polls yet.</p> : null}
          {rows.map((run) => (
            <div key={run.id} className="space-y-0.5 border-b border-border pb-2 text-sm last:border-0">
              <div className="flex items-center justify-between gap-2">
                <span className="font-medium">
                  {SOURCE_LABEL[run.source] ?? run.source}
                  {run.board ? ` · ${run.board}` : ""}
                </span>
                <span className="text-muted-foreground">{formatRelative(run.finished_at ?? run.started_at)}</span>
              </div>
              <p className="text-muted-foreground">
                found {run.found} · {run.new} new
              </p>
              {run.error ? <p className="text-red-700">{run.error}</p> : null}
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  );
}
