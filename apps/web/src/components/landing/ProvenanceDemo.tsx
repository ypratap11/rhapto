"use client";

/** The "wow" the owner asked for: not a claim that Rhapto refuses to invent facts, but that claim
 * shown happening, on Rhapto's own output. Lives in its own client boundary -- Landing (both of
 * its mounts, `/` inside `TokenGate` and `/about` as a server component) must stay free of client
 * hooks, so all state is here, not there.
 *
 * Every bullet, org, role and period below is fictional, `profile.example`-style content
 * (Acme Analytics, Northwind Labs -- the same fictional employers `profile.example/blocks.yaml`
 * uses) written directly into this component. No API call, no backend, no real profile data. */

import { useId, useState } from "react";
import { BadgeCheck, ChevronRight, ShieldAlert } from "lucide-react";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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

// Attached to ENTRIES[1] (Acme Analytics) when the toggle is on: a third bullet on that entry
// that no verified block supports. Message and path shape match what
// `apps/api/src/rhapto/engine/guardrails/metrics.py::check_metrics` actually produces --
// `f"block {block.id!r} is not verified but the text contains metric(s): {offending}"` -- not
// invented copy.
const INVENTED_ENTRY_INDEX = 1;
const INVENTED = {
  bullet: "Increased forecast accuracy by 42% using a new ML model.",
  rule: "no-unverified-metrics",
  path: "sections[0].entries[1].bullets[2]",
  message: "block 'acme-forecast' is not verified but the text contains metric(s): 42%",
};

export function ProvenanceDemo() {
  const [openIndex, setOpenIndex] = useState<number | null>(null);
  const [showInvented, setShowInvented] = useState(false);
  const baseId = useId();
  const inventedLabelId = `${baseId}-invented-label`;

  // The single-column ATS resume, rendered in CSS rather than screenshotted so it can never go stale
  // (item 4). It doubles as the interactive demo -- the same fragment that shows the artifact also
  // shows the mechanism, rather than two competing widgets on one page. The whole demo is one card at
  // every width: the toggle used to sit in a second grid column from `sm` up, which put it out in the
  // right-hand margin, detached from the document it changes and clipped on a narrow desktop window.
  // A control belongs with the thing it controls.
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
                    <p className="flex items-center gap-1.5 font-mono font-medium text-diff-add">
                      <BadgeCheck aria-hidden className="size-3.5" />
                      verified: true
                    </p>
                    <p className="mt-1 text-foreground/80">
                      {entry.org} &middot; {entry.role} &middot; {entry.period}
                    </p>
                    <p className="mt-1.5 font-medium text-foreground">&ldquo;{entry.bullet}&rdquo;</p>
                  </div>
                ) : null}
                {i === INVENTED_ENTRY_INDEX && showInvented ? (
                  <div className="mt-2.5">
                    <p className="flex items-start gap-2 px-2 text-sm text-muted-foreground">
                      <span aria-hidden className="size-3.5 shrink-0" />
                      <span className="line-through">{INVENTED.bullet}</span>
                    </p>
                    <div className="mt-1.5 ml-2 rounded-card border border-destructive/30 bg-destructive/5 px-3 py-2.5 text-xs">
                      <p className="flex items-center gap-1.5 font-mono font-medium text-destructive">
                        <ShieldAlert aria-hidden className="size-3.5" />
                        Blocked before this document was produced
                      </p>
                      <p className="mt-1.5 flex flex-wrap items-center gap-2">
                        <span className="rounded-chip bg-destructive/10 px-2 py-0.5 font-mono text-xs font-medium text-destructive">
                          {INVENTED.rule}
                        </span>
                        <span className="font-mono text-muted-foreground">{INVENTED.path}</span>
                      </p>
                      <p className="mt-1.5 font-mono text-foreground/80">{INVENTED.message}</p>
                    </div>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      </div>

      {/* The toggle's own visible label states exactly what it does, so no separate instruction
          sentence is needed on the page for this interaction either. It sits at the foot of the
          same card, under the bullets it adds one to: `items-start` rather than `items-center` so
          the switch stays beside the label's first line when the label wraps at phone width. */}
      <div className="flex items-start gap-2.5 border-t border-border px-5 py-3.5">
        <Switch
          aria-labelledby={inventedLabelId}
          className="mt-0.5 shrink-0"
          checked={showInvented}
          onCheckedChange={(checked) => setShowInvented(checked === true)}
        />
        <Label
          id={inventedLabelId}
          className="cursor-pointer leading-snug"
          onClick={() => setShowInvented((v) => !v)}
        >
          What happens when it invents something
        </Label>
      </div>
    </div>
  );
}
