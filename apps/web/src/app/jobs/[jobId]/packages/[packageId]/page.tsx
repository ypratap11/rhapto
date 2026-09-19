"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { Breadcrumbs } from "@/components/shell/Breadcrumbs";
import { ChangesPane } from "@/components/review/ChangesPane";
import { GuardrailPanel } from "@/components/review/GuardrailPanel";
import { JdPane } from "@/components/review/JdPane";
import { PackageActions } from "@/components/review/PackageActions";
import { RegenerateDialog } from "@/components/review/RegenerateDialog";
import { ResumePane } from "@/components/review/ResumePane";
import { SourceBlockCard } from "@/components/review/SourceBlockCard";
import { VersionSwitcher } from "@/components/review/VersionSwitcher";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useApplications, useBlocks, useJob, usePackage, usePackageList, usePackages, usePatchPackage, usePatchPackageEdits, type Block, type EditPatch, type ResumeDocument } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { nextReviewPackage } from "@/lib/flow";
import { parsePath } from "@/lib/resume-paths";
import { PACKAGE_STATUS_TONE } from "@/lib/status";

const TUNE_VIOLATION_PATH = /^edits\[(\d+)\]$/;

/** Bring a tune-mode guardrail path into view; those paths address the package, not resume nodes.
 *
 * `edits[i]` is one change card, `cover_note` is the cover note, and a bare `edits` is a violation
 * about the list as a whole (the six-edit cap), which belongs at the top of the Changes pane.
 */
