"use client";

/** "Click a line to see its source": every bullet in a resume fragment opens the verified block it
 * came from. (The catch itself -- a draft line rejected by a guardrail -- lives in `CaughtDemo`, in
 * the hero.) Lives in its own client boundary -- Landing (both of
 * its mounts, `/` inside `TokenGate` and `/about` as a server component) must stay free of client
 * hooks, so all state is here, not there.
 *
 * Every bullet, org, role and period below is fictional, `profile.example`-style content
 * (Acme Analytics, Northwind Labs -- the same fictional employers `profile.example/blocks.yaml`
 * uses) written directly into this component. No API call, no backend, no real profile data. */

import { useId, useState } from "react";
import { BadgeCheck, ChevronRight } from "lucide-react";
import { cn } from "cn";

const ENTRIES = [
  {
    id: "northwind-onboarding",
    org: "Northwind Labs",
    role: "Data Platform Lead",
    period: "2023–2025",
    bullet:
      "Redesigned the customer onboarding pipeline, cutting time-to-first-value from 3 weeks to 4 days.",
  },
  {
    id: "acme-migration",
    org: "Acme Analytics",
    role: "Senior Data Program Manager",
    period: "2019–2023",
    bullet: "Migrated 12 pipelines to Snowflake with zero downtime, cutting warehouse cost 18%.",
  },
] as const;

export function ProvenanceDemo() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const baseId = useId();

  // The single-column ATS resume, rendered in CSS rather than screenshotted so it can never go stale
  // (item 4). It doubles as the interactive demo -- the same fragment that shows the artifact also
  // shows the mechanism, rather than two competing widgets on one page.
  return (
    <div className="max-w-3xl overflow-hidden rounded-card bg-surface shadow-card ring-1 ring-foreground/10">
      <div className="border-b border-border px-5 py-4">
        <p className="font-heading text-lg font-medium">Maya Chen</p>
        <p className="text-xs text-muted-foreground">
          Data &amp; platform leadership &middot; maya.chen@example.com
        </p>
      </div>
      <div className="px-5 py-4">
        <p className="font-mono text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Experience
        </p>
        <ul className="mt-3 space-y-4">
          {ENTRIES.map((entry, i) => {
            const isOpen = openIndex === i;
            const sourceId = `${baseId}-source-${i}`;
            return (
              <li key={entry.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 text-sm">
                  <span className="font-medium text-foreground">
                    {entry.org} &mdash; {entry.role}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">{entry.period}</span>
                </div>
                {/* The affordance: a chevron that is always visible (not a hover reveal) plus a
                    dotted underline on the bullet text itself, the same visual grammar readers
                    already know from inline citations/footnotes. A real <button> makes it tap-,
                    click- and keyboard-operable with no extra wiring, and `aria-expanded` gives a
                    screen reader the state without any visible instruction text. */}
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={sourceId}
                  onClick={() => setOpenIndex(isOpen ? null : i)}
                  className="hover-lift mt-1.5 flex w-full items-start gap-2 rounded-control px-2 py-1.5 text-left text-sm"
                >
                  <ChevronRight
                    aria-hidden
                    className={cn(
                      "mt-0.5 size-3.5 shrink-0 text-primary transition-transform",
                      isOpen && "rotate-90",
                    )}
                  />
                  <span className="underline decoration-primary/40 decoration-dotted underline-offset-4">
                    {entry.bullet}
                  </span>
                </button>
                {isOpen ? (
                  <div
                    id={sourceId}
                    className="mt-1.5 ml-2 rounded-card border border-diff-add/30 bg-diff-add-bg px-3 py-2.5 text-xs"
                  >
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1 font-mono font-medium text-diff-add">
                      <span className="flex items-center gap-1.5">
                        <BadgeCheck aria-hidden className="size-3.5" />
                        verified: true
                      </span>
                      <span className="font-normal text-foreground/70">block: {entry.id}</span>
                    </p>
                    <p className="mt-1 text-foreground/80">
                      {entry.org} &middot; {entry.role} &middot; {entry.period}
                    </p>
                    <p className="mt-1.5 font-medium text-foreground">&ldquo;{entry.bullet}&rdquo;</p>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>

    </div>
  );
}
