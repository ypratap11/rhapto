import Link from "next/link";
import { buttonVariants } from "@/components/ui/button";
import { JobRow } from "@/components/ui/job-row";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { PackageListItem } from "@/lib/api/queries";
import { formatRelative } from "@/lib/format";
import { PACKAGE_STATUS_LABEL, PACKAGE_STATUS_TONE } from "@/lib/status";
import { cn } from "cn";

/** Plain words for how a resume was made: "tune" edits the wording, anything else rebuilds it. */
export const modeLabel = (mode: string): "Light touch" | "Full rewrite" => (mode === "tune" ? "Light touch" : "Full rewrite");

/** My resumes: one row per tailored resume, shaped like the Dashboard's job rows. The whole row is the
 * only link (one focus stop, one tap target); "Review", or "Fix" once the truth check has held a resume
 * back, is a button-looking `span` inside it, never a real button. Emptiness is the page's job, so this
 * always has at least one row to show. */
export function ResumeTable({ rows }: { rows: PackageListItem[] }) {
  return (
    <ul className="space-y-2.5">
      {rows.map((row) => {
        const company = row.company ?? "Unknown company";
        const role = row.title ?? "Untitled role";
        const statusLabel = (PACKAGE_STATUS_LABEL as Record<string, string>)[row.status] ?? row.status;
        const made = `Made ${formatRelative(row.created_at)}`;
        const mode = modeLabel(row.mode);
        const blocked = row.status === "blocked";
        return (
          <li key={row.id}>
            <Link
              href={`/jobs/${row.job_id}/packages/${row.id}`}
              aria-label={`${company}, ${role}, ${statusLabel}, ${made.toLowerCase()}, ${mode}`}
              className="block min-h-11 rounded-2xl outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <JobRow
                as="div"
                fit={row.best_fit}
                title={role}
                meta={
                  <>
                    <span>{company}</span>
                    <span>{made}</span>
                    <span>{mode}</span>
                    <StatusBadge tone={PACKAGE_STATUS_TONE[row.status] ?? "neutral"}>{statusLabel}</StatusBadge>
                  </>
                }
                actions={
                  <span className={cn(buttonVariants(blocked ? { variant: "outline", size: "sm" } : { size: "sm" }), "max-md:min-h-0")}>
                    {blocked ? "Fix" : "Review"}
                  </span>
                }
              />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
