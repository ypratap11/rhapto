/** Rhapto's front door at `/`: a headline, one way in, the three steps, and one proof. Everything
 * else (the tour, the walkthrough, pricing, "what it will not do", developer material) is on
 * `/about` (`About.tsx`), linked from the proof. Server component: keep it free of client hooks. */
import Link from "next/link";
import { Download, FileUp, Search } from "lucide-react";
import { HeroBand } from "@/components/shell/HeroBand";
import { buttonVariants } from "@/components/ui/button";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { accessRequestLink } from "./access";
import { freeLimitLine } from "./copy";
import { TuneProof } from "./TuneProof";

const STEPS = [
  { icon: FileUp, title: "Upload your resume", body: "A Word (.docx) file. Rhapto reads it and suggests the role you are aiming for." },
  { icon: Search, title: "Pick a job", body: "Choose from your best matches, or paste a job you found yourself." },
  { icon: Download, title: "Download your tailored resume", body: "Your own document, rewritten for that job. You read it, and you send it." },
] as const;

export function Landing() {
  const access = accessRequestLink();
  return (
    <>
      <HeroBand tone="peach" height="tall">
        <div className="flex min-w-0 max-w-3xl flex-col gap-3">
          <h1 className="font-heading text-[clamp(2.5rem,2.5vw+1.5rem,4rem)] leading-[0.98] font-medium tracking-tight">
            A resume you can defend in any interview.
          </h1>
          <p className="max-w-2xl text-base text-muted-foreground sm:text-lg">
            Rhapto tailors your own resume to a job and checks every number against what you wrote.
          </p>
          {/* Plain styled links, not the Base UI `Button` primitive: both navigate. */}
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-3">
            {SAME_ORIGIN_DEPLOYMENT ? (
              <>
                <Link href="/start" className={buttonVariants({ size: "lg" })}>
                  Tailor my resume
                </Link>
                <a
                  href={access.href}
                  target={access.external ? "_blank" : undefined}
                  rel={access.external ? "noreferrer" : undefined}
                  className="text-sm text-primary underline underline-offset-4"
                >
                  Request beta access
                </a>
              </>
            ) : (
              <>
                <Link href="/settings" className={buttonVariants({ size: "lg" })}>
                  Get started
                </Link>
                <Link href="/about#how" className="text-sm text-primary underline underline-offset-4">
                  See how it works
                </Link>
              </>
            )}
          </div>
          <p className="max-w-2xl text-sm text-muted-foreground">{freeLimitLine(SAME_ORIGIN_DEPLOYMENT)}</p>
        </div>
      </HeroBand>

      <section aria-labelledby="steps-heading" className="mb-12">
        <h2 id="steps-heading" className="sr-only">
          Three steps
        </h2>
        <ol aria-label="Three steps" className="grid gap-4 md:grid-cols-3">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className="rounded-card border border-border bg-surface p-4 shadow-card">
              <span className="mb-2 flex size-9 items-center justify-center rounded-card bg-band-mint text-foreground">
                <Icon className="size-4.5" aria-hidden />
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
