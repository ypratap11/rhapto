"use client";

/** The journey, played rather than listed: asking for access, and then every step that follows, up to
 * the click that is a person's. The owner asked for the animation to start at getting registered and
 * run through the rest, so beat 1 is the request for access and beat 6 is the send.
 *
 * Its own client boundary, for the same reason `ProvenanceDemo` has one: `Landing` renders at `/`
 * inside `TokenGate` and at `/about` as a server component, and must stay free of client hooks.
 *
 * Nothing here is a claim about data: no API call, no `profile/` content, no numbers. The six bodies
 * describe only what `main` does today -- in particular beat 2 does not say a .docx becomes blocks by
 * itself, because that is the unmerged `resume-import` branch, not this one.
 *
 * Motion is CSS transitions on classes and one inline `scaleY`; no keyframes, no animation library,
 * no new dependency. */

import { useCallback, useEffect, useId, useRef, useState } from "react";
import {
  Compass,
  FileText,
  FileUp,
  KeyRound,
  MousePointerClick,
  Radar,
  RotateCcw,
} from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "cn";

const BEATS = [
  {
    icon: KeyRound,
    title: "You ask for access",
    // True for both deployments, like step 1 of the cards: the hosted instance is invite-only, and a
    // self-hoster has nobody to ask. Saying only the first half would read as a gate to the audience
    // that does not have one.
    body: "The hosted instance is invite-only, so the way in is to ask. Your address goes on the allowlist and signing in is a one-time code. Running your own copy, you are already in.",
  },
  {
    icon: FileUp,
    // Deliberately the same promise the "Bring your resume" card makes, no more: Rhapto tailors the
    // .docx you upload in place, or composes from blocks you wrote. Automatic resume-to-blocks
    // extraction is the `resume-import` branch and is not on `main`, so this beat must not show a
    // document turning itself into a block library.
    title: "You bring your resume",
    body: "Upload a .docx and Rhapto edits that document in place, keeping your own wording. Or write a library of blocks — roles, projects, achievements — for it to compose from.",
  },
  {
    icon: Compass,
    title: "You pick a track",
    body: "A field and a role. That is the target every posting gets measured against, with keywords and a fit threshold you set.",
  },
  {
    icon: Radar,
    title: "Jobs arrive and get scored",
    body: "Search when you feel like it, or let Rhapto poll company boards in the background and score everything it finds against that track.",
  },
  {
    icon: FileText,
    title: "Rhapto tailors one",
    body: "One click drafts a resume and a cover note for a single posting. The guardrails run first: a bullet it cannot trace, or a number you have not verified, never reaches the file.",
  },
  {
    icon: MousePointerClick,
    // The product's first non-negotiable rule, and the reason the walkthrough ends here rather than on
    // a finished document: the last thing a reader sees is who does the sending.
    title: "You review and send it",
    body: "Rhapto hands you the file and opens the employer's own page. The last click is a person's — nothing in it sends an application for you, and nothing ever will.",
  },
] as const;

const LAST = BEATS.length - 1;

/** How long each beat holds before the next one arrives. Slow enough to read the title, short enough
 * that the whole journey is over in about five seconds and the page can be read again. */
const BEAT_MS = 950;

/** Read at play time rather than subscribed to: this decides how one run behaves, and a reader who
 * changes the OS setting mid-run can press Replay. Guarded because `matchMedia` is absent in some
 * test environments, and the safe answer there is "motion allowed, then the tests that care stub it". */
function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

