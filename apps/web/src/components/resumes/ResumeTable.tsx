import Link from "next/link";
import { FitRing } from "@/components/ui/fit-ring";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { PackageListItem } from "@/lib/api/queries";
import { PACKAGE_STATUS_LABEL, PACKAGE_STATUS_TONE } from "@/lib/status";

const COLUMNS = "md:grid-cols-[minmax(0,1.2fr)_minmax(0,1.6fr)_3rem_10rem_4rem]";

/** My resumes: one row per tailored resume. The whole row is the only link (one focus stop, one tap
 * target); "Review", or "Fix" once the truth check has held a resume back, is plain text inside it.
 * Emptiness is the page's job, so this always has at least one row to show. */
export function ResumeTable({ rows }: { rows: PackageListItem[] }) {
  return (
    <div>
      <div aria-hidden className={`hidden gap-4 px-4 pb-2 text-xs font-medium text-muted-foreground md:grid ${COLUMNS}`}>
        <span>Company</span>
        <span>Role</span>
        <span>Fit</span>
        <span>Status</span>
        <span />
      </div>
      <ul className="space-y-2">
        {rows.map((row) => {
          const company = row.company ?? "Unknown company";
          const role = row.title ?? "Untitled role";
          const statusLabel = (PACKAGE_STATUS_LABEL as Record<string, string>)[row.status] ?? row.status;
          const action = row.status === "blocked" ? "Fix" : "Review";
          return (
            <li key={row.id}>
              <Link
                href={`/jobs/${row.job_id}/packages/${row.id}`}
                aria-label={`${company}, ${role}, ${statusLabel}`}
                className={`hover-lift flex min-h-11 flex-col gap-2 rounded-card border border-border bg-surface px-4 py-3 text-sm md:grid md:items-center md:gap-4 ${COLUMNS}`}
              >
                <span className="font-medium">{company}</span>
                <span className="text-muted-foreground md:text-foreground">{role}</span>
                <span>
                  <FitRing fit={row.best_fit} size={32} />
                </span>
                <span>
                  <StatusBadge tone={PACKAGE_STATUS_TONE[row.status] ?? "neutral"}>{statusLabel}</StatusBadge>
                </span>
                <span className="font-medium text-primary md:text-right">{action}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
