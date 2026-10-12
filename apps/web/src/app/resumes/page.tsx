"use client";

import { Suspense } from "react";
import Link from "next/link";
import { FileText } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { ResumeTable } from "@/components/resumes/ResumeTable";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { PageHero } from "@/components/shell/PageHero";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { StatTile, type StatTone } from "@/components/ui/stat-tile";
import { usePackageList, usePackageListAny } from "@/lib/api/queries";
import { resolveTab, type ResumesTab } from "@/lib/resumes-tab";

const TILES: { value: ResumesTab; label: string; hint: string; tone: StatTone }[] = [
  { value: "review", label: "To review", hint: "Read it before you send it", tone: "peach" },
  { value: "ready", label: "Ready to send", hint: "Download and apply", tone: "mint" },
  { value: "blocked", label: "Needs attention", hint: "A line needs fixing first", tone: "amber" },
];

function ResumesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = resolveTab(searchParams);

  // One query per tile, always in this order. The rendered list is the current tab's own query, so a
  // tile's number is the length of the list it opens; same keys as before, so nothing is fetched twice.
  const lists = { review: usePackageList("review"), ready: usePackageList("ready"), blocked: usePackageList("blocked") };
  const list = lists[tab];
  // Only asked once this tab has come back empty: tells "nothing in this tab" from "no resumes yet".
  const tabIsEmpty = list.data !== undefined && list.data.length === 0;
  const anyList = usePackageListAny(tabIsEmpty);

  // Same shape as the Dashboard (src/app/dashboard/page.tsx): a settled error and TanStack's paused
  // fetchStatus both mean "something is wrong right now", but neither should discard rows a prior
  // fetch already put on screen — only fall back to nothing when there is truly nothing cached.
  const hasIssue = Boolean(list.error) || list.isPaused;
  const nothingToShow = !list.data && hasIssue;

  return (
    <>
      <PageHero title="My resumes" subtitle="Every tailored resume and what it is waiting on.">
        <div role="group" aria-label="Resume status" className="grid gap-3 sm:grid-cols-3">
          {TILES.map((t) => {
            const q = lists[t.value];
            return (
              <StatTile
                key={t.value}
                tone={t.tone}
                value={q.data ? q.data.length : "–"}
                label={t.label}
                hint={!q.data && (q.error || q.isPaused) ? "Couldn't load" : t.hint}
                hintClassName="max-sm:hidden"
                muted={!q.data?.length}
                pressed={tab === t.value}
                onClick={() => router.replace(`/resumes?tab=${t.value}`)}
              />
            );
          })}
        </div>
      </PageHero>
      {hasIssue ? (
        <div className="mb-4">
          <ApiErrorBanner error={list.error ?? "Can't reach Rhapto's API."} />
        </div>
      ) : null}
      {list.isLoading ? (
        <TableSkeleton />
      ) : nothingToShow ? null : tabIsEmpty ? (
        anyList.data && anyList.data.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="No resumes yet. Pick a job and Rhapto tailors your resume to it."
            action={
              <Link href="/start" className={buttonVariants()}>
                + Tailor a resume
              </Link>
            }
          />
        ) : (
          <EmptyState icon={FileText} title="Nothing here right now." />
        )
      ) : (
        <ResumeTable rows={list.data ?? []} />
      )}
    </>
  );
}

export default function ResumesPage() {
  return (
    <Suspense fallback={<TableSkeleton />}>
      <ResumesPageInner />
    </Suspense>
  );
}
