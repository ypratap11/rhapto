"use client";

import { useRouter } from "next/navigation";
import { Download, ExternalLink, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useAnswers, useMarkApplied, type ApplicationOut, type JobOut, type PackageOut } from "@/lib/api/queries";
import { downloadAuthenticated, resumeFilename } from "@/lib/download";
import { STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";

const APPLIED_STATUSES: ReadonlySet<ApplicationStatus> = new Set(["applied", "screen", "interview", "offer", "closed"]);

export function PackageActions({
  job,
  pkg,
  application,
  onRegenerate,
}: {
  job: JobOut;
  pkg: PackageOut;
  application: ApplicationOut | null;
  onRegenerate: () => void;
}) {
  const router = useRouter();
  const answers = useAnswers();
  const { markApplied, isPending } = useMarkApplied();
  const name = answers.data?.name;

  async function downloadFile(kind: "pdf" | "docx" | "zip") {
    const path = kind === "zip" ? `/api/v1/packages/${pkg.id}/download` : `/api/v1/packages/${pkg.id}/files/resume.${kind}`;
    try {
      await downloadAuthenticated(path, resumeFilename(name, kind));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    }
  }

  async function handleMarkApplied() {
    try {
      await markApplied(job, pkg.id, application);
      toast.success("Marked as applied", {
        action: { label: "Open pipeline", onClick: () => router.push("/pipeline") },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update the application");
    }
  }

  const showStatusBadge = application !== null && APPLIED_STATUSES.has(application.status as ApplicationStatus);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button variant="outline" onClick={() => downloadFile("pdf")} disabled={!pkg.has_pdf}>
        <Download className="size-4" aria-hidden /> Download PDF
      </Button>
      <Button variant="outline" onClick={() => downloadFile("docx")} disabled={!pkg.has_docx}>
        <Download className="size-4" aria-hidden /> Download DOCX
      </Button>
      <Button variant="outline" onClick={() => downloadFile("zip")}>
        <Download className="size-4" aria-hidden /> Download zip
      </Button>
      <Button variant="outline" onClick={onRegenerate}>
        <RefreshCw className="size-4" aria-hidden /> Regenerate
      </Button>
      {job.url ? (
        <Button variant="outline" render={<a href={job.url} target="_blank" rel="noreferrer" />}>
          <ExternalLink className="size-4" aria-hidden /> Open posting
        </Button>
      ) : null}
      {showStatusBadge && application ? (
        <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
      ) : (
        <Button onClick={handleMarkApplied} disabled={isPending}>
          Mark applied
        </Button>
      )}
    </div>
  );
}
