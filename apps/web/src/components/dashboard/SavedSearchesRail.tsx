import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { DashboardSavedSearch } from "@/lib/api/queries";

/**
 * Spec §6: opening a saved search's results is what clears its "N new" badge, so this only links —
 * `useMarkSearchViewed` fires from the Jobs page once `?search_id=` lands there.
 *
 * `loading` is separate from `searches.length === 0`: while `useDashboard()` is in flight there are
 * no searches to show *yet*, which is not the same claim as "you have never saved a search" — the
 * latter is what the empty-state copy below actually says.
 */
export function SavedSearchesRail({ searches, loading = false }: { searches: DashboardSavedSearch[]; loading?: boolean }) {
  if (loading) {
    return (
      <section
        aria-labelledby="saved-searches-heading"
        className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card"
        data-testid="saved-searches-skeleton"
      >
        <h2 id="saved-searches-heading" className="font-sans text-base font-semibold">
          Saved searches
        </h2>
        <div className="space-y-2" aria-hidden="true">
          <Skeleton className="h-8 w-full rounded-control" />
          <Skeleton className="h-8 w-full rounded-control" />
        </div>
      </section>
    );
  }
  return (
    <section aria-labelledby="saved-searches-heading" className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <h2 id="saved-searches-heading" className="font-sans text-base font-semibold">
        Saved searches
      </h2>
      {searches.length === 0 ? (
        <p className="text-sm text-muted-foreground">Save a search from the Jobs page to see it here.</p>
      ) : (
        <ul className="space-y-1">
          {searches.map((search) => (
            <li key={search.id}>
              <Link
                href={`/jobs?search_id=${search.id}`}
                className="hover-lift flex items-center justify-between gap-2 rounded-control px-2 py-1.5 text-sm hover:bg-surface-muted"
              >
                <span className="truncate">{search.name}</span>
                {search.new_count > 0 ? <StatusBadge tone="primary">{`${search.new_count} new`}</StatusBadge> : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
