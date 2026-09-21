"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { ApplicationDetail } from "@/components/pipeline/ApplicationDetail";
import { ApplicationList } from "@/components/pipeline/ApplicationList";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { HeroBand } from "@/components/shell/HeroBand";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { useApplications } from "@/lib/api/queries";
import { PIPELINE_STATUSES } from "@/lib/status";

function isPipelineStatus(status: string): boolean {
  return (PIPELINE_STATUSES as readonly string[]).includes(status);
}

export default function PipelinePage() {
  const applications = useApplications();

  // The board endpoint buckets by every APPLICATION_STATUSES key, including `discovered`/`queued`
  // (the status every Application is created with, before anyone applies) — but ApplicationList
  // only ever renders tabs for the five PIPELINE_STATUSES. An application in one of the other
  // buckets has no tab and no card here, so it's filtered out up front: it must never become the
  // default selection, and ApplicationList must never be handed a row it cannot show as current.
  const rows = useMemo(
    () =>
      Object.values(applications.data?.columns ?? {})
        .flat()
        .filter((a) => isPipelineStatus(a.status)),
    [applications.data],
  );

  // Same two-boolean shape as the Dashboard (app/page.tsx): a paused fetch (API unreachable)
  // settles with isLoading false and error null, so isPaused is checked explicitly; hasIssue shows
  // the banner even alongside stale cached rows, nothingToShow only gates falling back when there
  // truly is nothing cached to render.
  const hasIssue = Boolean(applications.error) || applications.isPaused;
  const nothingToShow = !applications.data && hasIssue;

  const [selectedId, setSelectedId] = useState<string | null>(null);
  // The default selection is latched once, the render after real rows first become available —
  // calling `setState` conditionally during render (guarded so it can fire at most once) rather
  // than in an effect, the pattern React's own docs recommend for "remembering something from a
  // previous render" (https://react.dev/reference/react/useState#storing-information-from-previous-renders).
  // Re-deriving `rows[0]` on every render instead would let the visible selection drift out from
  // under a user who never explicitly picked one: acting on the default-selected application (e.g.
  // a status change) reorders `rows` on the refetch that follows, and `rows[0]` can become a
  // different application entirely. Once latched, `selectedId` never reverts to null, so this can
  // only ever run once.
  if (selectedId === null && rows[0]) {
    setSelectedId(rows[0].id);
  }
  const selected = rows.find((a) => a.id === selectedId) ?? null;

  return (
    <>
      <HeroBand tone="sand">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="font-serif text-2xl font-medium">Pipeline</h1>
            <p className="text-sm text-muted-foreground">Every application you have sent, and what it is waiting on.</p>
          </div>
          {/* A real view switch, rather than a bare underlined link floating above the content. */}
          <nav aria-label="Pipeline view" className="flex items-center gap-1 rounded-lg border border-border bg-surface p-1">
            <span aria-current="page" className="rounded-md bg-muted px-3 py-1 text-sm font-medium text-foreground">
              List
            </span>
            <Link
              href="/pipeline/board"
              className="rounded-md px-3 py-1 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
            >
              Board
            </Link>
          </nav>
        </div>
      </HeroBand>
      {hasIssue ? (
        <div className="mb-4">
          <ApiErrorBanner error={applications.error ?? "Can't reach Rhapto's API."} />
        </div>
      ) : null}
      {!applications.data ? (
        nothingToShow ? null : (
          <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
            <TableSkeleton />
            <Skeleton className="h-96 w-full rounded-card" />
          </div>
        )
      ) : (
        // A master-detail pair: each pane owns its scroll from `lg` up, so reading a long JD no
        // longer scrolls the application list away and the page itself stays one screen tall.
        // `minmax(0,1fr)` and `min-w-0` are what stop a wide child from pushing its column open --
        // the failure this page shipped with. Below `lg` the two stack and the page scrolls.
        <div className="grid gap-6 lg:h-[calc(100vh-16rem)] lg:grid-cols-[360px_minmax(0,1fr)]">
          <div className="min-w-0 lg:h-full lg:overflow-y-auto lg:pr-1">
            <ApplicationList applications={rows} selectedId={selectedId} onSelect={setSelectedId} />
          </div>
          <div className="min-w-0 lg:h-full lg:overflow-y-auto lg:pr-1">
            {selected ? (
              <ApplicationDetail key={selected.id} application={selected} />
            ) : (
              <EmptyState
                icon={Inbox}
                title="Pick an application"
                description="Choose one on the left to see its status, notes and history."
              />
            )}
          </div>
        </div>
      )}
    </>
  );
}
