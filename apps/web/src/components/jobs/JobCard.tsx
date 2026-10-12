"use client";

import Link from "next/link";
import { cn } from "cn";
import { buttonVariants } from "@/components/ui/button";
import { FitRing } from "@/components/ui/fit-ring";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { JobOut } from "@/lib/api/queries";
import { isNewToday } from "@/lib/dashboard-view";
import { locationTierLabel, SOURCE_LABEL } from "@/lib/fit";
import { formatRelative, formatSalary, truncate } from "@/lib/format";
import { NotInterestedButton } from "./NotInterestedButton";
import { SimilarPostings } from "./SimilarPostings";

export type TrackInfo = { name: string; min_fit: number };

/** The card the Jobs grid renders once per job (the Dashboard uses the lighter `JobRow`). Tailor is a link
 * to the job page rather than an inline `TailorButton`: the grid card has no room for the track and mode
 * selects, and spec §3.3 puts the primary tailoring action on the job page. `now` is the page's one clock
 * reading, so "New today" here and the count in the page header cannot disagree. */
export function JobCard({ job, track, now }: { job: JobOut; track: TrackInfo | null; now?: Date }) {
  const company = job.company ?? "Unknown company";
  const tier = locationTierLabel(job.location_tier);
  const salary = formatSalary(job.salary_text, job.source);
  const alsoIds = job.also_ids ?? []; // absent on a response from before the field existed
  const isNew = isNewToday(job.discovered_at, now);
  return (
    <article className="flex h-full flex-col gap-3 rounded-2xl border border-border bg-surface p-4 transition-[border-color,box-shadow,transform] hover:border-primary motion-safe:hover:-translate-y-0.5 motion-safe:hover:shadow-card">
      <div className="flex items-start gap-3.5">
        <FitRing fit={job.best_fit ?? null} size={52} />
        <div className="min-w-0">
          <h3 className="font-sans text-base font-semibold leading-snug">
            <Link href={`/jobs/${job.id}`} className="underline-offset-4 hover:underline max-md:inline-block max-md:py-3">
              {job.title ?? "Untitled role"}
            </Link>
          </h3>
          <p className="text-sm text-muted-foreground">
            {company} · {job.location ?? tier}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {salary ? <StatusBadge tone="neutral">{salary}</StatusBadge> : null}
        {track ? <StatusBadge tone="primary">{track.name}</StatusBadge> : null}
        {isNew ? <StatusBadge tone="primary">New today</StatusBadge> : null}
        <StatusBadge tone="muted">{SOURCE_LABEL[job.source] ?? job.source}</StatusBadge>
        {job.location && tier ? <StatusBadge tone="muted">{tier}</StatusBadge> : null}
        {job.repost_of ? <StatusBadge tone="mid">Reposted</StatusBadge> : null}
        {job.unlisted_at ? <StatusBadge tone="muted">No longer listed</StatusBadge> : null}
        {job.search_name ? <StatusBadge tone="muted">{`via ${job.search_name}`}</StatusBadge> : null}
      </div>
      <p className="line-clamp-2 text-sm text-muted-foreground">{truncate(job.jd_text, 160)}</p>
      {alsoIds.length > 0 ? <SimilarPostings ids={alsoIds} /> : null}
      <div className="mt-auto flex items-center justify-between gap-2 border-t border-border pt-3">
        <p className="text-xs text-muted-foreground">Posted {formatRelative(job.posted_at ?? job.discovered_at)}</p>
        <div className="flex items-center gap-1.5">
          {/* A plain styled Link, not the Base UI `Button` primitive: Tailor is a navigation, and
              `Button render={<Link/>}` forces a choice between misreporting this as role="button"
              (`nativeButton={false}`) or a dev-mode console error (`nativeButton` left at its `true`
              default on a non-<button> element). `buttonVariants` gets the same look without either. */}
          <Link href={`/jobs/${job.id}`} className={cn(buttonVariants({ variant: "outline", size: "sm" }), "max-md:min-h-11")}>
            Tailor
          </Link>
          <NotInterestedButton job={job} iconOnly />
        </div>
      </div>
    </article>
  );
}
