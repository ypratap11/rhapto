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
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Pipeline", href: "/pipeline" }, { label: `${company} · ${title}` }]} />

      <div className="flex flex-wrap items-center gap-2">
        <div>
          <h2 className="text-base font-semibold">{company}</h2>
          <p className="text-sm text-muted-foreground">{title}</p>
        </div>
        <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
        {job.data?.unlisted_at ? <StatusBadge tone="muted">No longer listed</StatusBadge> : null}
      </div>

      <StatusControl application={application} />

      <div className="space-y-2 rounded-card border border-border bg-surface p-4">
        <label htmlFor="application-notes" className="text-sm font-medium">
          Notes
        </label>
        <Textarea id="application-notes" rows={4} value={notes} onChange={(e) => setNotes(e.target.value)} />
        <Button type="button" size="sm" onClick={saveNotes} disabled={patch.isPending}>
          Save notes
        </Button>
      </div>

      <div className="rounded-card border border-border bg-surface p-4">
        <h3 className="mb-2 text-sm font-semibold">Status history</h3>
        <ol className="space-y-1 text-sm text-muted-foreground">
          {application.status_history.map((h, i) => (
            <li key={`${h.status}-${h.at}-${i}`}>
              {STATUS_LABEL[h.status as ApplicationStatus] ?? h.status} · {formatDate(h.at)}
            </li>
          ))}
        </ol>
      </div>

      {application.package_id ? (
        <Link
          href={`/jobs/${application.job.id}/packages/${application.package_id}`}
          className="inline-block text-sm text-primary underline-offset-4 hover:underline"
        >
          Open the resume used →
        </Link>
      ) : null}

      {job.data ? <JdPane job={job.data} /> : job.isLoading ? <Skeleton className="h-72 w-full rounded-card" /> : null}
    </div>
  );
}
