/** Rhapto's front door at `/`: a hero with the coach tour inside the band, the three steps, and one
 * proof. The coach tour (`CoachTour`) is on this page; the older 12-step click-through tour stays on
 * `/about` (`About.tsx`), linked from the proof. Server component: keep it free of client hooks;
 * `CoachTour` carries its own client boundary. */
import Link from "next/link";
import { HeroBand } from "@/components/shell/HeroBand";
import { buttonVariants } from "@/components/ui/button";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { cn } from "cn";
import { accessRequestLink } from "./access";
import { CoachTour } from "./CoachTour";
import { freeLimitLine } from "./copy";
import { primaryCta } from "./cta";
import { TuneProof } from "./TuneProof";

const STEPS = [
  { title: "Upload your resume", body: "A Word (.docx) file. Rhapto reads it and suggests the role you are aiming for.", circle: "bg-step-1 text-step-1-fg" },
  { title: "Pick a job", body: "Choose from your best matches, or paste a job you found yourself.", circle: "bg-step-2 text-step-2-fg" },
  { title: "Download your tailored resume", body: "Your own document, rewritten for that job. You read it, and you send it.", circle: "bg-step-3 text-step-3-fg" },
] as const;

export function Landing() {
  const access = accessRequestLink();
  const cta = primaryCta(SAME_ORIGIN_DEPLOYMENT);
  return (
    <>
      <HeroBand tone="glow" height="tall">
        <div className="flex min-w-0 max-w-3xl flex-col gap-3">
          <p className="inline-flex w-fit items-center gap-2 rounded-full border border-border bg-surface px-3 py-1 text-sm font-medium text-foreground">
            <span aria-hidden="true" className="size-2 rounded-full bg-decor-teal" />
            Every number checked against your resume
          </p>
          <h1 className="font-heading text-[clamp(2.5rem,2.5vw+1.5rem,4rem)] leading-[0.98] font-semibold tracking-tight">
            A resume you can <span className="highlight-underline">defend</span> in any interview.
          </h1>
          <p className="max-w-2xl text-base text-muted-foreground sm:text-lg">
            Upload your resume, pick a job, and get your own document rewritten for it.
          </p>
          {/* Plain styled links, not the Base UI `Button` primitive: both navigate. */}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-3">
            <Link href={cta.href} className={cn(buttonVariants({ size: "lg" }), "shadow-cta")}>
              {cta.label} <span aria-hidden="true">→</span>
            </Link>
            <a href="#tour" className="text-sm text-link-on-band underline underline-offset-4">
              See how it works ↓
            </a>
          </div>
          {SAME_ORIGIN_DEPLOYMENT ? (
            <p className="text-sm text-muted-foreground">
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
          <p className="text-sm text-muted-foreground">Open source · You always submit · Your own document</p>
          <p className="max-w-2xl text-sm text-muted-foreground">{freeLimitLine(SAME_ORIGIN_DEPLOYMENT)}</p>
        </div>
        <CoachTour />
      </HeroBand>

      <section aria-labelledby="steps-heading" className="mb-12">
        <h2 id="steps-heading" className="sr-only">
          Three steps
        </h2>
        <ol aria-label="Three steps" className="grid gap-4 md:grid-cols-3">
          {STEPS.map(({ title, body, circle }, i) => (
            <li key={title} className="rounded-card border border-border bg-surface p-4 shadow-card">
              <span aria-hidden="true" className={cn("mb-2 flex size-9 items-center justify-center rounded-full text-sm font-semibold", circle)}>
                {i + 1}
              </span>
              <p className="text-base font-semibold">
                <span className="text-muted-foreground">{i + 1}. </span>
                {title}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="proof-heading" className="mb-12">
        <h2 id="proof-heading" className="sr-only">
          What the check catches
        </h2>
        <TuneProof />
        <p className="mt-4 text-sm">
          <Link href="/about" className="text-primary underline underline-offset-4">
            How it works in detail
          </Link>
        </p>
      </section>
    </>
  );
}
