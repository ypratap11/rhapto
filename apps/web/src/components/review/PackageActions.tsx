"use client";

import { Download, ExternalLink } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useCreateApplication, usePatchApplication, type ApplicationOut, type JobOut, type PackageOut } from "@/lib/api/queries";
import { downloadAuthenticated } from "@/lib/download";
import { STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";

export function PackageActions({ job, pkg, application }: { job: JobOut; pkg: PackageOut; application: ApplicationOut | null }) {
  const create = useCreateApplication();
  const patch = usePatchApplication();

  async function download() {
    try {
      await downloadAuthenticated(`/api/v1/packages/${pkg.id}/download`, `rhapto-package-v${pkg.version}.zip`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    }
  }

  async function markApplied() {
    try {
      if (application) await patch.mutateAsync({ id: application.id, body: { status: "applied" } });
      else {
        const created = await create.mutateAsync({ job_id: job.id, package_id: pkg.id });
        await patch.mutateAsync({ id: created.id, body: { status: "applied" } });
      }
      toast.success("Marked as applied");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update the application");
    }
  }

  const showStatusBadge = application !== null && application.status !== "queued";

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" onClick={download} disabled={!pkg.has_docx}>
        <Download className="size-4" aria-hidden /> Download zip
      </Button>
      {job.url ? (
        <Button variant="outline" render={<a href={job.url} target="_blank" rel="noreferrer" />}>
          <ExternalLink className="size-4" aria-hidden /> Open posting
        </Button>
      ) : null}
      {showStatusBadge && application ? (
        <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
      ) : (
        <Button onClick={markApplied} disabled={create.isPending || patch.isPending}>
          Mark applied
        </Button>
      )}
    </div>
  );
}
