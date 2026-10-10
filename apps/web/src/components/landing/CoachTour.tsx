"use client";

/** The homepage's public coach tour: four drawn coach screens with fictional data, so a visitor can
 * see the coach before signing in. Built on the Base UI tabs in components/ui/tabs.tsx (arrow keys,
 * Home/End, wrapping and focusable panels come with it). `keepMounted` renders all four panels in
 * the server HTML, the inactive ones hidden. Everything inside a panel is inert: drawn buttons are
 * aria-hidden spans, so the only interactive elements in the window are the four tabs. Wording the
 * real coach shows comes from lib/coach/copy.ts. Self-playing (useTourAutoplay): 4 s per slide, held while the pointer or focus is in the stage or the tour is off-screen, off for good once the visitor picks a tab, off under prefers-reduced-motion. It never moves focus, never scrolls the page and has no live region. */
import { Pause, Play } from "lucide-react";
import { useEffect, useId } from "react";
import { MatchChip } from "@/components/coach/MatchChip";
import { buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import * as copy from "@/lib/coach/copy";
import { matchLabel } from "@/lib/coach/labels";
import { cn } from "cn";
import { TOUR_CHANGES, TOUR_FILE, TOUR_JOBS, TOUR_ROLE, TOUR_TABS } from "./coachTourData";
import { primaryCta } from "./cta";
import { TOUR_INTERVAL_MS, useTourAutoplay } from "./useTourAutoplay";

/** Base UI makes the active panel tabbable; the shared TabsContent sets outline-none, so draw the ring here. */
const PANEL_FOCUS = "rounded-card focus-visible:ring-3 focus-visible:ring-ring/50";

const TOUR_VALUES = TOUR_TABS.map((t) => t.value);
type TourTab = (typeof TOUR_TABS)[number]["value"];
// All four panels share ONE grid cell, so the wrapper is as tall as the tallest panel at every width and nothing
// below the tour moves when the tab changes. Base UI marks an inactive keepMounted panel `hidden`
// (display: none), which would drop it from the grid, so each panel overrides hidden={false} and is hidden with
// `invisible` (data-hidden) instead; Base UI still sets inert on it, and aria-hidden is added for good measure.
const PANEL = cn(PANEL_FOCUS, "tour-panel flex flex-col [grid-area:1/1] data-[hidden]:invisible");

function Drawn({ children, outline = false, size = "lg" }: { children: React.ReactNode; outline?: boolean; size?: "lg" | "default" }) {
  return (
    <span aria-hidden="true" className={cn(buttonVariants({ variant: outline ? "outline" : "default", size }), "pointer-events-none")}>
      {children}
    </span>
  );
}

function Screen({ title, hint, children }: { title: string; hint?: string; children?: React.ReactNode }) {
  return (
    <div className="flex-1 space-y-4 rounded-card border border-border bg-surface p-5 text-left shadow-card">
      <p className="font-heading text-xl font-medium">{title}</p>
      {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
      {children}
    </div>
  );
}

export function CoachTour() {
  const headingId = useId();
  const hosted = SAME_ORIGIN_DEPLOYMENT;
  const cta = primaryCta(hosted);
  const { value, select, playing, running, reduced, toggle, takeOver, sectionRef, stageProps } = useTourAutoplay<TourTab>(TOUR_VALUES);

  // Phones show the tabs on one scrollable row. Keep the active tab in view by moving the tablist's own
  // scrollLeft. Never scrollIntoView: it scrolls every ancestor, the page included, and autoplay would
  // yank a visitor who is reading the hero or the steps every 4 s.
  useEffect(() => {
    const list = sectionRef.current?.querySelector<HTMLElement>('[role="tablist"]');
    const tab = list?.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
    if (!list || !tab) return;
    list.scrollLeft = tab.offsetLeft - (list.clientWidth - tab.offsetWidth) / 2;
  }, [value, sectionRef]);
  return (
    <section ref={sectionRef} id="tour" aria-labelledby={headingId} className="mx-auto mt-8 w-full max-w-5xl scroll-mt-20">
      <h2 id={headingId} className="mb-4 text-center font-heading text-xl font-semibold tracking-tight">
        See the coach, step by step
      </h2>
      <div className="overflow-hidden rounded-card border border-border bg-background shadow-card">
        <div className="flex items-center gap-3 border-b border-border bg-surface-muted px-3 py-2">
          <div aria-hidden="true" className="flex gap-1.5">
            <span className="size-2.5 rounded-full bg-border" />
            <span className="size-2.5 rounded-full bg-border" />
            <span className="size-2.5 rounded-full bg-border" />
          </div>
          <span className="rounded-full border border-border bg-background px-2 py-0.5 text-xs font-medium text-muted-foreground">Live demo</span>
          <button
            type="button"
            aria-label={playing ? "Pause demo" : "Play demo"}
            onClick={toggle}
            className="ml-auto inline-flex size-7 items-center justify-center rounded-control text-muted-foreground hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 max-md:size-11"
          >
            {playing ? <Pause className="size-4" aria-hidden="true" /> : <Play className="size-4" aria-hidden="true" />}
          </button>
        </div>
        {/* The hold zone: hover or focus anywhere in the tabs and panels pauses autoplay. The bar above is
            deliberately outside it, so pressing Play is never undone by the pointer or focus still being there. */}
        <Tabs data-testid="tour-stage" value={value} onValueChange={(v) => select(v as TourTab)} className="gap-3 p-3 sm:p-4" {...stageProps}>
          <TabsList
            variant="line"
            activateOnFocus
            loopFocus
            onClick={(e) => {
              if ((e.target as HTMLElement).closest('[role="tab"]')) takeOver(); // M-4: clicking the active tab also stops autoplay
            }}
            /* relative: the scrollLeft effect reads each tab's offsetLeft, which needs this list as the offsetParent */
            className="relative w-full flex-nowrap justify-start gap-x-1 overflow-x-auto pb-3 sm:justify-center [scrollbar-width:none] [&::-webkit-scrollbar]:hidden group-data-horizontal/tabs:h-auto"
          >
            {TOUR_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value} className="h-auto flex-none px-3 py-1.5 max-md:min-h-11">
                {t.label}
                {running && !reduced && t.value === value ? (
                  <span
                    aria-hidden="true"
                    data-tour-progress=""
                    className="tour-progress pointer-events-none absolute inset-x-0 -bottom-[9px] h-0.5 origin-left bg-primary"
                    style={{ animationDuration: `${TOUR_INTERVAL_MS}ms` }}
                  />
                ) : null}
              </TabsTrigger>
            ))}
          </TabsList>

          {/* Equal-height stack: see PANEL. The wrapper is as tall as the tallest panel, each card stretches to fill it. */}
          <div data-tour-panels="" className="grid">
            <TabsContent value="upload" keepMounted hidden={false} aria-hidden={value !== "upload"} className={PANEL}>
              <Screen title={copy.UPLOAD_TITLE} hint={copy.UPLOAD_HINT}>
                <p className="inline-flex items-center rounded-full border border-border bg-surface-muted px-3 py-1 text-sm">{TOUR_FILE}</p>
              </Screen>
            </TabsContent>

            <TabsContent value="role" keepMounted hidden={false} aria-hidden={value !== "role"} className={PANEL}>
              <Screen title={copy.roleQuestion(TOUR_ROLE)}>
                <div className="flex flex-wrap gap-3">
                  <Drawn>{copy.ROLE_YES}</Drawn>
                  <Drawn outline>{copy.ROLE_OTHER}</Drawn>
                </div>
              </Screen>
            </TabsContent>

            <TabsContent value="matches" keepMounted hidden={false} aria-hidden={value !== "matches"} className={PANEL}>
              <Screen title={copy.matchesTitle(TOUR_ROLE)}>
                <ul className="space-y-3">
                  {TOUR_JOBS.map((job, i) => (
                    <li
                      key={job.company}
                      className="tour-row flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-background p-4"
                      style={{ "--i": i } as React.CSSProperties}
                    >
                      <div className="min-w-0">
                        <p className="font-medium">{job.title}</p>
                        <p className="truncate text-sm text-muted-foreground">{job.company}</p>
                        <p className="mt-1">
                          <MatchChip label={matchLabel(job.fit, job.minFit)} />
                        </p>
                      </div>
                      <Drawn size="default">{copy.TAILOR_THIS}</Drawn>
                    </li>
                  ))}
                </ul>
              </Screen>
            </TabsContent>

            <TabsContent value="result" keepMounted hidden={false} aria-hidden={value !== "result"} className={PANEL}>
              <Screen title={copy.RESULT_TITLE}>
                <p className="text-sm text-muted-foreground">{copy.RESULT_READY}</p>
                <div className="flex flex-wrap gap-3">
                  <Drawn>{copy.DOWNLOAD_DOCX}</Drawn>
                  <Drawn outline>{copy.DOWNLOAD_PDF}</Drawn>
                </div>
                <div className="space-y-2">
                  <p className="text-base font-medium">{copy.WHAT_CHANGED}</p>
                  <ul className="space-y-3">
                    {TOUR_CHANGES.map((c, i) => (
                      <li key={c.reason} className="text-sm">
                        <p className="font-medium">{c.reason}</p>
                        <p className="text-muted-foreground">
                          {/* the changed line: the first change's new text gets the highlight after a short delay */}
                          {i === 0 ? <span className="tour-hl rounded-sm px-0.5 text-foreground">{c.after}</span> : c.after}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              </Screen>
            </TabsContent>
          </div>
        </Tabs>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-sm">
        <p className="text-muted-foreground">Example with a fictional person, Maya Chen.</p>
        <a href={cta.href} className="font-medium text-link-on-band underline underline-offset-4 max-md:inline-flex max-md:min-h-11 max-md:items-center">
          Try it with your resume →
        </a>
      </div>
    </section>
  );
}
