"use client";

/** The hero's proof: what Rhapto's checks do INSIDE a run, shown on three fictional drafts.
 *
 * What is and is not true, because this is the one place on the page that could overclaim:
 *  - The drafts, reports and paths below are what the guardrails produce while a run is in progress.
 *    After a caught line is repaired (the pipeline gives the model one fix attempt) the rejected
 *    draft and its report are discarded; the visitor is shown the rule only when the package ends up
 *    blocked. So the copy says "inside a run" and never says the user is shown every catch.
 *  - Provenance, metrics and completeness (every selected role, project and credential keeps an
 *    entry) are unconditional on model output; completeness alone is skipped on a user's own hand
 *    edit (`registry.run_guardrails(include_completeness=...)`). The entities check is on by default
 *    but is a per-account setting, so its case says "on by default".
 *  - A blocked package now produces no resume document in any mode (the pipeline, the hand-edit
 *    path and both serving routes enforce it). The copy here does not rely on that claim and does
 *    not need to; if it ever makes it, pin it to `tests/unit/test_package_serving.py`.
 *
 * The rule names, paths and messages are quoted EXACTLY from
 * `apps/api/src/rhapto/engine/guardrails/{metrics,entities,provenance}.py`, and pinned by
 * `CaughtDemo.test.tsx`. Change the API wording and this file together, or neither.
 *
 * Own client boundary: `Landing` is a server component at `/` and `/about` and must stay hook-free.
 *
 * Rendering contract (SSR-safe): the first render is a constant, case 0, complete and legible with no
 * JS. `matchMedia` and the timer are touched only inside an effect. The stamp's motion is CSS
 * (`motion-safe:`) keyed by the case index, and its resting style is the fully visible stamp.
 *
 * Every person and employer is fictional (`profile.example` style). */

import { useEffect, useId, useState } from "react";
import { ShieldAlert } from "lucide-react";
import { prefersReducedMotion } from "./JourneyWalkthrough";

const ADVANCE_MS = 6000;

type Bullet = { text: string; rejected?: boolean };
type Entry = { head: string; headRejected?: boolean; bullets: Bullet[] };

type Case = {
  id: string;
  label: string;
  rule: string;
  path: string;
  message: string;
  /** Whether the visitor can turn this check off. Only the two unconditional checks say "always". */
  gate: string;
  entries: Entry[];
  sent: { text: string; block: string };
};

const CASES: readonly Case[] = [
  {
    id: "metrics",
    label: "Unverified number",
    rule: "no-unverified-metrics",
    path: "sections[0].entries[1].bullets[1]",
    message: "block 'acme-forecast' is not verified but the text contains metric(s): 42%",
    gate: "This check always runs.",
    entries: [
      {
        head: "Northwind Labs — Data Platform Lead",
        bullets: [
          {
            text: "Redesigned the customer onboarding pipeline, cutting time-to-first-value from 3 weeks to 4 days.",
          },
        ],
      },
      {
        head: "Acme Analytics — Senior Data Program Manager",
        bullets: [
          { text: "Migrated 12 pipelines to Snowflake with zero downtime, cutting warehouse cost 18%." },
          { text: "Increased forecast accuracy by 42% using a new ML model.", rejected: true },
        ],
      },
    ],
    sent: { text: "Built a new ML model to improve forecast accuracy.", block: "acme-forecast" },
  },
  {
    id: "entities",
    label: "Invented job title",
    rule: "no-invented-entities",
    path: "sections[0].entries[0]",
    message:
      "role 'Director of Data Platform' does not match block 'northwind-onboarding' ('Data Platform Lead')",
    gate: "This check is on by default, and can be switched off.",
    entries: [
      {
        head: "Northwind Labs — Director of Data Platform",
        headRejected: true,
        bullets: [
          {
            text: "Redesigned the customer onboarding pipeline, cutting time-to-first-value from 3 weeks to 4 days.",
          },
        ],
      },
    ],
    sent: { text: "Northwind Labs — Data Platform Lead", block: "northwind-onboarding" },
  },
  {
    id: "provenance",
    label: "Unsourced line",
    rule: "provenance",
    path: "sections[0].entries[0]",
    message: "source block 'acme-board' does not exist",
    gate: "This check always runs.",
    entries: [
      {
        head: "Acme Analytics — Advisory Board Member",
        headRejected: true,
        bullets: [],
      },
    ],
    sent: { text: "Acme Analytics — Senior Data Program Manager", block: "acme-migration" },
  },
];

function Rejected({ children }: { children: React.ReactNode }) {
  return (
    <>
      <span className="sr-only">Rejected draft: </span>
      <span className="text-destructive line-through decoration-destructive/60">{children}</span>
    </>
  );
}

