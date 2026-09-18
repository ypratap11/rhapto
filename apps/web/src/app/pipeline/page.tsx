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

export default function PipelinePage() {
  const applications = useApplications();

  const rows = useMemo(() => Object.values(applications.data?.columns ?? {}).flat(), [applications.data]);

  // Same two-boolean shape as the Dashboard (app/page.tsx): a paused fetch (API unreachable)
  // settles with isLoading false and error null, so isPaused is checked explicitly; hasIssue shows
  // the banner even alongside stale cached rows, nothingToShow only gates falling back when there
  // truly is nothing cached to render.
  const hasIssue = Boolean(applications.error) || applications.isPaused;
  const nothingToShow = !applications.data && hasIssue;

  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Derived, never assigned in an effect: the first row is the default selection until the person
  // picks one themselves.
  const activeId = selectedId ?? rows[0]?.id ?? null;
  const selected = rows.find((a) => a.id === activeId) ?? null;

  return (
    <>
      <HeroBand tone="sand">
        <h1 className="font-serif text-2xl font-medium">Pipeline</h1>
        <p className="text-sm text-muted-foreground">Every application you have sent, and what it is waiting on.</p>
      </HeroBand>
      <div className="mb-4">
        <Link href="/pipeline/board" className="text-sm text-primary underline-offset-4 hover:underline">
          Board view
        </Link>
      </div>
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
        <div className="grid gap-6 lg:grid-cols-[360px_1fr]">
          <ApplicationList applications={rows} selectedId={activeId} onSelect={setSelectedId} />
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
      )}
    </>
  );
}
