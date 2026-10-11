"use client";

import { useId } from "react";
import { useRouter } from "next/navigation";
import { Download, ExternalLink, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useAnswers, useMarkApplied, type ApplicationOut, type JobOut, type PackageOut } from "@/lib/api/queries";
import { downloadAuthenticated, resumeFilename } from "@/lib/download";
import { APPLIED_STATUSES } from "@/lib/flow";
import { safeHttpUrl } from "@/lib/links";
import { STATUS_LABEL, statusTone, type ApplicationStatus } from "@/lib/status";

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
  const postingUrl = safeHttpUrl(job.url);
  const router = useRouter();
  const answers = useAnswers();
  const { markApplied, isPending } = useMarkApplied();
  const name = answers.data?.name;
  // A blocked package's resume documents are never served (409), even when a legacy file from
  // before that rule is still on disk, so the buttons must not offer them.
  const blocked = pkg.status === "blocked";
  const blockedNoteId = useId();
  const documentButtonProps = blocked ? { "aria-describedby": blockedNoteId } : {};

  async function downloadFile(kind: "pdf" | "docx" | "zip") {
    const path = kind === "zip" ? `/api/v1/packages/${pkg.id}/download` : `/api/v1/packages/${pkg.id}/files/resume.${kind}`;
    try {
      await downloadAuthenticated(path, answers.isLoading ? undefined : resumeFilename(name, kind));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    }
  }

  async function handleMarkApplied() {
    try {
      await markApplied(job, pkg.id, application);
      toast.success("Marked as applied", {
        action: { label: "Open dashboard", onClick: () => router.push("/dashboard") },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not update the application");
    }
  }

  const showStatusBadge = application !== null && (APPLIED_STATUSES as readonly string[]).includes(application.status);

  return (
    <div className="flex flex-wrap items-center gap-3">
      <div data-slot="button-group" className="inline-flex divide-x divide-border overflow-hidden rounded-full border border-border">
        <Button variant="outline" className="rounded-none border-0" onClick={() => downloadFile("pdf")} disabled={blocked || !pkg.has_pdf} {...documentButtonProps}>
          <Download className="size-4" aria-hidden /> Download PDF
        </Button>
        <Button variant="outline" className="rounded-none border-0" onClick={() => downloadFile("docx")} disabled={blocked || !pkg.has_docx} {...documentButtonProps}>
          <Download className="size-4" aria-hidden /> Download DOCX
        </Button>
        <Button variant="outline" className="rounded-none border-0" onClick={() => downloadFile("zip")}>
          <Download className="size-4" aria-hidden /> Download zip
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Button variant="outline" onClick={onRegenerate}>
          <RefreshCw className="size-4" aria-hidden /> Regenerate
        </Button>
        {showStatusBadge && application ? (
          <StatusBadge tone={statusTone(application.status)}>{STATUS_LABEL[application.status as ApplicationStatus] ?? application.status}</StatusBadge>
        ) : (
          <Button onClick={handleMarkApplied} disabled={isPending}>
            Mark applied
          </Button>
        )}
      </div>
      {blocked ? (
        <p id={blockedNoteId} className="basis-full text-xs text-muted-foreground">
          Guardrails blocked this package, so its resume documents are not available. Fix the violations and regenerate; the zip
          still holds the report.
        </p>
      ) : null}
      {postingUrl ? (
        <Button variant="outline" render={<a href={postingUrl} target="_blank" rel="noreferrer" />}>
          <ExternalLink className="size-4" aria-hidden /> Open posting
        </Button>
      ) : null}
    </div>
  );
}
