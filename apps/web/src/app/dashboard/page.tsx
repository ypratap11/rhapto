"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ApplicationsSection } from "@/components/dashboard/ApplicationsSection";
import { FinishSetupLine } from "@/components/dashboard/FinishSetupLine";
import { RecommendedShort } from "@/components/dashboard/RecommendedShort";
import { WaitingBanner } from "@/components/dashboard/WaitingBanner";
import { ApiErrorBanner } from "@/components/shell/ApiErrorBanner";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "cn";
import { Skeleton } from "@/components/ui/skeleton";
import { useApplications, useDashboard, useResumeDocument } from "@/lib/api/queries";
import { isApplication } from "@/lib/applications-view";

/** The signed-in home: where my applications stand, and what to apply to next. One centred column. */
export default function DashboardPage() {
  const applications = useApplications();
  const resume = useResumeDocument();
  const dashboard = useDashboard();

  const rows = useMemo(
    () => Object.values(applications.data?.columns ?? {}).flat().filter(isApplication),
    [applications.data],
  );

  // Follow-ups due today or overdue, by application id (the old dashboard's "Follow up today").
  const dueIds = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    return new Set((dashboard.data?.due_followups ?? []).filter((f) => f.follow_up_at.slice(0, 10) <= today).map((f) => f.application_id));
  }, [dashboard.data]);

  // A paused query (no network) is not "empty": same two-boolean shape the old page used.
  const hasIssue = Boolean(applications.error) || applications.isPaused;
  const loading = applications.isLoading || resume.isLoading;
  const noResume = resume.data === null && rows.length === 0 && !hasIssue;

  return (
    <div className="mx-auto max-w-3xl space-y-8">
      <h1 className="font-serif text-2xl font-medium">Dashboard</h1>
      {hasIssue ? <ApiErrorBanner error={applications.error ?? "Can't reach Rhapto's API."} /> : null}
      {loading ? (
        <Skeleton className="h-48 w-full rounded-card" />
      ) : noResume ? (
        <section className="mx-auto flex max-w-md flex-col items-center gap-3 rounded-card border border-border bg-surface p-8 text-center shadow-card">
          <h2 className="font-heading text-xl font-medium">Start with your resume</h2>
          <p className="text-sm text-muted-foreground">Upload a Word (.docx) file. Rhapto only ever uses what&apos;s in it.</p>
          <Link href="/start" className={cn(buttonVariants({ size: "lg" }), "max-md:min-h-11")}>
            Upload resume
          </Link>
        </section>
      ) : (
        <>
          <WaitingBanner count={dashboard.data?.needs_review_count ?? 0} />
          <FinishSetupLine checklist={dashboard.data?.checklist} />
          {rows.length > 0 ? (
            <ApplicationsSection rows={rows} dueIds={dueIds} />
          ) : hasIssue ? null : (
            <section aria-labelledby="applications-heading" className="space-y-2">
              <h2 id="applications-heading" className="font-sans text-base font-semibold">Your applications</h2>
              <p className="text-sm text-muted-foreground">
                Your applications will show here. After you tailor a resume and send it, mark it as applied and track replies here.
              </p>
            </section>
          )}
          <RecommendedShort />
        </>
      )}
    </div>
  );
}
