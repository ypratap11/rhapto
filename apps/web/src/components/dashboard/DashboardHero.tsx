import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PollNowButton } from "@/components/jobs/PollNowButton";

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/**
 * Spec §2: the dashboard reports facts, not promos — both numbers come from GET /dashboard. While
 * that call is still in flight, `loading` swaps in a shape-matched skeleton instead of falling back
 * to `newFitCount={0} needsReviewCount={0}`: a real zero renders the *same* empty-state prompt this
 * would, so a caller that didn't distinguish loading from empty would show it a beat too early —
 * telling a user with plenty of new roles that they have none.
 *
 * `error` covers the third state a `newFitCount`/`needsReviewCount` pair can't: TanStack Query's
 * `isLoading` is `isPending && isFetching`, so once a failed request *settles*, loading goes false
 * again while there was still never real data — the exact moment a caller with only the two counts
 * would fall back to 0/0 and repeat the same false-empty prompt `loading` was added to prevent.
 */
export function DashboardHero({
  newFitCount,
  needsReviewCount,
  loading = false,
  error = false,
}: {
  newFitCount: number;
  needsReviewCount: number;
  loading?: boolean;
  error?: boolean;
}) {
  if (loading) {
    return (
      <div data-testid="dashboard-hero-skeleton" aria-hidden="true">
        <Skeleton className="h-9 w-3/4 max-w-md" />
        <div className="mt-3 flex flex-wrap gap-2">
          <Skeleton className="h-8 w-32 rounded-lg" />
          <Skeleton className="h-8 w-28 rounded-lg" />
        </div>
      </div>
    );
  }
  if (error) {
    // No CTAs: "Review resumes" and "New search" both imply a count we don't actually have. The
    // ApiErrorBanner just below the hero band carries the real failure detail; this just avoids
    // asserting "you have nothing" in its place.
    return (
      <div data-testid="dashboard-hero-error">
        <h1 className="font-serif text-[32px] font-medium leading-tight tracking-tight">Couldn&rsquo;t load your dashboard right now.</h1>
        <p className="text-sm text-muted-foreground">Try refreshing the page.</p>
      </div>
    );
  }
  const empty = newFitCount === 0 && needsReviewCount === 0;
  return (
    <>
      <h1 className="font-serif text-[32px] font-medium leading-tight tracking-tight">
        {empty
          ? "Nothing new yet. Add a search or a company to your watchlist."
          : `${plural(newFitCount, "new role fits", "new roles fit")} you this week · ${plural(needsReviewCount, "resume waiting", "resumes waiting")} for review`}
      </h1>
      <div className="flex flex-wrap gap-2">
        {empty ? (
          <>
            {/* A plain styled Link, not the Base UI `Button` primitive: these are navigations, not
                actions, and the Dashboard's own test asserts `role="link"` on them. Routing this
                through `Button render={<Link/>}` would force a choice between an a11y-tree role of
                "button" (`nativeButton={false}`) or a dev-mode console error (`nativeButton` left at
                its `true` default on a non-<button> element) — `buttonVariants` sidesteps both. */}
            <Link href="/jobs" className={buttonVariants()}>
              New search
            </Link>
            <Link href="/profile?card=watchlist" className={buttonVariants({ variant: "outline" })}>
              Add company
            </Link>
          </>
        ) : (
          <>
            <Link href="/resumes?tab=review" className={buttonVariants()}>
              Review resumes
            </Link>
            <PollNowButton onFinished={() => undefined} />
          </>
        )}
      </div>
    </>
  );
}
