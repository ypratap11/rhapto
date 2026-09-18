import { FileText } from "lucide-react";
import type { TrackInfo } from "@/components/jobs/JobCard";
import { EmptyState } from "@/components/ui/empty-state";
import { FitRing } from "@/components/ui/fit-ring";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import type { PackageListFilter, PackageListItem } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";
import { PACKAGE_STATUS_TONE } from "@/lib/status";
import { ResumeRowActions } from "./ResumeRowActions";

const EMPTY_TEXT: Record<PackageListFilter, string> = {
  review: "Nothing to review",
  ready: "Nothing ready to apply",
  blocked: "No blocked resumes",
  applied: "Nothing applied yet",
};

/** The Resumes table (spec §3.4): one row per tailored package, bounded and sticky-headed (Task
 * 2's `Table`), with row actions delegated to `ResumeRowActions`. */
export function ResumeTable({
  rows,
  tracks,
  filter,
}: {
  rows: PackageListItem[];
  tracks: Record<string, TrackInfo>;
  filter: PackageListFilter;
}) {
  if (rows.length === 0) {
    return <EmptyState icon={FileText} title={EMPTY_TEXT[filter]} />;
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Company</TableHead>
          <TableHead>Role</TableHead>
          <TableHead>Fit</TableHead>
          <TableHead>Version · status</TableHead>
          <TableHead>Mode</TableHead>
          <TableHead>Created</TableHead>
          <TableHead>
            <span className="sr-only">Actions</span>
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
                <div className="flex flex-col items-start gap-0.5">
                  <FitRing fit={row.best_fit} size={32} />
                  {track ? <span className="text-xs text-muted-foreground">{track.name}</span> : null}
                </div>
              </TableCell>
              <TableCell>
                <StatusBadge tone={PACKAGE_STATUS_TONE[row.status] ?? "neutral"}>{`v${row.version} · ${row.status}`}</StatusBadge>
              </TableCell>
              <TableCell>
                <StatusBadge tone="muted">{row.mode}</StatusBadge>
              </TableCell>
              <TableCell>{formatRelative(row.created_at)}</TableCell>
              <TableCell>
                <ResumeRowActions row={row} />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
