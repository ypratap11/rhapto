"use client";

/** The homepage's public coach tour: four drawn coach screens with fictional data, so a visitor can
 * see the coach before signing in. Built on the Base UI tabs in components/ui/tabs.tsx (arrow keys,
 * Home/End, wrapping and focusable panels come with it). `keepMounted` renders all four panels in
 * the server HTML, the inactive ones hidden. Everything inside a panel is inert: drawn buttons are
 * aria-hidden spans, so the only interactive elements in the window are the four tabs. Wording the
 * real coach shows comes from lib/coach/copy.ts. No autoplay, no timers. */
import { useId } from "react";
import { MatchChip } from "@/components/coach/MatchChip";
import { buttonVariants } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import * as copy from "@/lib/coach/copy";
import { matchLabel } from "@/lib/coach/labels";
import { cn } from "cn";
import { accessRequestLink } from "./access";
import { TOUR_CHANGES, TOUR_FILE, TOUR_JOBS, TOUR_ROLE, TOUR_TABS } from "./coachTourData";
import { primaryCta } from "./cta";

function Drawn({ children, outline = false, size = "lg" }: { children: React.ReactNode; outline?: boolean; size?: "lg" | "default" }) {
  return (
    <span aria-hidden="true" className={cn(buttonVariants({ variant: outline ? "outline" : "default", size }), "pointer-events-none")}>
      {children}
    </span>
  );
}

function Screen({ title, hint, children }: { title: string; hint?: string; children?: React.ReactNode }) {
  return (
    <div className="space-y-4 rounded-card border border-border bg-surface p-5 text-left shadow-card">
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
  const access = accessRequestLink();
  return (
    <section id="tour" aria-labelledby={headingId} className="mt-6 w-full max-w-3xl scroll-mt-20">
      <h2 id={headingId} className="mb-3 font-heading text-xl font-semibold tracking-tight">
        See the coach, step by step
      </h2>
      <div className="overflow-hidden rounded-t-card border border-border bg-background shadow-card">
        <div aria-hidden="true" className="flex gap-1.5 border-b border-border bg-surface-muted px-3 py-2">
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
          <span className="size-2.5 rounded-full bg-border" />
        </div>
        <Tabs defaultValue="upload" className="gap-3 p-3 sm:p-4">
          <TabsList
            variant="line"
            activateOnFocus
            loopFocus
            className="w-full flex-wrap justify-start gap-1 group-data-horizontal/tabs:h-auto"
          >
            {TOUR_TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value} className="h-auto flex-none px-3 py-1.5">
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>

          <TabsContent value="upload" keepMounted>
            <Screen title={copy.UPLOAD_TITLE} hint={copy.UPLOAD_HINT}>
              <p className="inline-flex items-center rounded-full border border-border bg-surface-muted px-3 py-1 text-sm">{TOUR_FILE}</p>
            </Screen>
          </TabsContent>

          <TabsContent value="role" keepMounted>
            <Screen title={copy.roleQuestion(TOUR_ROLE)}>
              <div className="flex flex-wrap gap-3">
                <Drawn>{copy.ROLE_YES}</Drawn>
                <Drawn outline>{copy.ROLE_OTHER}</Drawn>
              </div>
            </Screen>
          </TabsContent>

          <TabsContent value="matches" keepMounted>
            <Screen title={copy.matchesTitle(TOUR_ROLE)}>
              <ul className="space-y-3">
                {TOUR_JOBS.map((job) => (
                  <li key={job.company} className="flex flex-wrap items-center justify-between gap-3 rounded-card border border-border bg-background p-4">
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

          <TabsContent value="result" keepMounted>
            <Screen title={copy.RESULT_TITLE}>
              <p className="text-sm text-muted-foreground">{copy.RESULT_READY}</p>
              <div className="flex flex-wrap gap-3">
                <Drawn>{copy.DOWNLOAD_DOCX}</Drawn>
                <Drawn outline>{copy.DOWNLOAD_PDF}</Drawn>
              </div>
              <div className="space-y-2">
                <p className="text-base font-medium">{copy.WHAT_CHANGED}</p>
                <ul className="space-y-3">
                  {TOUR_CHANGES.map((c) => (
                    <li key={c.reason} className="text-sm">
                      <p className="font-medium">{c.reason}</p>
                      <p className="text-muted-foreground">{c.after}</p>
                    </li>
                  ))}
                </ul>
              </div>
            </Screen>
          </TabsContent>
        </Tabs>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <p className="text-muted-foreground">Example with a fictional person, Maya Chen.</p>
        <a href={cta.href} className="font-medium text-link-on-band underline underline-offset-4">
          Try it with your resume →
        </a>
        {hosted ? (
          <p className="text-muted-foreground">
            No invite yet?{" "}
            <a
              href={access.href}
              target={access.external ? "_blank" : undefined}
              rel={access.external ? "noreferrer" : undefined}
              className="text-link-on-band underline underline-offset-4"
            >
              Request beta access
            </a>
          </p>
        ) : null}
      </div>
    </section>
  );
}
