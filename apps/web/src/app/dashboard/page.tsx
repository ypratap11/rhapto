"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { ApplicationsSection } from "@/components/dashboard/ApplicationsSection";
import { DashboardTiles } from "@/components/dashboard/DashboardTiles";
import { FinishSetupLine } from "@/components/dashboard/FinishSetupLine";
import { NextStepCard } from "@/components/dashboard/NextStepCard";
import { RecommendedShort } from "@/components/dashboard/RecommendedShort";
import { ApplicationSheet } from "@/components/pipeline/ApplicationSheet";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { PageHero } from "@/components/shell/PageHero";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useAnswers,
  useApplications,
  useDashboard,
  usePackageList,
  useRecommendedJobs,
  useResumeDocument,
  useTracks,
} from "@/lib/api/queries";
import { type ChipId, chipCounts, isApplication } from "@/lib/applications-view";
import { useStartTailor } from "@/lib/coach/useStartTailor";
import { firstName, greeting, pickNextStep, strongMatchCount, summaryLine } from "@/lib/dashboard-view";
import { cn } from "cn";

/** On a phone the applications sit below the jobs; a tile that filters them takes the person there. */
function scrollToApplications() {
  if (typeof window === "undefined" || !window.matchMedia?.("(max-width: 1023px)").matches) return;
  const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.getElementById("applications-heading")?.scrollIntoView?.({ behavior: calm ? "auto" : "smooth", block: "start" });
}

/**
 * The signed-in home: a greeting, the one next step, four status tiles, then recommended jobs beside
 * where my applications stand. Full header width. Not server-rendered (TokenGate renders nothing on the
 * server), so reading the browser's clock for the greeting cannot cause a hydration mismatch.
 */
export default function DashboardPage() {
  const applications = useApplications();
  const resume = useResumeDocument();
  const dashboard = useDashboard();
  const answers = useAnswers();
  const recommended = useRecommendedJobs(0);
  const tracks = useTracks();
  const starter = useStartTailor();
  const [chip, setChip] = useState<ChipId>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Unfiltered board first: a due follow-up can belong to an application that is not a "real" one in the list.
  const board = useMemo(() => Object.values(applications.data?.columns ?? {}).flat(), [applications.data]);
  const rows = useMemo(() => board.filter(isApplication), [board]);
  const counts = useMemo(() => chipCounts(rows), [rows]);

  // Follow-ups due today or overdue, by application id.
  const dueFollowUps = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return (dashboard.data?.due_followups ?? []).filter((f) => f.follow_up_at.slice(0, 10) <= today);
  }, [dashboard.data]);
  const dueIds = useMemo(() => new Set(dueFollowUps.map((f) => f.application_id)), [dueFollowUps]);

  const dashboardState = dashboard.error ? "error" : dashboard.data ? "ready" : "loading";
  const reviewCount = dashboard.data?.needs_review_count ?? 0;
  const drafts = usePackageList("review", reviewCount > 0);
  const draftsState = drafts.error ? "error" : drafts.data ? "ready" : "loading";
  const jobsState = recommended.isLoading ? "loading" : recommended.error && recommended.data.length === 0 ? "error" : "ready";

  // The first due follow-up whose application is on the board (a follow-up we can't open isn't suggested).
  const dueFollowUp = (() => {
    const f = dueFollowUps.find((d) => board.some((a) => a.id === d.application_id));
    return f ? { applicationId: f.application_id, company: f.job.company, title: f.job.title } : null;
  })();

  const next = pickNextStep({
    dashboard: dashboardState,
    reviewCount,
    drafts: draftsState,
    newestDraft: drafts.data?.[0],
    dueFollowUp,
    jobs: jobsState,
    topJob: recommended.data[0],
  });

  const selected = board.find((a) => a.id === selectedId) ?? null;

  // A paused query (no network) is not "empty": same two-boolean shape the old page used.
  const hasIssue = Boolean(applications.error) || applications.isPaused;
  const loading = applications.isLoading || resume.isLoading;
  const noResume = resume.data === null && rows.length === 0 && !hasIssue;
  const bannerError = applications.error ?? dashboard.error ?? "Can't reach Rhapto's API.";

  const title = answers.isLoading ? (
    <>
      <span className="sr-only">Dashboard</span>
      <Skeleton aria-hidden className="h-10 w-72 max-w-full" />
    </>
  ) : (
    greeting(new Date().getHours(), firstName(answers.data?.name))
  );

  const summaryReady = dashboardState !== "loading" && !recommended.isLoading && !tracks.isLoading;
  const subtitle = loading || noResume ? null : summaryReady ? (
    summaryLine({
      strong: strongMatchCount(recommended.data, tracks.data),
      review: dashboardState === "ready" ? reviewCount : null,
    })
  ) : (
    <Skeleton aria-hidden className="h-6 w-80 max-w-full" />
  );

  function pickChip(id: Exclude<ChipId, "all" | "closed">) {
    setChip((current) => (current === id ? "all" : id));
    scrollToApplications();
  }

  return (
    <>
      <PageHero
        title={title}
        subtitle={subtitle}
        aside={
          loading ? undefined : noResume ? (
            <section className="flex max-w-md flex-col items-start gap-3 rounded-2xl border border-border bg-surface p-5 shadow-card">
              <h2 className="font-serif text-xl font-medium">Start with your resume</h2>
              <p className="text-sm text-muted-foreground">Upload a Word (.docx) file. Your tailored resumes are built from what&apos;s in it.</p>
              <Link href="/start" className={cn(buttonVariants({ size: "lg" }), "max-md:min-h-11")}>
                Upload resume
              </Link>
            </section>
          ) : (
            <NextStepCard step={next} starter={starter} onOpenApplication={setSelectedId} />
          )
        }
      >
        {loading ? (
          <div aria-hidden className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-[102px] rounded-2xl" />
            ))}
          </div>
        ) : noResume ? null : (
          <DashboardTiles
            reviewCount={dashboardState === "ready" ? reviewCount : null}
            counts={hasIssue && rows.length === 0 ? null : counts}
            chip={chip}
            onChip={pickChip}
          />
        )}
      </PageHero>
      {hasIssue || dashboard.error ? (
        <div className="mb-6">
          <ApiErrorBanner error={bannerError} />
        </div>
      ) : null}
      {loading || noResume ? null : <FinishSetupLine checklist={dashboard.data?.checklist} />}
      {loading ? (
        <div aria-hidden className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <div className="space-y-2.5">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-[84px] rounded-2xl" />
            ))}
          </div>
          <Skeleton className="h-64 rounded-2xl" />
        </div>
      ) : noResume ? null : (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
          <RecommendedShort starter={starter} hideErrorFor={next?.kind === "tailor" ? next.job.id : null} />
          {rows.length > 0 ? (
            <ApplicationsSection rows={rows} dueIds={dueIds} chip={chip} onChipChange={setChip} onSelect={setSelectedId} />
          ) : hasIssue ? null : (
            <section aria-labelledby="applications-heading" className="space-y-2">
              <h2 id="applications-heading" className="font-serif text-xl font-semibold">
                Your applications
              </h2>
              <p className="rounded-2xl border border-dashed border-border p-4 text-sm text-muted-foreground">
                Your applications will show here. After you tailor a resume and send it, mark it as applied and track replies here.
              </p>
            </section>
          )}
        </div>
      )}
      <ApplicationSheet application={selected} open={selected !== null} onOpenChange={(open) => !open && setSelectedId(null)} />
    </>
  );
}
