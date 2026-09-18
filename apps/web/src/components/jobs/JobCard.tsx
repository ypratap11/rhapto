"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { FitRing } from "@/components/ui/fit-ring";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { JobOut } from "@/lib/api/queries";
import { locationTierLabel, SOURCE_LABEL } from "@/lib/fit";
import { formatRelative, truncate } from "@/lib/format";
import { NotInterestedButton } from "./NotInterestedButton";

export type TrackInfo = { name: string; min_fit: number };

/** The card the whole portal reuses: the Jobs grid and the Dashboard recommendations both render
 * one of these per job. Tailor is a link to the job page rather than an inline `TailorButton`: the
 * grid card has no room for the track and mode selects, and spec §3.3 puts the primary tailoring
 * action on the job page. */
export function JobCard({ job, track }: { job: JobOut; track: TrackInfo | null }) {
  const company = job.company ?? "Unknown company";
  const tier = locationTierLabel(job.location_tier);
  return (
    <article className="hover-lift flex h-full flex-col gap-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {/* A warm tile with the company's initial: no logo fetching, no third-party requests. */}
          <span data-testid="logo-placeholder" aria-hidden="true" className="grid size-9 shrink-0 place-items-center rounded-control bg-band-peach font-serif text-base font-medium">
            {company.charAt(0).toUpperCase()}
          </span>
          <div className="min-w-0">
            <h3 className="font-sans text-base font-semibold leading-tight">
              <Link href={`/jobs/${job.id}`} className="underline-offset-4 hover:underline">
                {job.title ?? "Untitled role"}
              </Link>
            </h3>
            <p className="truncate text-sm text-muted-foreground">{company}</p>
          </div>
        </div>
        <FitRing fit={job.best_fit ?? null} />
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {track ? <StatusBadge tone="primary">{track.name}</StatusBadge> : null}
        <StatusBadge tone="muted">{SOURCE_LABEL[job.source] ?? job.source}</StatusBadge>
        {tier ? <StatusBadge tone="muted">{tier}</StatusBadge> : null}
        {job.repost_of ? <StatusBadge tone="mid">Reposted</StatusBadge> : null}
        {job.unlisted_at ? <StatusBadge tone="muted">No longer listed</StatusBadge> : null}
        {job.search_name ? <StatusBadge tone="muted">{`via ${job.search_name}`}</StatusBadge> : null}
      </div>
      {job.salary_text ? <p className="text-sm font-medium">{job.salary_text}</p> : null}
      <p className="line-clamp-2 text-sm text-muted-foreground">{truncate(job.jd_text, 160)}</p>
      <p className="mt-auto text-xs text-muted-foreground">Posted · {formatRelative(job.posted_at ?? job.discovered_at)}</p>
      <div className="flex items-center justify-between gap-2 border-t border-border pt-3">
        <Button size="sm" render={<Link href={`/jobs/${job.id}`} />}>
          Tailor
        </Button>
        <NotInterestedButton job={job} size="sm" />
      </div>
    </article>
  );
}
