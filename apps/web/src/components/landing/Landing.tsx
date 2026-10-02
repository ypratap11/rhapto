/** Rhapto's pitch, in the order a stranger needs it: what it does and the one way in, the product
 * tour, why it exists, why it is a promise rather than a chatbot, the six-beat walkthrough, what to
 * know before starting, and then, clearly separated, the developer and self-hosting material
 * (licence, where data lives, per-model costs).
 *
 * Rendered at two mounts, which is why it is a component and not just a page: `/about` (its own
 * URL, linkable, readable by anyone) and `/` (its own page, `apps/web/src/app/page.tsx`, which
 * `TokenGate` renders unconditionally for everyone -- signed in or not -- since "/" is one of its
 * `PUBLIC_ROUTES`). Keep it free of client hooks: it is a server component in both mounts, and
 * `SAME_ORIGIN_DEPLOYMENT` is a build-time constant, not a runtime read, so branching on it below
 * needs no client boundary. */
import Link from "next/link";
import { Ban, BadgeCheck, Coins, Fingerprint, Hand, ListChecks } from "lucide-react";
import { HeroBand } from "@/components/shell/HeroBand";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { ACCESS_REQUEST_EMAIL, accessRequestLink } from "./access";
import { CaughtDemo } from "./CaughtDemo";
import { JourneyWalkthrough } from "./JourneyWalkthrough";
import { ProductTour } from "./ProductTour";


// The three non-negotiable product rules, written for someone who has never seen the repo. They
// are the reason to choose Rhapto over a chat window, so they come before the steps.
const PROMISES = [
  {
    icon: Fingerprint,
    title: "Know where each claim came from",
    body: "Each bullet cites a block from your own library, and a bullet Rhapto cannot trace fails the check and blocks the package. “Where did that come from?” always has an answer.",
  },
  {
    icon: BadgeCheck,
    title: "Use numbers you can support",
    body: "Rhapto is told to write “several teams,” never “fifteen teams,” until you have marked that number verified. If the model writes it anyway, the guardrail catches it and the model gets one try at a fix; if that fails, the whole package is marked blocked.",
  },
  {
    icon: Hand,
    title: "The last click is yours",
    body: "Rhapto opens the employer’s own page and hands you the file. There is no code path in it that submits an application, and there never will be.",
  },
] as const;

