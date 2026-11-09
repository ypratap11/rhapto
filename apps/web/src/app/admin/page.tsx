"use client";

import { AttentionList } from "@/components/admin/AttentionList";
import { OverviewTiles } from "@/components/admin/OverviewTiles";
import { UserTable } from "@/components/admin/UserTable";
import { Skeleton } from "@/components/ui/skeleton";
import { useAdminOverview } from "@/lib/admin/queries";

export default function AdminPage() {
  const overview = useAdminOverview();
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-4 py-6">
      <div>
        <h1 className="font-heading text-2xl font-semibold text-foreground">Admin</h1>
        <p className="text-sm text-muted-foreground">Only you can open this page.</p>
      </div>
      {overview.isError ? <p className="text-sm text-destructive">Could not load the overview.</p> : null}
      {overview.data ? (
        <>
          <OverviewTiles overview={overview.data} />
          <AttentionList alerts={overview.data.alerts} />
        </>
      ) : overview.isError ? null : (
        <Skeleton className="h-32 w-full" />
      )}
      <UserTable />
    </div>
  );
}
