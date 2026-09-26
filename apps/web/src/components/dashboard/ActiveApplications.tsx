"use client";

import { Package } from "lucide-react";
import Link from "next/link";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useApplications, useDashboard, usePackageList, type ApplicationOut, type DueFollowup, type PackageListItem } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";
import { STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";

const RECENT_COUNT = 3;

type Row = { key: string; href: string; dueToday: boolean; card: React.ReactNode };

function isoDate(iso: string): string {
  return iso.slice(0, 10);
}

function applicationCard(application: ApplicationOut, dueToday: boolean): Row {
  return {
    key: `application-${application.id}`,
    href: `/jobs/${application.job.id}`,
    dueToday,
    card: (
      <>
        {dueToday ? <StatusBadge tone="danger">Follow up today</StatusBadge> : null}
        <p className="truncate text-sm font-medium">{application.job.company ?? "Unknown company"}</p>
        <p className="truncate text-xs text-muted-foreground">{application.job.title ?? "Untitled role"}</p>
        <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
        <p className="mt-auto text-xs text-muted-foreground">Updated {formatRelative(application.updated_at)}</p>
      </>
    ),
  };
}

/** A due-followup application that didn't already make the recent-3 cut — built from `FollowUpOut`'s
 * own `job` ref, since the full `ApplicationOut` (and its `updated_at`) isn't fetched for it. */
function followupCard(followup: DueFollowup): Row {
  return {
    key: `application-${followup.application_id}`,
    href: `/jobs/${followup.job.id}`,
    dueToday: true,
    card: (
      <>
        <StatusBadge tone="danger">Follow up today</StatusBadge>
        <p className="truncate text-sm font-medium">{followup.job.company ?? "Unknown company"}</p>
        <p className="truncate text-xs text-muted-foreground">{followup.job.title ?? "Untitled role"}</p>
        <StatusBadge tone={statusTone(followup.status)}>{STATUS_LABEL[followup.status as ApplicationStatus] ?? followup.status}</StatusBadge>
      </>
    ),
  };
}

function readyCard(item: PackageListItem): Row {
  return {
    key: `ready-${item.id}`,
    href: `/jobs/${item.job_id}/packages/${item.id}`,
    dueToday: false,
    card: (
      <>
        <StatusBadge tone="mid">Ready to apply</StatusBadge>
        <p className="truncate text-sm font-medium">{item.company ?? "Unknown company"}</p>
        <p className="truncate text-xs text-muted-foreground">{item.title ?? "Untitled role"}</p>
      </>
    ),
  };
}

/**
 * Spec §3.1: the three most recently updated pipeline items, plus tailored packages that are ready
 * but have no application yet. Every follow-up due today or earlier gets a row too — flagged on its
 * existing card when it's already one of the recent three, or added as its own card (built from
 * `FollowUpOut.job`, since its full `ApplicationOut` may not be among the recent three fetched) when
 * it isn't — rather than a due reminder living in a separate list the user has to check twice.
 */
export function ActiveApplications() {
  const applications = useApplications();
  const ready = usePackageList("ready");
  const dashboard = useDashboard();

  const today = isoDate(new Date().toISOString());
  const dueToday = (dashboard.data?.due_followups ?? []).filter((f) => isoDate(f.follow_up_at) <= today);
  const dueTodayIds = new Set(dueToday.map((f) => f.application_id));

  const recent = Object.values(applications.data?.columns ?? {})
    .flat()
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    .slice(0, RECENT_COUNT);
  const recentIds = new Set(recent.map((a) => a.id));

  const dueNotInRecent = dueToday.filter((f) => !recentIds.has(f.application_id));

  const readyNotApplied = (ready.data ?? []).filter((p) => p.application_status === null);

  const rows = [
    ...recent.map((a) => applicationCard(a, dueTodayIds.has(a.id))),
    ...dueNotInRecent.map(followupCard),
    ...readyNotApplied.map(readyCard),
  ].sort((a, b) => Number(b.dueToday) - Number(a.dueToday));

  // Also waits on `dashboard` (not just applications/ready): due_followups defaults to [] until it
  // settles, and starting the grid without it would flash cards in without their "Follow up today"
  // flag, then re-flag them a moment later.
  const loading = applications.isLoading || ready.isLoading || dashboard.isLoading;
  // Three separate queries, each of which can fail or pause independently (dashboard's own call can
  // succeed while these fail, or vice versa) — same gap app/dashboard/page.tsx's hasIssue/nothingToShow closes.
  // A paused query (unreachable network) settles into isLoading: false, error: null, data: undefined,
  // indistinguishable from "nothing in flight" without checking isPaused too.
  const hasIssue =
    Boolean(applications.error) || applications.isPaused || Boolean(ready.error) || ready.isPaused || Boolean(dashboard.error) || dashboard.isPaused;
  const bannerError = applications.error ?? ready.error ?? dashboard.error ?? (hasIssue ? "Can't reach Rhapto's API." : null);
  const nothingToShow = rows.length === 0 && hasIssue;

  return (
    <section aria-labelledby="active-applications-heading" className="space-y-3">
      <h2 id="active-applications-heading" className="font-sans text-base font-semibold">
        Active applications
      </h2>
      {!loading && hasIssue ? <ApiErrorBanner error={bannerError} /> : null}
      {loading ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3" aria-hidden="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-28 animate-pulse rounded-card bg-surface-muted" />
          ))}
        </div>
      ) : nothingToShow ? (
        <EmptyState icon={Package} title="Couldn&rsquo;t load active applications" description="Try refreshing the page." />
      ) : rows.length === 0 ? (
        <EmptyState icon={Package} title="Nothing in flight yet" description="Tailor a role from Recommended roles above to start your pipeline." />
      ) : (
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((row) => (
            <li key={row.key}>
              <Link href={row.href} className="hover-lift flex h-full flex-col gap-2 rounded-card border border-border bg-surface p-3 shadow-card">
                {row.card}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
