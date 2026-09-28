import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { DashboardSavedSearch } from "@/lib/api/queries";

/**
 * Spec §6: opening a saved search's results is what clears its "N new" badge, so this only links —
 * `useMarkSearchViewed` fires from the Jobs page once `?search_id=` lands there.
 *
 * `loading` and `error` are both separate from `searches.length === 0`: while `useDashboard()` is
 * in flight, or once it has settled into a failure, there are no searches to show *yet* (or ever,
 * this time) — neither is the same claim as "you have never saved a search", which is what the
 * empty-state copy below actually says.
 */
export function SavedSearchesRail({
  searches,
  loading = false,
  error = false,
}: {
  searches: DashboardSavedSearch[];
  loading?: boolean;
  error?: boolean;
}) {
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
  if (error) {
    return (
      <section
        aria-labelledby="saved-searches-heading"
        className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card"
        data-testid="saved-searches-error"
      >
        <div className="flex items-center justify-between gap-2">
          <h2 id="saved-searches-heading" className="font-sans text-base font-semibold">
            Saved searches
          </h2>
          <StatusBadge tone="danger">Couldn&rsquo;t load</StatusBadge>
        </div>
        <p className="text-sm text-muted-foreground">Try refreshing the page.</p>
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
                {search.new_count > 0 ? (
                  <StatusBadge tone="primary">{`${search.new_count} new`}</StatusBadge>
                ) : search.ever_found ? null : (
                  // The badge is hidden at zero, so this is exactly where the silence lived: a search
                  // that has never returned a job rendered identically to one the user had read.
                  // `ever_found` comes from `poll_runs`, so it distinguishes them honestly.
                  <StatusBadge tone="muted">Never matched</StatusBadge>
                )}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
