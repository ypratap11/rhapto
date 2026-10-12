"use client";

import Link from "next/link";
import { CoachErrorNote } from "@/components/coach/CoachFrame";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import type { NextStep } from "@/lib/dashboard-view";
import type { TailorStarter } from "@/lib/coach/useStartTailor";
import { cn } from "cn";

const ACTION = "max-md:min-h-11 max-md:w-full";

/**
 * The one thing to do next, in the hero. Which step it is was decided by `pickNextStep`; this only draws it.
 * Review links to the package; a due follow-up opens that application's sheet (`onOpenApplication`); Tailor
 * uses the page's shared starter. Renders nothing when there is nothing to suggest.
 */
export function NextStepCard({
  step,
  starter,
  onOpenApplication,
}: {
  step: NextStep;
  starter: TailorStarter;
  onOpenApplication: (id: string) => void;
}) {
  if (step === null) return null;
  if (step.kind === "loading") return <Skeleton aria-hidden className="h-[74px] w-full rounded-2xl md:w-[26rem]" />;

  let title: string;
  let detail: string;
  let action: React.ReactNode;
  let note: React.ReactNode = null;

  switch (step.kind) {
    case "review": {
      const { draft } = step;
      title = draft.company ? `Review your ${draft.company} resume` : "Review your latest resume";
      detail = [draft.title, draft.best_fit !== null && draft.best_fit !== undefined ? `fit ${draft.best_fit}` : null].filter(Boolean).join(" · ");
      action = (
        <Link href={`/jobs/${draft.job_id}/packages/${draft.id}`} className={cn(buttonVariants({ size: "lg" }), ACTION)}>
          Review it
        </Link>
      );
      break;
    }
    case "review-list":
      title = "Review your resumes";
      detail = "Tailored resumes are waiting for you";
      action = (
        <Link href="/resumes?tab=review" className={cn(buttonVariants({ size: "lg" }), ACTION)}>
          Review them
        </Link>
      );
      break;
    case "followup":
      title = `Follow up with ${step.company ?? "this company"}`;
      detail = step.title ?? "";
      action = (
        <Button type="button" size="lg" className={ACTION} onClick={() => onOpenApplication(step.applicationId)}>
          Update status
        </Button>
      );
      break;
    case "tailor": {
      const { job } = step;
      title = `Tailor a resume for ${job.company ?? "this job"}`;
      detail = job.title ?? "";
      action = (
        <Button
          type="button"
          size="lg"
          className={ACTION}
          aria-label={`Tailor a resume for ${job.company ?? "this job"}`}
          disabled={starter.pickedId !== null}
          onClick={() => void starter.start(job)}
        >
          {starter.pickedId === job.id ? "Starting…" : "Tailor"}
        </Button>
      );
      if (starter.failedJobId === job.id) note = <CoachErrorNote error={starter.error} />;
      break;
    }
  }

  return (
    <section aria-label="Next step" className="space-y-2 md:w-[26rem]">
      <div className="flex items-center gap-4 rounded-2xl border border-border bg-surface p-4 shadow-card max-md:flex-wrap">
        <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-xl bg-band-peach font-bold text-primary">
          1
        </span>
        <div className="min-w-0 flex-1 max-md:basis-[calc(100%-3.5rem)]">
          <p className="font-semibold">{title}</p>
          {detail ? <p className="truncate text-[0.8rem] text-muted-foreground">{detail}</p> : null}
        </div>
        {action}
      </div>
      {note}
    </section>
  );
}