export function CaughtDemo() {
  // Constant initial state: identical on the server and the first client render.
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  // Empty until a visitor presses a button, so auto-advance never announces.
  const [announcement, setAnnouncement] = useState("");
  const groupLabelId = useId();
  const current = CASES[index]!;

  useEffect(() => {
    if (paused || prefersReducedMotion()) return;
    const timer = setInterval(() => {
      if (document.hidden) return;
      setIndex((i) => (i + 1) % CASES.length);
    }, ADVANCE_MS);
    return () => clearInterval(timer);
  }, [paused]);

  const pause = () => setPaused(true);

  return (
    <div
      className="min-w-0 overflow-hidden rounded-card bg-surface shadow-card ring-1 ring-foreground/10"
      onPointerEnter={pause}
      onFocus={pause}
      onClick={pause}
    >
      <div className="border-b border-border px-4 py-3">
        <p className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
          What happens inside a run
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          The model&rsquo;s draft is checked before you see the resume. The draft gets one repair
          pass; only if that fails is the package blocked, and then you see the rule that fired.
        </p>
      </div>

      <div className="px-4 pt-3">
        <p id={groupLabelId} className="sr-only">
          Example of a draft the checks catch
        </p>
        <div role="group" aria-labelledby={groupLabelId} className="flex flex-wrap gap-2">
          {CASES.map((c, i) => (
            <button
              key={c.id}
              type="button"
              aria-pressed={i === index}
              onClick={() => {
                setIndex(i);
                setAnnouncement(`Showing ${c.label}. Rule ${c.rule}: ${c.message}`);
              }}
              className="rounded-control border border-border px-2.5 py-1 text-xs font-medium text-foreground outline-none hover:bg-surface-muted focus-visible:ring-2 focus-visible:ring-ring aria-pressed:border-primary aria-pressed:bg-primary aria-pressed:text-primary-foreground"
            >
              {c.label}
            </button>
          ))}
        </div>
      </div>

      <div className="px-4 py-3">
        <p className="font-mono text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Experience
        </p>
        <ul className="mt-2 space-y-3">
          {current.entries.map((entry) => (
            <li key={entry.head} data-testid="entry" className="min-w-0">
              <p className="text-sm font-medium [overflow-wrap:anywhere]">
                {entry.headRejected ? <Rejected>{entry.head}</Rejected> : entry.head}
              </p>
              {entry.bullets.length > 0 ? (
                <ul className="mt-1 space-y-1.5 pl-3">
                  {entry.bullets.map((b) => (
                    <li
                      key={b.text}
                      data-testid="bullet"
                      className="text-xs text-foreground/80 [overflow-wrap:anywhere]"
                    >
                      {b.rejected ? <Rejected>{b.text}</Rejected> : b.text}
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          ))}
        </ul>
      </div>

      <div className="border-t border-destructive/30 bg-destructive/5 px-4 py-3 text-xs">
        <div className="flex items-center justify-between gap-2">
          <p className="flex items-center gap-1.5 font-mono font-medium text-destructive">
            <ShieldAlert aria-hidden className="size-3.5" />
            Guardrail report
          </p>
          {/* Decorative: the meaning is in the text beside it and the "Rejected draft:" prefix.
              Resting style is fully visible; only `motion-safe:` adds the entrance, and `key`
              replays it for each case. */}
          <span
            key={index}
            data-testid="caught-stamp"
            aria-hidden="true"
            className="rounded-control border-[3px] border-destructive px-3 py-1 font-mono text-base font-extrabold tracking-[0.2em] text-destructive uppercase -rotate-6 sm:text-lg motion-safe:animate-in motion-safe:fade-in motion-safe:zoom-in-150 motion-safe:duration-300"
          >
            Caught
          </span>
        </div>
        <p className="mt-2 flex flex-wrap items-center gap-2">
          <span className="rounded-chip bg-destructive/10 px-2 py-0.5 font-mono font-medium text-destructive">
            {current.rule}
          </span>
          <span className="min-w-0 font-mono text-muted-foreground [overflow-wrap:anywhere]">
            {current.path}
          </span>
        </p>
        <p className="mt-1.5 font-mono text-foreground/80 [overflow-wrap:anywhere]">
          {current.message}
        </p>
        <p className="mt-1.5 text-muted-foreground">{current.gate}</p>
      </div>

      <div className="border-t border-diff-add/30 bg-diff-add-bg px-4 py-3 text-xs">
        <p className="font-mono font-medium text-diff-add">Repaired to</p>
        <p className="mt-1 font-medium text-foreground [overflow-wrap:anywhere]">
          {current.sent.text}
        </p>
        <p className="mt-0.5 font-mono text-foreground/70">block: {current.sent.block}</p>
      </div>

      {/* Present and empty from the first render, filled only by a button press: a region has to
          exist before its text changes for the change to be announced, and it must not contain the
          visible report, or every auto-advance would be read out. */}
      <div role="status" className="sr-only">
        {announcement}
      </div>
    </div>
  );
}