function scrollToChange(path: string): void {
  const match = TUNE_VIOLATION_PATH.exec(path);
  const id = match ? `change-${match[1]}` : path === "cover_note" ? "cover-note" : path === "edits" ? "changes" : null;
  if (!id) return;
  document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

function PackageReviewPageInner() {
  const { jobId, packageId } = useParams<{ jobId: string; packageId: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const job = useJob(jobId);
  const pkg = usePackage(packageId);
  const packages = usePackages(jobId);
  const blocks = useBlocks();
  const applications = useApplications();
  const reviewQueue = usePackageList("review");
  const patch = usePatchPackage();
  const patchEdits = usePatchPackageEdits();
  // The job page's blocked-package GuardrailPanel links here with `?path=` (the violation the
  // reviewer clicked) rather than just the package — "here is what to fix", not just "here is the
  // package". A blocks-mode package uses `selectedPath` directly, below; a tune-mode one has no
  // such state (`ChangesPane` only flags violations inline via `violationsByPath`), so the effect
  // further down scrolls to the matching change card once the package has loaded instead.
  const initialPath = searchParams.get("path");
  const [selectedPath, setSelectedPath] = useState<string | null>(initialPath);
  const [regenOpen, setRegenOpen] = useState(searchParams.get("regenerate") === "1");
  const scrolledToInitialPath = useRef(false);

  const blockMap = useMemo(() => new Map<string, Block>((blocks.data ?? []).map((b) => [b.id, b])), [blocks.data]);
  const violationsByPath = useMemo(() => new Set((pkg.data?.guardrail_report.violations ?? []).map((v) => v.path)), [pkg.data]);
  const application = useMemo(() => {
    const columns = applications.data?.columns ?? {};
    return Object.values(columns).flat().find((a) => a.job.id === jobId) ?? null;
  }, [applications.data, jobId]);
  const nextPackage = useMemo(() => nextReviewPackage(reviewQueue.data ?? [], packageId), [reviewQueue.data, packageId]);

  useEffect(() => {
    if (scrolledToInitialPath.current || !initialPath || pkg.data?.mode !== "tune") return;
    scrolledToInitialPath.current = true;
    scrollToChange(initialPath);
  }, [initialPath, pkg.data]);

  if (job.error || pkg.error) return <ApiErrorBanner error={job.error ?? pkg.error} />;
  if (!job.data || !pkg.data) return <Skeleton className="h-64 w-full" />;

  const selectedBlock = (() => {
    if (!selectedPath) return null;
    const p = parsePath(selectedPath);
    const r = pkg.data.resume;
    if (p.kind === "summary") return blockMap.get(r.summary[p.index]?.source_block_id ?? "") ?? null;
    if (p.kind === "bullet") return blockMap.get(r.sections[p.section]?.entries[p.entry]?.bullets[p.bullet]?.source_block_id ?? "") ?? null;
    if (p.kind === "entry" || p.kind === "field") return blockMap.get(r.sections[p.section]?.entries[p.entry]?.source_block_id ?? "") ?? null;
    return null;
  })();

  const blocked = pkg.data.status === "blocked";
  const tune = pkg.data.mode === "tune";
  // A tune-mode violation path is `edits[<i>]`, which addresses a change card rather than a
  // resume path, so selecting one scrolls the card into view instead of driving the pane.
  const guardrailPanel = <GuardrailPanel report={pkg.data.guardrail_report} onSelect={tune ? scrollToChange : setSelectedPath} />;

  function saveNewVersion(created: { id: string; status: string; version: number }): void {
    toast.success(created.status === "blocked" ? "Saved as v" + created.version + ", but guardrails blocked it" : "Saved as v" + created.version);
    router.push(`/jobs/${jobId}/packages/${created.id}`);
  }

  const crumbLabel = `${job.data.company ?? "Unknown company"} · ${job.data.title ?? "Untitled role"}`;

  return (
    <div className="space-y-6">
      <Breadcrumbs items={[{ label: "Resumes", href: "/resumes" }, { label: crumbLabel, href: `/jobs/${jobId}` }, { label: `v${pkg.data.version}` }]} />
      <div className="sticky top-0 z-10 -mx-6 border-b border-border bg-background/95 px-6 py-3 backdrop-blur">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-sm text-muted-foreground">{job.data.company}</p>
            <h1 className="text-2xl">{job.data.title ?? "Package review"}</h1>
            <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
              <StatusBadge tone={PACKAGE_STATUS_TONE[pkg.data.status] ?? "neutral"}>{`v${pkg.data.version} · ${pkg.data.status}`}</StatusBadge>
              created {formatDate(pkg.data.created_at)} · {pkg.data.llm_calls} LLM calls · track {pkg.data.track_id}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {packages.data ? <VersionSwitcher jobId={jobId} packages={packages.data} currentId={packageId} /> : null}
            <PackageActions job={job.data} pkg={pkg.data} application={application} onRegenerate={() => setRegenOpen(true)} />
          </div>
        </div>
      </div>
      <RegenerateDialog job={job.data} pkg={pkg.data} open={regenOpen} onOpenChange={setRegenOpen} />
      {blocks.error || packages.error || applications.error ? (
        <div className="space-y-2">
          {blocks.error ? <ApiErrorBanner error={blocks.error} /> : null}
          {packages.error ? <ApiErrorBanner error={packages.error} /> : null}
          {applications.error ? <ApiErrorBanner error={applications.error} /> : null}
        </div>
      ) : null}
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <JdPane job={job.data} />
        <div className="space-y-4">
          {blocked ? guardrailPanel : null}
          {tune ? (
            <ChangesPane
              pkg={pkg.data}
              violationsByPath={violationsByPath}
              onSave={async (edits: EditPatch[]) => {
                try {
                  saveNewVersion(await patchEdits.mutateAsync({ id: packageId, edits }));
                } catch (e) {
                  toast.error(e instanceof ApiError ? e.message : "Could not save");
                }
              }}
            />
          ) : (
            <ResumePane
              key={pkg.data.id}
              resume={pkg.data.resume}
              blocks={blockMap}
              selectedPath={selectedPath}
              onSelect={setSelectedPath}
              violationsByPath={violationsByPath}
              onSave={async (draft: ResumeDocument) => {
                try {
                  saveNewVersion(await patch.mutateAsync({ id: packageId, resume: draft }));
                } catch (e) {
                  toast.error(e instanceof ApiError ? e.message : "Could not save");
                }
              }}
            />
          )}
          {blocked ? null : guardrailPanel}
          {tune ? null : <SourceBlockCard block={selectedBlock} />}
          <section className="rounded-md border border-border bg-card p-4 text-sm">
            <h3 id="cover-note" className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Cover note
            </h3>
            <p className="whitespace-pre-wrap">{pkg.data.cover_note}</p>
            <h3 className="mb-1 mt-4 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Change log</h3>
            <p className="whitespace-pre-wrap text-muted-foreground">{pkg.data.change_log}</p>
          </section>
        </div>
      </div>
      <div className="flex justify-end border-t border-border pt-4">
        {nextPackage ? (
          <Link href={`/jobs/${nextPackage.job_id}/packages/${nextPackage.id}`} className="text-sm font-medium text-primary underline-offset-4 hover:underline">
            Next tailored job →
          </Link>
        ) : (
          <p className="text-sm text-muted-foreground">All reviewed</p>
        )}
      </div>
    </div>
  );
}

export default function PackageReviewPage() {
  return (
    <Suspense fallback={<Skeleton className="h-64 w-full" />}>
      <PackageReviewPageInner />
    </Suspense>
  );
}
