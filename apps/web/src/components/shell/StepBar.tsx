"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FLOW_STEPS, flowPrompt, nextUp, stepForPath } from "@/lib/flow";
import { useJobs, usePackageList } from "@/lib/api/queries";
import { useSkipped } from "@/lib/skipped";

export function StepBar({ tailoring = false }: { tailoring?: boolean }) {
  const pathname = usePathname();
  const jobs = useJobs({ search: "", track: null, tab: "new", sort: "fit" });
  const review = usePackageList("review");
  const skipped = useSkipped();
  if (pathname.startsWith("/settings")) return null;
  const current = stepForPath(pathname, tailoring);
  const prompt = flowPrompt({ needsReview: review.data?.length ?? 0, next: nextUp(jobs.data ?? [], skipped, 1)[0] ?? null });
  return (
    <div className="border-b border-border bg-card/60">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-2 text-sm">
        <ol className="flex items-center gap-2" aria-label="Flow">
          {FLOW_STEPS.map((label, i) => (
            <li
              key={label}
              aria-current={i === current ? "step" : undefined}
              className={`flex items-center gap-2 ${i === current ? "font-medium text-foreground" : "text-muted-foreground"}`}
            >
              <span className={`inline-flex size-5 items-center justify-center rounded-full border text-xs ${i === current ? "border-foreground" : "border-border"}`}>
                {i + 1}
              </span>
              <span>{label}</span>
              {i < FLOW_STEPS.length - 1 ? (
                <span aria-hidden className="text-muted-foreground">
                  →
                </span>
              ) : null}
            </li>
          ))}
        </ol>
        {prompt ? (
          <Link href={prompt.href} className="underline">
            {prompt.text}
          </Link>
        ) : null}
      </div>
    </div>
  );
}
