"use client";

import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { usePackages, type JobOut, type PackageSummary } from "@/lib/api/queries";

function newest(packages: PackageSummary[]): PackageSummary | null {
  return packages.reduce<PackageSummary | null>((best, p) => (!best || p.version > best.version ? p : best), null);
}

/** Shown when `job.repost_of` points back at an earlier posting of the same role (spec §3.3): the
 * original's newest package can be reused instead of tailoring from scratch again. */
export function RepostNotice({ job }: { job: JobOut }) {
  const originalId = job.repost_of ?? "";
  const packages = usePackages(originalId);
  if (!job.repost_of) return null;

  const latest = newest(packages.data ?? []);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-card border border-border bg-surface-muted p-4">
      <StatusBadge tone="mid">Reposted</StatusBadge>
      <Link href={`/jobs/${job.repost_of}`} className="text-sm underline-offset-4 hover:underline">
        See the original posting
      </Link>
      {latest ? (
        // A plain styled Link, not `Button render={<Link/>}`: that combination announces the
        // navigation as role="button" and breaks `getByRole("link")` (Task 5's hard-won rule).
        <Link href={`/jobs/${job.repost_of}/packages/${latest.id}`} className={buttonVariants({ variant: "outline", size: "sm" })}>
          Reuse resume v{latest.version}
        </Link>
      ) : null}
    </div>
  );
}
