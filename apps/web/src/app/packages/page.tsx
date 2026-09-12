"use client";

import { Suspense, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PackageTable } from "@/components/packages/PackageTable";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import type { TrackInfo } from "@/components/queue/JobCard";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePackageList, useTracks, type PackageListFilter } from "@/lib/api/queries";

const FILTERS: { value: PackageListFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "review", label: "Needs review" },
  { value: "blocked", label: "Blocked" },
  { value: "applied", label: "Applied" },
];

function isPackageListFilter(value: string | null): value is PackageListFilter {
  return value === "all" || value === "review" || value === "blocked" || value === "applied";
}

function PackagesPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filter: PackageListFilter = isPackageListFilter(searchParams.get("filter")) ? (searchParams.get("filter") as PackageListFilter) : "review";

  const list = usePackageList(filter);
  const tracksQuery = useTracks();

  const tracks = useMemo(() => {
    const map: Record<string, TrackInfo> = {};
    for (const t of tracksQuery.data ?? []) map[t.id] = { name: t.name, min_fit: t.min_fit };
    return map;
  }, [tracksQuery.data]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl">Packages</h1>
        <Tabs value={filter} onValueChange={(value) => value && router.replace(`/packages?filter=${value}`)}>
          <TabsList aria-label="Package filter">
            {FILTERS.map((f) => (
              <TabsTrigger key={f.value} value={f.value}>
                {f.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>
      {list.isLoading ? (
        <Skeleton className="h-32 w-full" />
      ) : list.error ? (
        <ApiErrorBanner error={list.error} />
      ) : (
        <PackageTable rows={list.data ?? []} tracks={tracks} filter={filter} />
      )}
    </div>
  );
}

export default function PackagesPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <PackagesPageInner />
    </Suspense>
  );
}
