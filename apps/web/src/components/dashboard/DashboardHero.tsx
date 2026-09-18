import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { PollNowButton } from "@/components/queue/PollNowButton";

function plural(n: number, one: string, many: string): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Spec §2: the dashboard reports facts, not promos — both numbers come from GET /dashboard. */
export function DashboardHero({ newFitCount, needsReviewCount }: { newFitCount: number; needsReviewCount: number }) {
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
