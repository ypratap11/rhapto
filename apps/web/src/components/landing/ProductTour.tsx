"use client";

/** The landing page's click-through product tour: 14 real screenshots of one captured run, a pulsing
 * hotspot on the thing to look at, a caption card, and a five-chapter rail.
 *
 * What is and is not true, because this is the section that shows the product:
 *  - Everything shown is ONE run, captured 29 September 2026, on a fictional profile (Maya Chen)
 *    against real jobs. The copy in `tourSteps.ts` states facts of that run, never guarantees, and the
 *    intro says so in visible text.
 *  - The outro's numbers are labelled as coming from this run. The call to action is the hero's own
 *    logic: same-origin (hosted, invite-only) deployments get "Request access", everyone else
 *    "Get started".
 *
 * Own client boundary: `Landing` is a server component at `/` and `/about` and must stay hook-free.
 *
 * Rendering contract (SSR-safe): the first render is the intro, a constant. `matchMedia` is read only
 * through `useSyncExternalStore` with a constant server snapshot. All geometry is percentages precomputed in `tourSteps.ts`, so there is no
 * measuring (no ResizeObserver, no getBoundingClientRect) and the phone layout is a CSS breakpoint,
 * never a JS width check. The intro renders no `<img>`: it covers the stage, so the first screenshot
 * downloads when the visitor starts, and the next two are warmed then. */

import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import type { KeyboardEvent } from "react";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { cn } from "cn";
import { accessRequestLink } from "./access";
import { prefersReducedMotion } from "./JourneyWalkthrough";
import { CHAPTERS, CHAPTER_FIRST_STEP, STEPS, STEPS_STILL, TOUR_H, TOUR_W } from "./tourSteps";
import type { Seg } from "./tourSteps";

const HOST = "rhapto.augaster.com";

const focusRing =
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring";

const primaryBtn = cn(
  "inline-flex items-center justify-center rounded-control bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90",
  focusRing,
);
const quietBtn = cn(
  "inline-flex items-center justify-center rounded-control border border-border bg-transparent px-3 py-1.5 text-sm text-foreground transition-colors hover:bg-muted disabled:opacity-50",
  focusRing,
);

function Caption({ body }: { body: readonly Seg[] }) {
  return (
    <p className="mb-3 text-sm text-muted-foreground">
      {body.map((s, i) =>
        s.bold ? (
          <strong key={i} className="font-semibold text-foreground">
            {s.text}
          </strong>
        ) : (
          <span key={i}>{s.text}</span>
        ),
      )}
    </p>
  );
}

/** The server snapshot is `false`, so the first render (server and hydration) is the same constant
 * whatever the visitor's setting; the real value is read on the client right after hydration. The
 * `matchMedia` guard mirrors `prefersReducedMotion`'s, for environments that do not implement it. */
