import { CheckCircle2, Circle } from "lucide-react";
import Link from "next/link";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { DashboardChecklist } from "@/lib/api/queries";

type Row = {
  label: string;
  done: (c: DashboardChecklist) => boolean;
  detail: (c: DashboardChecklist) => string;
  href: string;
};

function plural(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

/**
 * Four states, because "is there a key" is the question that lies. A user on this instance's key has
 * no key of their own and is not blocked; a user whose free runs are gone has a key configured and
 * IS blocked. Saying "configured" to both hides the ceiling one of them is about to hit, and saying
 * "no LLM key" to the first is simply false — they can tailor right now.
 *
 * The API decides which state applies (`services/trial.py::llm_setup_status`); this only words it.
 */
function llmKeyDetail(c: DashboardChecklist): string {
  switch (c.llm_key_source) {
    case "settings":
      return "Your own key";
    case "env":
      return "This instance's key";
    case "trial": {
      const left = c.trial_runs_left ?? 0;
      return left > 0 ? `${plural(left, "free run")} left on this instance's key` : "Free runs used — add your own key";
    }
    default:
      return "Add a provider key";
  }
}

// Fixed order per spec §2: setup steps first, then the two "quality" checks, then preferences.
const ROWS: Row[] = [
  {
    label: "Resume template",
    done: (c) => c.resume_template,
    detail: (c) => (c.resume_template ? "Uploaded" : "Upload the resume Rhapto tunes"),
    href: "/profile?card=resume-template",
  },
  {
    label: "Contact and answers",
    done: (c) => c.contact_answers,
    detail: (c) => (c.contact_answers ? "Complete" : "Name, email, phone, location, links"),
    href: "/profile?card=answers",
  },
  {
    label: "Tracks",
    done: (c) => c.tracks,
    detail: (c) => (c.tracks ? "At least one track" : "Pick a field and a role"),
    href: "/profile?card=tracks",
  },
  {
    label: "Verified blocks",
    done: (c) => c.blocks_verified,
    detail: (c) => `${c.verified_blocks} of ${c.total_blocks} verified`,
    href: "/profile?card=blocks",
  },
  {
    label: "Guardrails",
    done: (c) => c.guardrails,
    detail: (c) => (c.guardrails ? "Set" : "Decide what Rhapto may never write"),
    href: "/profile?card=guardrails",
  },
  {
    label: "Location preferences",
    done: (c) => c.location_preferences,
    detail: (c) => (c.location_preferences ? "Set" : "Home, preferred areas, remote"),
    href: "/profile?card=location",
  },
  // The five setup rows. Every detail string below is built from a value the API sent — never from
  // a second guess at the same condition — so the row cannot claim something the API disagrees with.
  {
    label: "LLM key",
    done: (c) => c.llm_key,
    detail: llmKeyDetail,
    href: "/settings",
  },
  {
    label: "Job sources",
    done: (c) => c.job_sources,
    detail: (c) => (c.job_sources ? `${plural(c.usable_sources, "source")} ready` : "No source can run yet"),
    href: "/settings",
  },
  {
    label: "Saved searches",
    done: (c) => c.saved_searches,
    detail: (c) => (c.saved_searches ? `${c.active_searches} active` : "Save a search so polls have something to run"),
    href: "/settings",
  },
  {
    label: "Jobs found",
    done: (c) => c.jobs_found,
    detail: (c) => (c.jobs_found ? "Jobs are arriving" : "No jobs yet — run a poll"),
    href: "/jobs",
  },
  {
    label: "Block dates",
    done: (c) => c.dateless_blocks === 0,
    detail: (c) => (c.dateless_blocks === 0 ? "Every block has a period" : `${c.dateless_blocks} need a period`),
    href: "/profile?card=blocks",
  },
];

/**
 * Spec §2 plus §8: six profile checks and five setup rows, each an "Edit" deep link into the place
 * that fixes it. The setup rows exist so a stranger on a dashboard of zeroes always has a next
 * action instead of a screen that says nothing.
 *
 * Three states share the one `checklist` prop, and a caller must keep them apart: `loading` (the
 * `useDashboard()` call is still in flight — render a skeleton, not a row of false "not done"
 * checks), `error` (the call settled but failed — say so, don't pretend there is nothing to show),
 * and a settled `checklist` of `null` with neither flag set (defensive only; `DashboardOut.checklist`
 * is required, so a successful response always has one) — which renders nothing, as before.
 */
export function ProfileChecklist({
  checklist,
  loading = false,
  error = false,
}: {
  checklist: DashboardChecklist | null;
  loading?: boolean;
  error?: boolean;
}) {
  if (loading) {
    return (
      <section
        aria-labelledby="checklist-heading"
        className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card"
        data-testid="checklist-skeleton"
      >
        <h2 id="checklist-heading" className="font-sans text-base font-semibold">
          Profile checklist
        </h2>
        <ul className="space-y-2" aria-hidden="true">
          {/* `ROWS.length`, not a literal: a skeleton that is shorter than the list it stands in
              for makes the page jump on every load, and a hard-coded count silently stops matching
              the moment a row is added. */}
          {Array.from({ length: ROWS.length }).map((_, i) => (
            <li key={i} className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Skeleton className="size-4 shrink-0 rounded-full" />
                <div className="space-y-1.5">
                  <Skeleton className="h-3.5 w-28" />
                  <Skeleton className="h-3 w-36" />
                </div>
              </div>
              <Skeleton className="h-3 w-8" />
            </li>
          ))}
        </ul>
      </section>
    );
  }
  if (error) {
    return (
      <section
        aria-labelledby="checklist-heading"
        className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card"
        data-testid="checklist-error"
      >
        <div className="flex items-center justify-between gap-2">
          <h2 id="checklist-heading" className="font-sans text-base font-semibold">
            Profile checklist
          </h2>
          <StatusBadge tone="danger">Couldn&rsquo;t load</StatusBadge>
        </div>
        <p className="text-sm text-muted-foreground">Try refreshing the page.</p>
      </section>
    );
  }
  if (!checklist) return null;
  return (
    <section aria-labelledby="checklist-heading" className="space-y-3 rounded-card border border-border bg-surface p-4 shadow-card">
      <h2 id="checklist-heading" className="font-sans text-base font-semibold">
        Profile checklist
      </h2>
      <ul className="space-y-2">
        {ROWS.map((row) => {
          const done = row.done(checklist);
          const Icon = done ? CheckCircle2 : Circle;
          return (
            <li key={row.label} data-done={done ? "true" : "false"} className="flex items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2">
                <Icon aria-hidden="true" className={`size-4 shrink-0 ${done ? "text-fit-high" : "text-muted-foreground"}`} />
                <div className="min-w-0">
                  <p className="text-sm font-medium">{row.label}</p>
                  <p className="truncate text-xs text-muted-foreground">{row.detail(checklist)}</p>
                </div>
              </div>
              <Link href={row.href} className="shrink-0 text-xs underline-offset-4 hover:underline">
                Edit
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