export function JourneyWalkthrough() {
  /** Index of the furthest beat arrived at; -1 before the run starts. Every beat's text is in the DOM
   * and legible at every value of this -- an un-arrived beat differs only in its badge and title
   * colour, never in opacity. That keeps the pre-play state honest for a reader with JavaScript off
   * or a crawler, and means no invisible button can ever be tabbed to or clicked. */
  const [current, setCurrent] = useState(-1);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const headingId = useId();

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const play = useCallback(() => {
    stop();
    // Under `prefers-reduced-motion: reduce` there is no run at all: the journey simply is in its
    // final state, and Replay is the control that puts it back there after stepping.
    if (prefersReducedMotion()) {
      setCurrent(LAST);
      return;
    }
    setCurrent(0);
    let i = 0;
    timerRef.current = setInterval(() => {
      i += 1;
      setCurrent(i);
      if (i >= LAST) stop();
    }, BEAT_MS);
  }, [stop]);

  const step = useCallback(
    (i: number) => {
      // A reader who reaches for a beat has taken over; an autoplay still in flight would otherwise
      // overwrite their choice a moment later.
      stop();
      setCurrent(i);
    },
    [stop],
  );

  // Plays once, when it has been scrolled to -- not on mount, so the run is not already over by the
  // time the reader arrives, and not on a loop, because a looping animation beside prose is a
  // distraction. Without an `IntersectionObserver` there is no way to know when the reader arrives, so
  // the fallback is the same as the reduced-motion one: show the finished journey rather than animate
  // it at a moment nobody is looking, and never withhold it. Deps are stable callbacks, so this arms
  // exactly once.
  useEffect(() => {
    const node = rootRef.current;
    if (!node || typeof IntersectionObserver === "undefined") {
      setCurrent(LAST);
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          play();
        }
      },
      // Deliberately threshold 0 with a bottom margin, NOT a fractional threshold. The ratio
      // `IntersectionObserver` reports is intersection area over the TARGET's area, so an element
      // taller than the viewport can never reach a high one: at 360px this list is about 2500px tall
      // against a ~900px viewport, and a 0.35 threshold never fired at all -- the journey sat unplayed
      // on exactly the device the brief says this link gets opened on, including for reduced-motion
      // readers, who then never reached the final state either. Caught in a real browser; jsdom has no
      // IntersectionObserver, so no unit test here can see it. The -15% bottom margin means "its top
      // edge has come up past the last sixth of the screen", which behaves the same at any height.
      { rootMargin: "0px 0px -15% 0px" },
    );
    observer.observe(node);
    return () => {
      observer.disconnect();
      stop();
    };
  }, [play, stop]);

  return (
    <div ref={rootRef} className="w-full">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <h3 id={headingId} className="font-heading text-lg font-medium">
          From asking for access to pressing send
        </h3>
        {/* A real button with a visible label, so the run can be seen again without reloading the
            page. `type="button"` because this sits inside no form but Landing is embedded in pages
            that have them. */}
        <button
          type="button"
          onClick={play}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          <RotateCcw aria-hidden />
          Replay
        </button>
      </div>

      {/* One column at every width. Six beats side by side would not survive 360px, and a horizontal
          timeline that collapses into a scroller hides the last beats -- which here is the one that
          matters most. A vertical rail reads the same on a phone and on a desktop. */}
      <ol aria-labelledby={headingId} className="mt-4">
        {BEATS.map(({ icon: Icon, title, body }, i) => {
          const arrived = i <= current;
          const isCurrent = i === current;
          return (
            // `data-beat` is this beat's own state, written once and read by both the styling below
            // and the tests. Asserting on a Tailwind class instead would let a restyle silently stop
            // proving anything, which has already happened once on this page.
            <li key={title} data-beat={arrived ? "arrived" : "pending"} className="flex gap-3 sm:gap-4">
              <div className="flex flex-col items-center" aria-hidden>
                <span
                  className={cn(
                    "flex size-9 shrink-0 items-center justify-center rounded-full border transition-[background-color,border-color,color,transform,box-shadow] duration-500 ease-out",
                    arrived
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-surface text-muted-foreground",
                    isCurrent && "scale-110 ring-4 ring-primary/20",
                  )}
                >
                  <Icon className="size-4.5" />
                </span>
                {i < LAST ? (
                  // The rail between this beat and the next, growing from the top as the journey
                  // moves on. `flex-1` makes it span whatever height the body text needs.
                  <span className="relative mt-1 w-px flex-1 bg-border">
                    <span
                      className="absolute inset-0 origin-top bg-primary transition-transform duration-500 ease-out"
                      style={{ transform: `scaleY(${i < current ? 1 : 0})` }}
                    />
                  </span>
                ) : null}
              </div>
              {/* The whole row is the control: a real button, so it is tappable at phone width,
                  reachable by Tab and operable with Enter or Space with no extra wiring.
                  `aria-current="step"` is how the current beat reaches a screen reader -- not a live
                  region, which during a six-beat autoplay would talk over whatever else is being
                  read and would announce beats the reader did not ask for. */}
              <button
                type="button"
                aria-current={isCurrent ? "step" : undefined}
                onClick={() => step(i)}
                className={cn(
                  "-mx-2 flex-1 rounded-control px-2 py-1.5 text-left transition-colors duration-500 ease-out hover:bg-surface/70",
                  i < LAST && "mb-3",
                )}
              >
                <span
                  className={cn(
                    "block font-medium transition-colors duration-500 ease-out",
                    arrived ? "text-foreground" : "text-muted-foreground",
                  )}
                >
                  {title}
                </span>
                <span className="mt-1 block text-sm text-muted-foreground">{body}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
