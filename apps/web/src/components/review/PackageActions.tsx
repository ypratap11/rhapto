"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { ChevronDown, Download, MoreHorizontal } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { useAnswers, useMarkApplied, useMarkPackageReady, type ApplicationOut, type JobOut, type PackageOut } from "@/lib/api/queries";
import { downloadAuthenticated, resumeFilename } from "@/lib/download";
import { APPLIED_STATUSES } from "@/lib/flow";
import { safeHttpUrl } from "@/lib/links";
import { useArchiveAndHide } from "./useArchiveAndHide";

const ITEM = "flex min-h-11 w-full items-center rounded-control px-3 text-left text-sm hover:bg-muted disabled:pointer-events-none disabled:opacity-50";
const PRIMARY_CLASS = "min-h-11 max-sm:w-full";
const SECONDARY_CLASS = "min-h-11";

/** A button that opens a short list of actions. A plain disclosure (not role=menu): each item is an
 * ordinary button or link, Escape and a click outside close it. */
function Menu({ label, variant, className, icon, children }: { label: string; variant: "default" | "outline"; className: string; icon?: ReactNode; children: (close: () => void) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (root.current && !root.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={root} className="relative max-sm:w-full">
      <Button ref={trigger} variant={variant} className={`${className} max-sm:w-full`} aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {icon}
        {label}
        {label === "More" ? null : <ChevronDown className="size-4" aria-hidden />}
      </Button>
      {open ? (
        <div className="absolute right-0 top-full z-20 mt-1 min-w-48 max-sm:left-0 max-sm:min-w-0 rounded-card border border-border bg-surface p-1 shadow-card">{children(() => setOpen(false))}</div>
      ) : null}
    </div>
  );
}

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
  const markReady = useMarkPackageReady();
  const { archiveAndHide, isPending: archiving } = useArchiveAndHide();
  const name = answers.data?.name;
  // A blocked resume's documents are never served (409), even when a legacy file from before that
  // rule is still on disk, so nothing here offers them.
  const blocked = pkg.status === "blocked";
  const applied = application !== null && (APPLIED_STATUSES as readonly string[]).includes(application.status);
  const state = blocked ? "blocked" : applied ? "applied" : pkg.status === "ready" ? "ready" : "draft";

  async function downloadFile(kind: "pdf" | "docx" | "zip") {
    const path = kind === "zip" ? `/api/v1/packages/${pkg.id}/download` : `/api/v1/packages/${pkg.id}/files/resume.${kind}`;
    try {
      await downloadAuthenticated(path, answers.isLoading ? undefined : resumeFilename(name, kind));
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Download failed");
    }
  }

  async function handleMarkReady() {
    try {
      await markReady.mutateAsync(pkg.id);
      toast.success("Marked ready to send");
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not mark this resume ready");
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

  async function handleArchive() {
    const label = `${job.company ?? "Unknown company"} · ${job.title ?? "Untitled role"}`;
    if (await archiveAndHide({ packageId: pkg.id, jobId: job.id, label })) router.push("/resumes");
  }

  const downloadMenu = (variant: "default" | "outline") => (
    <Menu label="Download" variant={variant} className={variant === "default" ? PRIMARY_CLASS : SECONDARY_CLASS} icon={<Download className="size-4" aria-hidden />}>
      {(close) => (
        <>
          <button type="button" className={ITEM} disabled={!pkg.has_docx} onClick={() => { close(); void downloadFile("docx"); }}>
            Word
          </button>
          <button type="button" className={ITEM} disabled={!pkg.has_pdf} onClick={() => { close(); void downloadFile("pdf"); }}>
            PDF
          </button>
        </>
      )}
    </Menu>
  );

  return (
    <div className="flex flex-wrap items-center gap-3 max-sm:flex-col max-sm:items-stretch">
      {state === "draft" ? (
        <Button className={PRIMARY_CLASS} onClick={() => void handleMarkReady()} disabled={markReady.isPending}>
          Mark ready to send
        </Button>
      ) : null}
      {state === "ready" ? downloadMenu("default") : null}
      {state === "draft" || state === "applied" ? downloadMenu("outline") : null}
      {state === "ready" ? (
        <Button variant="outline" className={SECONDARY_CLASS} onClick={() => void handleMarkApplied()} disabled={isPending}>
          I&apos;ve applied
        </Button>
      ) : null}
      <Menu label="More" variant="outline" className={SECONDARY_CLASS} icon={<MoreHorizontal className="size-4" aria-hidden />}>
        {(close) => (
          <>
            <button type="button" className={ITEM} onClick={() => { close(); onRegenerate(); }}>
              Regenerate
            </button>
            <button type="button" className={ITEM} onClick={() => { close(); void downloadFile("zip"); }}>
              Download everything
            </button>
            {postingUrl && !blocked ? (
              <a href={postingUrl} target="_blank" rel="noopener noreferrer" className={ITEM} onClick={close}>
                Open the job posting
              </a>
            ) : null}
            <button type="button" className={ITEM} disabled={archiving} onClick={() => { close(); void handleArchive(); }}>
              Archive
            </button>
          </>
        )}
      </Menu>
      {blocked ? (
        <p className="basis-full text-xs text-muted-foreground">
          This resume was stopped by the truth check, so the documents are not available. Fix the problems in the Truth check and regenerate; Download everything has the full report.
        </p>
      ) : null}
    </div>
  );
}