export function Landing() {
  // Hosted only in practice (the buttons below render only when SAME_ORIGIN_DEPLOYMENT), computed
  // once so the hero and the footer cannot disagree about where "Request beta access" goes.
  const access = accessRequestLink();
  const accessAttrs = {
    href: access.href,
    target: access.external ? "_blank" : undefined,
    rel: access.external ? "noreferrer" : undefined,
  };
  return (
    <>
      <HeroBand tone="peach" height="tall">
        {/* Two columns at `lg` only (1024): at 768 each column would be ~340px and the headline
            would wrap to five-plus lines. `minmax(0, ...)` on both tracks so a long mono path in
            the demo can never widen its track past the viewport. Below `lg` the demo stacks under
            the copy. */}
        <div className="grid items-center gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)] lg:gap-12">
          <div className="flex min-w-0 flex-col gap-3">
        <p className="text-sm font-medium text-muted-foreground">
          Tailored for each job, with every line checked against your own record.
        </p>
        {/* Plain on purpose: no coloured word. The `clamp` keeps one class readable from a 360px
            phone (2.5rem floor) to the two-column desktop layout, where the ceiling is lower than
            the old full-width 5rem because the copy column is only about half the band. */}
        <h1 className="max-w-4xl font-heading text-[clamp(2.5rem,2.5vw+1.5rem,4rem)] leading-[0.98] font-medium tracking-tight">
          A resume you can defend in any interview.
        </h1>
        {/* What is true inside a run: the model's draft is checked, a caught line gets one repair,
            and only a failed repair blocks the package and shows the rule. Not "you see every
            catch", and no claim about what a blocked package does or does not produce. */}
        <p className="max-w-2xl text-base text-muted-foreground sm:text-lg">
          Rhapto drafts your resume with an AI model and checks the draft before you see it. A
          number you never confirmed, or a line with no source, is sent back for one fix; if that
          fails, the package is blocked and you see which rule fired. Then you read it, and you
          press submit.
        </p>
        {/* Plain styled links, not the Base UI `Button` primitive: both of these navigate, and
            `Button render={<Link/>}` forces a choice between misreporting them as role="button"
            (`nativeButton={false}`) or a dev-mode console error. Same house style, neither cost —
            the pattern JobCard and RepostNotice already settled on. */}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-3">
          {/* Hosted: one filled button, the way in. The tour is a plain text link and sign-in is small
              text, so a stranger sees a single obvious next step and an invited person still finds
              the door. Sign-in is "Sign in" rather than "Open your dashboard" because /dashboard sits
              behind Cloudflare Access, so following this link IS the sign-in flow; there is no /login
              route to point at. Token mode (self-hosted) keeps "Get started" -> /settings, with
              nobody to request access from. */}
          {SAME_ORIGIN_DEPLOYMENT ? (
            <>
              <a {...accessAttrs} className={buttonVariants({ size: "lg" })}>
                Request beta access
              </a>
              <a href="#tour" className="text-sm text-primary underline underline-offset-4">
                Watch the 2-minute tour
              </a>
              <p className="text-sm text-muted-foreground">
                Already invited?{" "}
                <Link href="/dashboard" className="text-primary underline underline-offset-4">
                  Sign in
                </Link>
              </p>
            </>
          ) : (
            <>
              <Link href="/settings" className={buttonVariants({ size: "lg" })}>
                Get started
              </Link>
              <a href="#how" className="text-sm text-primary underline underline-offset-4">
                See how it works
              </a>
            </>
          )}
        </div>
        {SAME_ORIGIN_DEPLOYMENT ? (
          // One line. No response time is promised and no pronoun is used -- the maintainer is unnamed
          // on this page. While the mailto fallback is live the address is spelled out as text, since a
          // visitor with no registered mail handler otherwise gets a button that does nothing.
          <p className="max-w-2xl text-sm text-muted-foreground">
            Private beta: sign-in is invite-only, so request access first.
            {access.external
              ? null
              : ` The button opens an email to ${ACCESS_REQUEST_EMAIL} for you to send.`}
          </p>
        ) : null}
        <p className="max-w-2xl text-sm text-muted-foreground">
          A new account starts empty. You will need a resume to upload (or a few blocks written by
          hand), one track, and your contact details before Rhapto can produce anything.{" "}
          <a href="#honest" className="text-primary underline underline-offset-4">
            What that means
          </a>
        </p>
          </div>
          <CaughtDemo />
        </div>
      </HeroBand>

      {/* Right under the hero, because "watch it work" is the hero's secondary action (`#tour`). The
          anchor lives on this wrapper, not inside `ProductTour`, so the tour stays anchor-agnostic.
          The claim below it (every line traces to a block) is shown by walking the real product end to
          end. The catch itself is the hero's `CaughtDemo`. All interaction lives in `ProductTour`, a
          separate `"use client"` component -- this wrapper stays a plain server-rendered band. The
          tour's own intro heading is this section's h2, and it must not repeat the page's h1, so the
          page keeps exactly one h1 without the headline showing twice in a row. */}
      <section id="tour" className="mb-12 scroll-mt-20">
        <HeroBand tone="sand" height="tall">
          <ProductTour />
        </HeroBand>
      </section>

      {/* The human reason, before any mechanism. Everything below this explains HOW Rhapto works;
          without this, nothing on the page says why it should exist. Deliberately prose in a single
          block rather than the card grids used elsewhere -- it is meant to be read, not scanned.
          "It will not apply for you" is not repeated here: it is said once, in the third card. */}
      <section aria-labelledby="why-this" className="mb-12">
        <div className="rounded-card border-l-4 border-primary bg-surface-muted px-6 py-6 sm:px-8 sm:py-7">
          <h2 id="why-this" className="font-heading text-2xl font-medium">
            Why this exists
          </h2>
          <div className="mt-3 max-w-3xl space-y-3 text-base leading-relaxed text-muted-foreground">
            <p>
              Looking for work is tedious in a way that wears people down. The same job description
              read for the fourth time. The same bullet rewritten to match slightly different words.
              Evenings spent on applications that go nowhere, with no way to tell which ones were
              worth it.
            </p>
            <p>
              Most of that effort is real work — a resume genuinely should match the role it is sent
              to. It just should not cost you an evening every time.
            </p>
            <p>
              Rhapto takes that weight off. It finds the roles worth your time and writes a resume
              that is true to what you have actually done. Every draft is checked for invented
              numbers and lines with no source, and one that fails is marked blocked. What is left is
              the part that needs a person: deciding where to apply, and what to say when someone
              answers.
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="why" className="mb-12">
        <h2 id="why" className="font-heading text-2xl font-medium">
          Why not just ask a chatbot?
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          A chatbot can add details you didn’t confirm. Rhapto checks every draft for numbers you
          haven’t confirmed and lines it can’t trace to your record, gives the model one chance to
          fix them, and marks the package blocked if the fix doesn’t hold.
        </p>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          {PROMISES.map(({ icon: Icon, title, body }) => (
            <Card key={title} className="h-full">
              <CardHeader>
                <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-mint text-foreground">
                  <Icon className="size-4.5" aria-hidden />
                </span>
                <CardTitle className="text-base">{title}</CardTitle>
              </CardHeader>
              <CardContent className="text-sm text-muted-foreground">{body}</CardContent>
            </Card>
          ))}
        </div>
        {/* What the checks do not cover, said next to the promises rather than buried: a line can
            stretch the wording of the block it cites and still pass, so the read-through is real. */}
        <h3 className="mt-6 font-heading text-lg font-medium">
          What Rhapto checks — and what you still review
        </h3>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          What the checks do not catch: a line can stretch the wording of its source without
          adding a number or a title, and a role Rhapto never selected for this resume is not
          flagged as missing. You still read the resume before you send it.
        </p>
      </section>

      {/* The six beats are the only telling of the journey. The residency and cost disclosures that
          used to sit under them now live in the developer section below; the beats stay here because
          they are what a job seeker reads to see how it fits into a week. */}
      <section aria-labelledby="how-heading" className="mb-12 scroll-mt-20" id="how">
        <HeroBand tone="mint" height="tall">
          <h2 id="how-heading" className="font-heading text-2xl font-medium">
            How it works
          </h2>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            Six beats from a cold install to an application you send yourself. The first three you
            do once; the last three repeat, one posting at a time.
          </p>
          <div className="mt-4 max-w-3xl">
            <JourneyWalkthrough />
          </div>
        </HeroBand>
      </section>

      <section aria-labelledby="honest" className="mb-10">
        <h2 id="honest" className="scroll-mt-20 font-heading text-2xl font-medium">
          Before you start
        </h2>
        {/* The privacy line. Every clause was written after a real shipped defect: the first version
            claimed "it runs on your machine -- your resume and your key stay there", false for anyone
            on a hosted instance. What is true: the text sent to draft goes to ONE model provider, and
            on the hosted beta during the free runs that provider is the instance's, not one the visitor
            picked. Token mode has no free runs, so it drops that clause. The full residency wording is
            kept, unchanged, in the developer section. */}
        <p className="mt-3 max-w-3xl text-sm text-muted-foreground">
          Your documents and career record stay in your account. To draft, Rhapto sends text from
          them to one AI provider:{" "}
          {SAME_ORIGIN_DEPLOYMENT ? "this beta’s during your free runs, then yours." : "yours."}
        </p>
        {SAME_ORIGIN_DEPLOYMENT ? (
          // The allowlist mechanics, moved out of the hero and shortened. No turnaround, no pronoun.
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
            Sign-in is an allowlist the maintainer keeps by hand, so an address that is not on it will
            be turned away.
          </p>
        ) : null}
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <Card className="h-full">
            <CardHeader>
              <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-sand text-foreground">
                <Coins className="size-4.5" aria-hidden />
              </span>
              <CardTitle className="text-base">Pricing</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              {/* "5 AI runs", not "5 tailored resumes": resume import spends a run too, and blocked
                  or failed runs count. The number is the server's RHAPTO_TRIAL_RUNS (5 as of
                  2026-09-29); nothing here reads it, so changing it means editing this sentence.
                  Hosted only: a self-hoster has no free runs. */}
              <p>
                {SAME_ORIGIN_DEPLOYMENT
                  ? "Free during the beta: 5 AI runs on us (importing your resume uses one), then use your own AI key. A paid plan with AI usage included is coming."
                  : "Free and open source (AGPL-3.0); you use your own AI key."}
              </p>
              <p>
                <a href="#developers" className="text-primary underline underline-offset-4">
                  Per-model costs
                </a>
              </p>
            </CardContent>
          </Card>
          <Card className="h-full">
            <CardHeader>
              <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-sand text-foreground">
                <Ban className="size-4.5" aria-hidden />
              </span>
              <CardTitle className="text-base">What it will not do</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <ul className="list-disc space-y-2 pl-4 marker:text-primary">
                <li>
                  Quietly let an unverified number or a line with no source through. Those two checks
                  always run, and a package that fails them after one fix attempt is marked blocked.
                  The check that job titles, employers and dates match your blocks is on by default.
                </li>
                <li>Spray hundreds of applications. It is built for a considered few, not volume.</li>
                <li>
                  Send your resume, your key, or your history anywhere except to one AI provider for
                  drafting:{" "}
                  {SAME_ORIGIN_DEPLOYMENT
                    ? "this beta’s during your free runs, then yours."
                    : "the one you picked."}
                </li>
              </ul>
            </CardContent>
          </Card>
          {/* Item 5, the ease-of-use requirement: a brand-new account has nothing in it -- one
              track at best, zero blocks, zero documents. The owner's wife hit exactly this: signed
              in, saw jobs, and an empty dashboard. This says, before the CTA below, what to bring so
              that surprise doesn't happen. Two lines of intro plus a three-item list, not a wall --
              a person who is surprised by this closes the tab instead of going to get their CV. */}
          <Card className="h-full">
            <CardHeader>
              <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-mint text-foreground">
                <ListChecks className="size-4.5" aria-hidden />
              </span>
              <CardTitle className="text-base">What you need first</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <p>A new account starts empty. Before Rhapto can produce anything, bring:</p>
              <ul className="mt-2 list-disc space-y-1.5 pl-4 marker:text-primary">
                <li>A resume to upload, or a few blocks written by hand</li>
                <li>One track &mdash; a field and a role</li>
                <li>Contact details and where you are willing to work</li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </section>

      <div className="mb-12 flex flex-wrap items-center gap-x-4 gap-y-3 border-t border-border pt-6">
        {/* Mirrors the hero, and keeps the same labels: someone who has read the whole page should not
            have to scroll back up to find the way in, and should not meet a different word for the
            same action down here. Two "Sign in" links on the page, one per place. */}
        {SAME_ORIGIN_DEPLOYMENT ? (
          <>
            <a {...accessAttrs} className={buttonVariants()}>
              Request beta access
            </a>
            <p className="text-sm text-muted-foreground">
              Already invited?{" "}
              <Link href="/dashboard" className="text-primary underline underline-offset-4">
                Sign in
              </Link>
            </p>
          </>
        ) : (
          <>
            <Link href="/settings" className={buttonVariants()}>
              Connect your instance
            </Link>
            {/* Token mode only. In hosted mode "Sign in" already goes to /dashboard; here the button
                beside it goes to /settings, so "head to the dashboard" names a different page for
                someone who has already connected. */}
            <p className="text-sm text-muted-foreground">
              Already set up? Head to the{" "}
              <Link href="/dashboard" className="text-primary underline underline-offset-4">
                dashboard
              </Link>
              .
            </p>
          </>
        )}
      </div>

      {/* Clearly separated and last: the material a developer or self-hoster wants, kept out of the
          conversion path but still on the page. */}
      <section
        aria-labelledby="developers-heading"
        id="developers"
        className="mb-10 scroll-mt-20 border-t border-border pt-10"
      >
        <h2 id="developers-heading" className="font-heading text-2xl font-medium">
          For developers &amp; self-hosting
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Rhapto is open source under AGPL-3.0. You can run your own instance with your own AI key.
        </p>
        {/* Card 1's copy, kept whole and moved verbatim. Every clause here was written after a real
            shipped defect: the first version claimed "it runs on your machine -- your resume and your
            key stay there", which is a privacy claim, and false for anyone invited onto a hosted
            instance, whose resume is in that server's database and whose provider key is encrypted
            there too. A privacy claim true for only half the readers is the one kind of copy that must
            never ship, because the people it misleads are deciding whether to upload a CV. */}
        <div className="mt-6 max-w-3xl rounded-card border-l-4 border-primary bg-surface-muted px-5 py-4">
          <h3 id="residency" className="font-heading text-lg font-medium">
            Wherever you run it
          </h3>
          <p className="mt-2 text-sm text-muted-foreground">
            Run it yourself and your blocks, your documents and your provider key stay on your
            machine. What does leave, on every run, is the text Rhapto sends to the model provider
            you chose &mdash; that is how the drafting happens, and it is true of any tool that
            uses a model. Rhapto sends the parts it needs and tells you which. On an instance you
            have been invited to, your data lives on that server, encrypted, and walled off from
            every other account. Your provider key is yours, and the only usage you pay for is
            your own.
          </p>
        </div>
        <Card className="mt-6 max-w-3xl">
          <CardHeader>
            <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-sand text-foreground">
              <Coins className="size-4.5" aria-hidden />
            </span>
            <CardTitle className="text-base">What it costs</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-muted-foreground">
            <p>
              Rhapto itself is free and AGPL-3.0 licensed. Run it yourself and the only bill is your
              own AI provider&rsquo;s.
            </p>
            <p>
              A tailored resume takes one or two model calls. Tested on the same real job in
              September 2026, that is about{" "}
              <strong className="font-medium text-foreground">29&ndash;36&cent;</strong> on Claude
              Opus 5 (from token counts at list price), up to{" "}
              <strong className="font-medium text-foreground">13.5&cent;</strong> on GPT-5 (billed),
              and an estimated{" "}
              <strong className="font-medium text-foreground">2&ndash;5&cent;</strong> on Gemini 3.7
              Flash (from token counts at Google&rsquo;s price through December 2026, which doubles
              from January 2027). That is the model calls only; it does not include running the
              server if you host it yourself.
            </p>
            <p>
              Cheaper is not automatically safe. On that same job Claude Haiku 4.5 passed every
              guardrail and still left a whole role out of the resume. Rhapto now also checks that
              every role it selected for the resume appears in the draft the model writes (not your
              own hand edits); a role it never selected is not flagged. Opus 5, GPT-5 and Gemini 3.7 Flash each kept every role, but that is two runs
              each on one job, so read the resume before you send it. The free trial runs on Claude
              Opus 5.
            </p>
          </CardContent>
        </Card>
      </section>
    </>
  );
}
