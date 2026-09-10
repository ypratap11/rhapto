"use client";

import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { GuardrailPanel } from "@/components/review/GuardrailPanel";
import { JdPane } from "@/components/review/JdPane";
import { PackageActions } from "@/components/review/PackageActions";
import { RegenerateDialog } from "@/components/review/RegenerateDialog";
import { ResumePane } from "@/components/review/ResumePane";
import { SourceBlockCard } from "@/components/review/SourceBlockCard";
import { VersionSwitcher } from "@/components/review/VersionSwitcher";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useApplications, useBlocks, useJob, usePackage, usePackages, usePatchPackage, type Block, type ResumeDocument } from "@/lib/api/queries";
import { formatDate } from "@/lib/format";
import { parsePath } from "@/lib/resume-paths";
import { PACKAGE_STATUS_TONE } from "@/lib/status";

export default function PackageReviewPage() {
  const { jobId, packageId } = useParams<{ jobId: string; packageId: string }>();
  const router = useRouter();
  const job = useJob(jobId);
  const pkg = usePackage(packageId);
  const packages = usePackages(jobId);
  const blocks = useBlocks();
  const applications = useApplications();
  const patch = usePatchPackage();
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [regenOpen, setRegenOpen] = useState(false);

  const blockMap = useMemo(() => new Map<string, Block>((blocks.data ?? []).map((b) => [b.id, b])), [blocks.data]);
  const violationsByPath = useMemo(() => new Set((pkg.data?.guardrail_report.violations ?? []).map((v) => v.path)), [pkg.data]);
  const application = useMemo(() => {
    const columns = applications.data?.columns ?? {};
    return Object.values(columns).flat().find((a) => a.job.id === jobId) ?? null;
  }, [applications.data, jobId]);

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

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">{job.data.company}</p>
          <h1 className="text-2xl">{job.data.title ?? "Package review"}</h1>
          <p className="mt-1 flex items-center gap-2 text-sm text-muted-foreground">
            <StatusBadge tone={PACKAGE_STATUS_TONE[pkg.data.status] ?? "slate"}>{`v${pkg.data.version} · ${pkg.data.status}`}</StatusBadge>
            created {formatDate(pkg.data.created_at)} · {pkg.data.llm_calls} LLM calls · track {pkg.data.track_id}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {packages.data ? <VersionSwitcher jobId={jobId} packages={packages.data} currentId={packageId} /> : null}
          <PackageActions job={job.data} pkg={pkg.data} application={application} />
          <Button variant="outline" onClick={() => setRegenOpen(true)}>
            Regenerate
          </Button>
        </div>
      </div>
      <RegenerateDialog job={job.data} pkg={pkg.data} open={regenOpen} onOpenChange={setRegenOpen} />
      <div className="grid gap-6 lg:grid-cols-[1fr_1.2fr]">
        <JdPane job={job.data} />
        <div className="space-y-4">
          <ResumePane
            key={pkg.data.id}
            resume={pkg.data.resume}
            blocks={blockMap}
            selectedPath={selectedPath}
            onSelect={setSelectedPath}
            violationsByPath={violationsByPath}
            onSave={async (draft: ResumeDocument) => {
              try {
                const created = await patch.mutateAsync({ id: packageId, resume: draft });
                toast.success(created.status === "blocked" ? "Saved as v" + created.version + ", but guardrails blocked it" : "Saved as v" + created.version);
                router.push(`/jobs/${jobId}/packages/${created.id}`);
              } catch (e) {
                toast.error(e instanceof ApiError ? e.message : "Could not save");
              }
            }}
          />
          <GuardrailPanel report={pkg.data.guardrail_report} onSelect={setSelectedPath} />
          <SourceBlockCard block={selectedBlock} />
          <section className="rounded-md border border-border bg-card p-4 text-sm">
            <h3 className="mb-1 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cover note</h3>
            <p className="whitespace-pre-wrap">{pkg.data.cover_note}</p>
            <h3 className="mb-1 mt-4 font-sans text-xs font-semibold uppercase tracking-wide text-muted-foreground">Change log</h3>
            <p className="whitespace-pre-wrap text-muted-foreground">{pkg.data.change_log}</p>
          </section>
        </div>
      </div>
    </div>
  );
}
