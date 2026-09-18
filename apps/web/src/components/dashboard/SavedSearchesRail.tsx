import Link from "next/link";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { DashboardSavedSearch } from "@/lib/api/queries";

/** Spec §6: opening a saved search's results is what clears its "N new" badge, so this only links —
 * `useMarkSearchViewed` fires from the Jobs page once `?search_id=` lands there. */
export function SavedSearchesRail({ searches }: { searches: DashboardSavedSearch[] }) {
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
