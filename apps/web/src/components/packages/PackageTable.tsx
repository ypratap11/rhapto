import Link from "next/link";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { TrackInfo } from "@/components/queue/JobCard";
import { FitBadge } from "@/components/queue/FitBadge";
import type { PackageListFilter, PackageListItem } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";
import { PACKAGE_STATUS_TONE, STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";

const EMPTY_TEXT: Record<PackageListFilter, string> = {
  review: "Nothing to review",
  blocked: "No blocked packages",
  applied: "Nothing applied yet",
  all: "No packages yet",
};

export function PackageTable({
  rows,
  tracks,
  filter,
}: {
  rows: PackageListItem[];
  tracks: Record<string, TrackInfo>;
  filter: PackageListFilter;
}) {
  if (rows.length === 0) {
    return <p className="text-muted-foreground">{EMPTY_TEXT[filter]}</p>;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Company</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Fit</TableHead>
          <TableHead>Version · status</TableHead>
          <TableHead>Application</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>
            <span className="sr-only">Review</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const track = row.best_track_id ? tracks[row.best_track_id] : undefined;
          const company = row.company ?? "Unknown company";
          return (
            <TableRow key={row.id}>
              <TableCell className="font-medium">{company}</TableCell>
              <TableCell>{row.title ?? "Untitled role"}</TableCell>
              <TableCell>
                <FitBadge fit={row.best_fit} trackName={track?.name ?? null} minFit={track?.min_fit ?? null} />
              </TableCell>
              <TableCell>
                <div className="flex flex-wrap items-center gap-1.5">
                  <StatusBadge tone={PACKAGE_STATUS_TONE[row.status] ?? "slate"}>{`v${row.version} · ${row.status}`}</StatusBadge>
                  <StatusBadge tone="zinc">{row.mode}</StatusBadge>
                </div>
              </TableCell>
              <TableCell>
                {row.application_status ? (
                  <StatusBadge tone={statusTone(row.application_status)}>
                    {STATUS_LABEL[row.application_status as ApplicationStatus] ?? row.application_status}
                  </StatusBadge>
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>{formatRelative(row.created_at)}</TableCell>
              <TableCell>
                <Button size="sm" render={<Link href={`/jobs/${row.job_id}/packages/${row.id}`} />} aria-label={`Review ${company}`}>
                  Review
                </Button>
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