function subscribeReducedMotion(onChange: () => void) {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  const query = window.matchMedia("(prefers-reduced-motion: reduce)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

export function ProductTour() {
  const labelId = useId();
  const access = accessRequestLink();
  // -1 is the intro, STEPS.length is the outro.
  const [index, setIndex] = useState(-1);
  const reduced = useSyncExternalStore(subscribeReducedMotion, prefersReducedMotion, () => false);

  const startRef = useRef<HTMLButtonElement>(null);
  const captionRef = useRef<HTMLHeadingElement>(null);
  const outroRef = useRef<HTMLHeadingElement>(null);
  const previous = useRef(-1);

  // Focus follows the move between the three states, and only that: within the steps the hotspot,
  // Next and Back keep the focus the visitor gave them (they are never remounted).
  useEffect(() => {
    const was = previous.current;
    previous.current = index;
    if (was === index) return;
    if (index === STEPS.length) outroRef.current?.focus();
    else if (index === -1) startRef.current?.focus();
    else if (was === -1 || was === STEPS.length) captionRef.current?.focus();
  }, [index]);

  // Warm the next two screenshots. Never all fourteen on mount.
  useEffect(() => {
    if (index < 0) return;
    for (const s of STEPS.slice(index + 1, index + 3)) {
      const warm = new Image();
      warm.src = `/tour/${s.img}.webp`;
    }
  }, [index]);

  const go = (n: number) => setIndex(Math.max(-1, Math.min(STEPS.length, n)));

  const onKeyDown = (e: KeyboardEvent<HTMLElement>) => {
    if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey || e.shiftKey) return;
    const to = e.key === "ArrowRight" ? index + 1 : e.key === "ArrowLeft" ? index - 1 : null;
    if (to === null || to < -1 || to > STEPS.length || index === to) return;
    // From the intro, ArrowLeft has nowhere to go; from the outro, ArrowRight likewise.
    if ((index === -1 && to < index) || (index === STEPS.length && to > index)) return;
    e.preventDefault();
    go(to);
  };

  const steps = reduced ? STEPS_STILL : STEPS;
  const inStep = index >= 0 && index < STEPS.length;
  const step = inStep ? steps[index]! : null;
  const nextStep = inStep && index < STEPS.length - 1 ? STEPS[index + 1]! : null;
  const chapter = inStep ? step!.c : index < 0 ? -1 : CHAPTERS.length;

  return (
    <section
      role="region"
      aria-labelledby={labelId}
      onKeyDown={onKeyDown}
      className="w-full text-foreground"
    >
      <h2 id={labelId} className="sr-only">
        Product tour
      </h2>

      <nav aria-label="Tour chapters" className="mb-4 grid grid-cols-5 items-start gap-1.5">
        {CHAPTERS.map((name, k) => {
          const inChapter = STEPS.map((s, j) => (s.c === k ? j : -1)).filter((j) => j >= 0);
          const done =
            index >= STEPS.length ? 1
            : index < 0 ? 0
            : k < chapter ? 1
            : k > chapter ? 0
            : (inChapter.indexOf(index) + 1) / inChapter.length;
          return (
            <button
              key={name}
              type="button"
              aria-current={k === chapter ? "step" : undefined}
              onClick={() => go(CHAPTER_FIRST_STEP[k]!)}
              className={cn(
                "flex min-w-0 flex-col gap-1.5 rounded-chip pb-0.5 text-left text-muted-foreground",
                focusRing,
                k === chapter && "text-foreground",
              )}
            >
              <span className="block h-1 w-full overflow-hidden rounded-full bg-border">
                <i
                  className="block h-full bg-primary not-italic motion-safe:transition-[width] motion-safe:duration-300"
                  style={{ width: `${done * 100}%` }}
                />
              </span>
              <span className="block truncate text-[0.7rem] leading-tight font-semibold sm:text-xs md:text-[0.8rem]">
                {k + 1}. {name}
              </span>
            </button>
          );
        })}
      </nav>

      <div className="overflow-hidden rounded-card border border-border bg-card shadow-card">
        <div aria-hidden="true" className="flex items-center gap-2.5 border-b border-border bg-muted px-3.5 py-2">
          <span className="flex gap-1.5">
            <i className="size-2.5 rounded-full bg-border" />
            <i className="size-2.5 rounded-full bg-border" />
            <i className="size-2.5 rounded-full bg-border" />
          </span>
          <span className="min-w-0 flex-1 truncate rounded-chip bg-card px-2.5 py-1 font-mono text-xs text-muted-foreground">
            {HOST}
            {step ? step.url : ""}
          </span>
        </div>

        <div className="relative">
          <div
            className={cn(
              "relative overflow-hidden bg-background",
              inStep ? "aspect-[1443/758]" : "xl:aspect-[1443/758]",
            )}
          >
            {step ? (
              <>
                <div
                  className="absolute inset-0 origin-top-left motion-safe:transition-transform motion-safe:duration-700 motion-safe:ease-out"
                  style={
                    reduced ? undefined : { transform: `translate(${step.tx}%, ${step.ty}%) scale(${step.zoom})` }
                  }
                >
                  {/* Plain <img>, on purpose: this app ships without the image optimizer (no sharp,
                      no `images` config), and these are already-encoded WebP files. */}
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={`/tour/${step.img}.webp`}
                    alt={step.title}
                    width={TOUR_W}
                    height={TOUR_H}
                    className="block h-full w-full object-cover"
                  />
                </div>
                <button
                  type="button"
                  aria-label={nextStep ? `Next: ${nextStep.title}` : "Finish: see the summary"}
                  onClick={() => go(index + 1)}
                  className={cn(
                    "absolute size-[34px] -translate-x-1/2 -translate-y-1/2 rounded-full p-0 md:size-[46px]",
                    focusRing,
                  )}
                  style={{ left: `${step.hx}%`, top: `${step.hy}%` }}
                >
                  <span
                    aria-hidden="true"
                    className="absolute inset-0 scale-[0.42] rounded-full bg-primary shadow-[0_0_0_4px_var(--card)]"
                  />
                  <span
                    aria-hidden="true"
                    className="absolute inset-0 scale-110 rounded-full border-[3px] border-primary opacity-60 motion-safe:animate-ping motion-safe:opacity-100"
                  />
                </button>
              </>
            ) : null}

            {index === -1 ? (
              <div className="grid min-h-80 place-items-center bg-band-peach p-6 text-center xl:absolute xl:inset-0 xl:min-h-0">
                <div className="mx-auto max-w-2xl">
                  <p className="mb-3 text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
                    Product tour, about 2 minutes
                  </p>
                  <h2 className="mb-3 font-heading text-[clamp(1.7rem,3.4vw,3rem)] leading-[1.05] font-medium tracking-tight text-balance">
                    See a real run, start to finish
                  </h2>
                  <p className="mx-auto mb-5 max-w-[52ch] text-[clamp(0.95rem,1.2vw,1.1rem)] text-muted-foreground">
                    Follow Maya, a data program manager, from her career record to a tailored application,
                    and see how Rhapto keeps every line tied to something she actually wrote.
                  </p>
                  <button ref={startRef} type="button" onClick={() => go(0)} className={primaryBtn}>
                    Start the tour
                  </button>
                  <p className="mx-auto mt-5 max-w-[52ch] text-sm text-muted-foreground">
                    Maya Chen is a fictional demo person. Everything else is real: live jobs, a real AI
                    tailoring run and the real app, captured 29 September 2026.
                  </p>
                </div>
              </div>
            ) : null}

            {index === STEPS.length ? (
              <div className="grid min-h-80 place-items-center bg-band-peach p-6 text-center xl:absolute xl:inset-0 xl:min-h-0">
                <div className="mx-auto max-w-2xl">
                  <h2
                    ref={outroRef}
                    tabIndex={-1}
                    className="mb-3 font-heading text-[clamp(1.7rem,3.4vw,3rem)] leading-[1.05] font-medium tracking-tight text-balance outline-none"
                  >
                    One real job, one honest resume.
                  </h2>
                  <dl className="mb-1 flex flex-wrap justify-center gap-x-7 gap-y-3">
                    {[
                      ["28", "live jobs in her first search"],
                      ["13¢", "AI cost for this resume"],
                      ["6 of 6", "checks passed"],
                      ["0", "unverified numbers"],
                    ].map(([n, label]) => (
                      <div key={label}>
                        <dt className="font-heading text-3xl leading-none font-medium">{n}</dt>
                        <dd className="text-xs text-muted-foreground">{label}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="mb-4 text-xs text-muted-foreground">From the run in this tour.</p>
                  <p className="mx-auto mb-5 max-w-[52ch] text-[clamp(0.95rem,1.2vw,1.1rem)] text-muted-foreground">
                    Rhapto finds the roles, tailors from your own record, checks every line, and leaves the
                    submit button to you.
                    {SAME_ORIGIN_DEPLOYMENT ? " Access is invite-only." : ""}
                  </p>
                  <div className="flex flex-wrap items-center justify-center gap-3">
                    {SAME_ORIGIN_DEPLOYMENT ? (
                      <a
                        href={access.href}
                        target={access.external ? "_blank" : undefined}
                        rel={access.external ? "noreferrer" : undefined}
                        className={primaryBtn}
                      >
                        Request beta access
                      </a>
                    ) : (
                      <a href="/settings" className={primaryBtn}>
                        Get started
                      </a>
                    )}
                    <button type="button" onClick={() => go(0)} className={quietBtn}>
                      Watch again
                    </button>
                  </div>
                </div>
              </div>
            ) : null}
          </div>

          {step ? (
            <div
              className="border-t border-border bg-card p-4 text-card-foreground xl:absolute xl:w-[min(340px,42%)] xl:rounded-card xl:border xl:px-[18px] xl:pt-4 xl:pb-3.5 xl:shadow-card"
              style={{ left: `${step.at[0] * 100}%`, top: `${step.at[1] * 100}%` }}
            >
              <div aria-live="polite">
                <p className="font-mono text-xs text-primary">
                  {index + 1} of {STEPS.length} · {CHAPTERS[step.c]}
                </p>
                <h3
                  ref={captionRef}
                  tabIndex={-1}
                  className="mt-1 mb-1.5 font-heading text-xl leading-tight font-medium text-balance outline-none"
                >
                  {step.title}
                </h3>
                <Caption body={step.body} />
              </div>
              <div className="flex items-center justify-between gap-2">
                <button type="button" onClick={() => go(index - 1)} className={quietBtn}>
                  Back
                </button>
                <button type="button" onClick={() => go(index + 1)} className={cn(primaryBtn, "px-3.5 py-2")}>
                  {index === STEPS.length - 1 ? "Finish" : "Next"}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>

      <p className="mt-3 text-center text-xs text-muted-foreground">
        Click the pulsing dot or press &rarr; to continue. &larr; goes back.
      </p>
    </section>
  );
}
