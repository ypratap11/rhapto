"use client";

import { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { ResumeTable } from "@/components/resumes/ResumeTable";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { HeroBand } from "@/components/shell/HeroBand";
import { TableSkeleton } from "@/components/ui/table-skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePackageList, useTracks, type PackageListFilter } from "@/lib/api/queries";

const FILTERS: { value: PackageListFilter; label: string }[] = [
  { value: "review", label: "Needs review" },
  { value: "ready", label: "Ready" },
  { value: "blocked", label: "Blocked" },
  { value: "applied", label: "Applied" },
];

function isPackageListFilter(value: string | null): value is PackageListFilter {
  return value === "review" || value === "ready" || value === "blocked" || value === "applied";
}

// The old /packages route 307-redirected here with its ?filter= intact, including the retired
// "all" value — that value, and any other unrecognized one, falls back to "review".
function resolveTab(searchParams: URLSearchParams): PackageListFilter {
  const raw = searchParams.get("tab") ?? searchParams.get("filter");
  return isPackageListFilter(raw) ? raw : "review";
}

function ResumesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tab = resolveTab(searchParams);

  const list = usePackageList(tab);
  const tracksQuery = useTracks();

  const tracks = useMemo(() => {
    const map: Record<string, TrackInfo> = {};
    for (const t of tracksQuery.data ?? []) map[t.id] = { name: t.name, min_fit: t.min_fit };
    return map;
  }, [tracksQuery.data]);

  // Same shape as the Dashboard (src/app/dashboard/page.tsx): a settled error and TanStack's paused
  // fetchStatus both mean "something is wrong right now", but neither should discard rows a prior
  // fetch already put on screen — only fall back to nothing when there is truly nothing cached.
  const hasIssue = Boolean(list.error) || list.isPaused;
  const nothingToShow = !list.data && hasIssue;

  return (
    <>
      <HeroBand tone="sand">
        <h1 className="font-serif text-2xl font-medium">Resumes</h1>
        <p className="text-sm text-muted-foreground">Every tailored resume, and what it is waiting on.</p>
      </HeroBand>
      <Breadcrumbs items={[{ label: "Resumes" }]} />
      <div className="mb-4">
        <Tabs value={tab} onValueChange={(value) => value && router.replace(`/resumes?tab=${value}`)}>
          <TabsList aria-label="Resume status">
            {FILTERS.map((f) => (
              <TabsTrigger key={f.value} value={f.value}>
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
      {list.isLoading ? <TableSkeleton /> : nothingToShow ? null : <ResumeTable rows={list.data ?? []} tracks={tracks} filter={tab} />}
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
