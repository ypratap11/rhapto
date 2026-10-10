/** Rhapto's front door at `/`: a hero with the coach tour inside the band, the three steps, one proof and a
 * closing call to action. Server component: keep it free of client hooks; `CoachTour` carries its own
 * client boundary. */
import Link from "next/link";
import { HeroBand } from "@/components/shell/HeroBand";
import { buttonVariants } from "@/components/ui/button";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { cn } from "cn";
import { accessRequestLink, REQUEST_LINK_CLASS } from "./access";
import { CoachTour } from "./CoachTour";
import { freeLimitLine } from "./copy";
import { primaryCta } from "./cta";
import { RevealOnScroll } from "./RevealOnScroll";
import { TuneProof } from "./TuneProof";

const STEPS = [
  { title: "Upload your resume", body: "A Word (.docx) file. Rhapto reads it and suggests the role you are aiming for.", circle: "bg-step-1 text-step-1-fg" },
  { title: "Pick a job", body: "Choose from your best matches, or paste a job you found yourself.", circle: "bg-step-2 text-step-2-fg" },
  { title: "Download your tailored resume", body: "Your own document, rewritten for that job. You read it, and you send it.", circle: "bg-step-3 text-step-3-fg" },
] as const;

export function Landing() {
  const access = accessRequestLink();
  const cta = primaryCta(SAME_ORIGIN_DEPLOYMENT);
  const ctaClass = cn(buttonVariants({ size: "lg" }), "shadow-cta cta-lift max-md:h-11");
  const requestLine = SAME_ORIGIN_DEPLOYMENT ? (
    <p className="text-sm text-muted-foreground">
      No invite yet?{" "}
      <a
        href={access.href}
        target={access.external ? "_blank" : undefined}
        rel={access.external ? "noreferrer" : undefined}
        className={REQUEST_LINK_CLASS}
      >
        Request beta access
      </a>
    </p>
  ) : null;
  return (
    <>
      <RevealOnScroll />
      <HeroBand tone="glow" height="tall">
        <div className="flex min-w-0 max-w-3xl flex-col items-center gap-3">
          <h1 className="font-heading text-[clamp(2.5rem,2.5vw+1.5rem,4rem)] leading-[0.98] font-semibold tracking-tight">
            A resume you can <span className="highlight-underline">defend</span> in any interview.
          </h1>
          <p className="max-w-2xl text-base text-muted-foreground sm:text-lg">
            Upload your resume, pick a job, and get your own document rewritten for it.
          </p>
          {/* A plain styled link, not the Base UI `Button` primitive: it navigates. */}
          <div className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-3">
            <Link href={cta.href} prefetch={false} className={ctaClass}>
              {cta.label} <span aria-hidden="true">→</span>
            </Link>
          </div>
          {requestLine}
          <p className="text-sm text-muted-foreground">Open source · You always submit · Every number checked</p>
          <p className="max-w-2xl text-sm text-muted-foreground">{freeLimitLine(SAME_ORIGIN_DEPLOYMENT)}</p>
        </div>
        <CoachTour />
      </HeroBand>

      <section aria-labelledby="steps-heading" className="reveal mx-auto mb-16 w-full max-w-5xl sm:mb-20">
        <h2 id="steps-heading" className="mb-6 text-center font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
          Three steps to a resume you can defend
        </h2>
        <ol aria-label="Three steps" className="grid gap-4 md:grid-cols-3">
          {STEPS.map(({ title, body, circle }, i) => (
            <li key={title} className="flex flex-col items-center rounded-card border border-border bg-surface p-4 text-center shadow-card">
              <span aria-hidden="true" className={cn("mb-2 flex size-9 items-center justify-center rounded-full text-sm font-semibold", circle)}>
                {i + 1}
              </span>
              <p className="text-base font-semibold">
                {/* The circle stays aria-hidden and the prefix is sr-only so the position is announced once. */}
                <span className="sr-only">{i + 1}. </span>
                {title}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="proof-heading" className="reveal mx-auto mb-16 w-full max-w-5xl sm:mb-20">
        <h2 id="proof-heading" className="sr-only">
          What the check catches
        </h2>
        <TuneProof />
      </section>

      {/* Visitors who scroll to the end always have a next step. No numbers, logos or promises. mb-8 +
          main's pb-8 gives the same gap before the footer as between the sections above. */}
      <section
        aria-labelledby="closing-heading"
        className="reveal mx-auto mb-8 flex w-full max-w-5xl flex-col items-center gap-3 rounded-card bg-band-peach px-6 py-10 text-center text-foreground sm:mb-12"
      >
        <h2 id="closing-heading" className="font-heading text-2xl font-semibold tracking-tight sm:text-3xl">
          Try it on your own resume
        </h2>
        <p className="max-w-xl text-base text-muted-foreground">Upload a Word file, pick a job, and read the result before you send anything.</p>
        <Link href={cta.href} prefetch={false} className={cn(ctaClass, "mt-2")}>
          {cta.label} <span aria-hidden="true">→</span>
        </Link>
        {requestLine}
      </section>
    </>
  );
}
