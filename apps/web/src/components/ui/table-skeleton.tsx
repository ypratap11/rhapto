import { Skeleton } from "@/components/ui/skeleton";

/** A stack of 44px row placeholders — the loading shape for any page whose loaded content is an
 * `EntityTable`/`Table` (spec §3: skeletons match the card/row shapes they replace). */
export function TableSkeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div data-slot="table-skeleton" className="space-y-1 rounded-card border border-border p-1" aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full rounded-control" />
      ))}
    </div>
  );
}
