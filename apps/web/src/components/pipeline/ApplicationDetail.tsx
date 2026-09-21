"use client";

import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";
import { JdPane } from "@/components/review/JdPane";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { Textarea } from "@/components/ui/textarea";
import { ApiError } from "@/lib/api/client";
import { useJob, usePatchApplication, type ApplicationOut } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";
import { StatusControl } from "./StatusControl";

/** This page owns all per-application detail (Task 7's job page deliberately shows only a status
 * pill and a link here): notes, status history, the follow-up date, the resume link and the JD. */
export function ApplicationDetail({ application }: { application: ApplicationOut }) {
  const job = useJob(application.job.id);
  const patch = usePatchApplication();
  const [notes, setNotes] = useState(application.notes);

  async function saveNotes() {
    try {
      await patch.mutateAsync({ id: application.id, body: { notes } });
      toast.success("Notes saved");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not save the notes");
    }
  }

  const company = application.job.company ?? "Unknown company";
  const title = application.job.title ?? "Untitled role";

  return (
    <div className="space-y-4">
      {/* Both crumbs stay: Breadcrumbs is also the document title, and spec §3 requires the two to
        * read the same, so trimming the trail would cost the tab title its company and role. */}
      <Breadcrumbs items={[{ label: "Pipeline", href: "/pipeline" }, { label: `${company} · ${title}` }]} />

      <div className="flex flex-wrap items-start gap-x-3 gap-y-1">
        <div className="min-w-0">
          <h2 className="truncate text-base font-semibold">{company}</h2>
          <p className="text-sm text-muted-foreground">{title}</p>
        </div>
        <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
        {job.data?.unlisted_at ? <StatusBadge tone="muted">No longer listed</StatusBadge> : null}
      </div>

      {/* Status, follow-up and notes are one editing surface, not three stacked cards -- as three
        * they pushed the JD, the thing you actually read here, ~900px down the page. */}
      <div className="space-y-4 rounded-card border border-border bg-surface p-4">
        <StatusControl application={application} />
        <div className="space-y-2">
          <label htmlFor="application-notes" className="text-sm font-medium">
            Notes
          </label>
          <Textarea id="application-notes" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Button type="button" size="sm" onClick={saveNotes} disabled={patch.isPending}>
            Save notes
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <details className="text-sm">
          <summary className="cursor-pointer text-muted-foreground hover:text-foreground">
            Status history ({application.status_history.length})
          </summary>
          <ol className="mt-2 space-y-1 text-sm text-muted-foreground">
            {application.status_history.map((h, i) => (
              <li key={`${h.status}-${h.at}-${i}`}>
                {STATUS_LABEL[h.status as ApplicationStatus] ?? h.status} · {formatDate(h.at)}
              </li>
            ))}
          </ol>
        </details>

        {application.package_id ? (
          <Link
            href={`/jobs/${application.job.id}/packages/${application.package_id}`}
            className="text-sm text-primary underline-offset-4 hover:underline"
          >
            Open the resume used →
          </Link>
        ) : null}
      </div>

      {job.data ? <JdPane job={job.data} /> : job.isLoading ? <Skeleton className="h-72 w-full rounded-card" /> : null}
    </div>
  );
}
