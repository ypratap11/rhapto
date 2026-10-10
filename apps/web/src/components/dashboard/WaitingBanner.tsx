import Link from "next/link";

/** Only when something is waiting. The count is the dashboard's existing `needs_review_count`. */
export function WaitingBanner({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-surface-muted px-4 py-3 text-sm">
      <p>{count === 1 ? "1 resume is waiting for your review." : `${count} resumes are waiting for your review.`}</p>
      <Link href="/resumes?tab=review" className="inline-flex min-h-11 items-center font-medium text-primary underline underline-offset-4">
        {count === 1 ? "Review it →" : "Review them →"}
      </Link>
    </div>
  );
}
