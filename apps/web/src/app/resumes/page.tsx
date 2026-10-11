"use client";

import { Suspense } from "react";
import Link from "next/link";
import { FileText } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { ResumeTable } from "@/components/resumes/ResumeTable";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { HeroBand } from "@/components/shell/HeroBand";
import { buttonVariants } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePackageList, usePackageListAny } from "@/lib/api/queries";
import { resolveTab, type ResumesTab } from "@/lib/resumes-tab";

const FILTERS: { value: ResumesTab; label: string }[] = [
  { value: "review", label: "To review" },
  { value: "ready", label: "Ready to send" },
  { value: "blocked", label: "Needs attention" },
];

function ResumesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = resolveTab(searchParams);

  const list = usePackageList(tab);
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
      <HeroBand tone="sand">
        <h1 className="font-serif text-2xl font-medium">My resumes</h1>
        <p className="text-sm text-muted-foreground">Every tailored resume and what it is waiting on.</p>
      </HeroBand>
      <div className="mb-4">
        <Tabs value={tab} onValueChange={(value) => value && router.replace(`/resumes?tab=${value}`)}>
          <TabsList aria-label="Resume status" className="max-md:h-auto max-md:w-full">
            {FILTERS.map((f) => (
              <TabsTrigger key={f.value} value={f.value} className="max-md:min-h-11">
                {f.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
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
