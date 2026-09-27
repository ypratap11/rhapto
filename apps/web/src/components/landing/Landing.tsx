/** Rhapto's pitch: what it does, why it is a promise rather than a chatbot, the provenance demo,
 * the six-beat walkthrough of the journey, where your data lives, and what it costs.
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
import { ACCESS_REQUEST_EMAIL, ACCESS_REQUEST_MAILTO } from "./access";
import { JourneyWalkthrough } from "./JourneyWalkthrough";
import { ProvenanceDemo } from "./ProvenanceDemo";


// The three non-negotiable product rules, written for someone who has never seen the repo. They
// are the reason to choose Rhapto over a chat window, so they come before the steps.
const PROMISES = [
  {
    icon: Fingerprint,
    title: "Every line has a source",
    body: "Each bullet cites a block from your own library, and the renderer refuses a resume carrying a bullet it cannot trace. “Where did that come from?” always has an answer.",
  },
  {
    icon: BadgeCheck,
    title: "Numbers need your sign-off",
    body: "Rhapto is told to write “several teams,” never “fifteen teams,” until you have marked that number verified. If it writes the number anyway, the guardrail catches it and marks the whole package blocked — so the promise does not rest on the model behaving.",
  },
  {
    icon: Hand,
    title: "The last click is yours",
    body: "Rhapto opens the employer’s own page and hands you the file. There is no code path in it that submits an application, and there never will be.",
  },
] as const;

export function Landing() {
  return (
    <>
      <HeroBand tone="peach" height="tall">
        <p className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Open source &middot; Human in the loop
        </p>
        {/* Display size (item 1): a `clamp` so the same class reads as a strong headline on a
            360px phone (clamps to the 2.75rem floor) and genuine display type on desktop (up to
            5rem), rather than one fixed size that is either too small or overflowing. `max-w-4xl`
            (wider than the old `max-w-3xl`) keeps the measure sane at that size -- a narrower box
            would wrap this into three cramped lines instead of two confident ones. */}
        <h1 className="max-w-4xl font-heading text-[clamp(2.75rem,4vw+1.75rem,5rem)] leading-[0.95] font-medium tracking-tight">
          Every application, stitched to fit.
        </h1>
        <p className="max-w-2xl text-base text-muted-foreground sm:text-lg">
          Rhapto finds the roles, writes the resume, and shows you where every word came from. Then
          it steps back and lets you send it.
        </p>
        {/* Plain styled links, not the Base UI `Button` primitive: both of these navigate, and
            `Button render={<Link/>}` forces a choice between misreporting them as role="button"
            (`nativeButton={false}`) or a dev-mode console error. Same house style, neither cost —
            the pattern JobCard and RepostNotice already settled on. */}
        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-3">
          {/* Review finding I3: in access mode there is nothing to "connect" -- Cloudflare Access
              already signed this visitor in, and /settings' only connection card is hidden there
              (N1), so the token-mode wording sent an invited person to a page with nothing on it,
              away from the route that seeds their account.
              The label is "Sign in" rather than "Open your dashboard" because until today the page
              told people to sign in and then offered them no way to: /dashboard sits behind
              Cloudflare Access, so following this link IS the sign-in flow. There is no /login
              route to point at, and inventing one would 404. */}
          <Link
            href={SAME_ORIGIN_DEPLOYMENT ? "/dashboard" : "/settings"}
            className={buttonVariants({ size: "lg" })}
          >
            {SAME_ORIGIN_DEPLOYMENT ? "Sign in" : "Get started"}
          </Link>
          {/* Hosted only, and the branch is load-bearing: a self-hoster has nobody to request access
              from -- their instance is theirs -- so offering them this would be the same class of
              dead end the "Sign in" fix above removes. */}
          {SAME_ORIGIN_DEPLOYMENT ? (
            <a
              href={ACCESS_REQUEST_MAILTO}
              className={buttonVariants({ size: "lg", variant: "outline" })}
            >
              Request access
            </a>
          ) : null}
          {/* Demoted from an outline button to a text link: with a second real CTA beside the
              primary one, three buttons of equal weight would leave a stranger with no idea which
              one is the way in. */}
          <a href="#how" className="text-sm text-primary underline underline-offset-4">
            See how it works
          </a>
        </div>
        {SAME_ORIGIN_DEPLOYMENT ? (
          // Says out loud what the "Sign in" button cannot: there is no registration, and the reason
          // an unknown email is refused is not a bug. No response time is promised here, because
          // nobody has committed to one, and no pronoun either -- the maintainer is unnamed on this
          // page and nobody's are stated on it. The address is spelled out as text as well as being
          // the button's href: a visitor with no registered mail handler otherwise gets a button
          // that does nothing and no way to learn where to write.
          <p className="max-w-2xl text-sm text-muted-foreground">
            Rhapto is invite-only today &mdash; sign-in is an allowlist the maintainer keeps by hand,
            so an address that is not on it will be turned away. Request access opens an email to{" "}
            {ACCESS_REQUEST_EMAIL} for you to send, asking for yours to be added.
          </p>
        ) : null}
        <p className="max-w-2xl text-sm text-muted-foreground">
          A new account starts empty. You will need a resume to upload (or a few blocks written by
          hand), one track, and your contact details before Rhapto can produce anything.{" "}
          <a href="#honest" className="text-primary underline underline-offset-4">
            What that means
          </a>
        </p>
      </HeroBand>

      {/* The human reason, before any mechanism. Everything below this explains HOW Rhapto works;
          without this, nothing on the page says why it should exist. Deliberately prose in a single
          block rather than the card grids used elsewhere -- it is meant to be read, not scanned. */}
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
              that is true to what you have actually done. It will not apply on your behalf, and it
              will not invent anything to make you look better — it refuses to do either. What is
              left is the part that needs a person: deciding where to apply, and what to say when
              someone answers.
            </p>
          </div>
        </div>
      </section>

      <section aria-labelledby="why" className="mb-12">
        <h2 id="why" className="font-heading text-2xl font-medium">
          Why not just ask a chatbot?
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Because a chatbot will happily invent the number that gets you the interview, and you will
          not find out until someone asks you about it. Rhapto is built so that cannot happen.
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
      </section>

      {/* Item 2, the centrepiece: the claim two paragraphs up ("Rhapto is built so that cannot
          happen") shown happening, on Rhapto's own output, rather than asserted a second time. All
          interaction lives in `ProvenanceDemo`, a separate `"use client"` component -- this section
          itself stays a plain server-rendered wrapper, same as the rest of `Landing`. */}
      <section aria-labelledby="demo-heading" className="mb-12">
        <HeroBand tone="sand" height="tall">
          <p className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
            The mechanism, not a claim about it
          </p>
          <h2 id="demo-heading" className="font-heading text-2xl font-medium">
            Every bullet knows where it came from
          </h2>
          <p className="max-w-2xl text-sm text-muted-foreground">
            A resume fragment in Rhapto&rsquo;s layout. Every line traces back to a fact already
            confirmed &mdash; and the refusal you can switch on below is the validator&rsquo;s own
            output: rule, path and message exactly as it produces them.
          </p>
          <div className="mt-2">
            <ProvenanceDemo />
          </div>
        </HeroBand>
      </section>

      {/* The six beats are the only telling of the journey now. The five "How it works" cards that
          used to sit under them said the same thing a second time -- three of the five were pure
          paraphrase -- and a paragraph explaining why there were two of everything is evidence of a
          duplication, not a fix for one. Card 1 was the exception and did not die with them: it was
          never really a step, it is the data-residency and who-pays disclosure, and it is below. */}
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
          {/* Card 1's copy, kept whole. Every clause here was written after a real shipped defect:
              the first version claimed "it runs on your machine -- your resume and your key stay
              there", which is a privacy claim, and false for anyone invited onto a hosted instance,
              whose resume is in that server's database and whose provider key is encrypted there
              too. A privacy claim true for only half the readers is the one kind of copy that must
              never ship, because the people it misleads are deciding whether to upload a CV. It sits
              beside the beats rather than inside one because it is not a step -- nobody does it --
              and burying it in beat 1's body would have made the beat unreadable. */}
          <div className="mt-8 max-w-3xl rounded-card border-l-4 border-primary bg-surface/70 px-5 py-4">
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
        </HeroBand>
      </section>

      <section aria-labelledby="honest" className="mb-10">
        <h2 id="honest" className="scroll-mt-20 font-heading text-2xl font-medium">
          Before you start
        </h2>
        <div className="mt-6 grid gap-4 md:grid-cols-3">
          <Card className="h-full">
            <CardHeader>
              <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-sand text-foreground">
                <Coins className="size-4.5" aria-hidden />
              </span>
              <CardTitle className="text-base">What it costs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                Rhapto itself is free and AGPL-3.0 licensed. There is no subscription, and nothing
                to sign up for &mdash; the hosted instance is invite-only, so access is an address on
                an allowlist rather than an account you create. The only bill is your own LLM
                provider&rsquo;s.
              </p>
              <p>
                A tailored resume takes two model calls. Measured on a real run, that is{" "}
                <strong className="font-medium text-foreground">29&ndash;36&cent;</strong> on Claude
                Opus 5, or{" "}
                <strong className="font-medium text-foreground">5.8&cent;</strong> on Haiku 4.5, at
                list prices as of September 2026. That is the model calls only; it does not include
                running the server if you host it yourself.
              </p>
              <p>
                Rhapto defaults to the stronger model on purpose. On that same job the cheap one
                passed every guardrail and still left a whole role out of the resume &mdash; the
                checks catch invented claims, not missing ones. Until that gap is closed, the cheap
                path is not the recommended one.
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
                  Submit an application, fill an employer&rsquo;s form, or click anything on your
                  behalf.
                </li>
                <li>
                  Write a number, a job title, or a date that is not already in a block you wrote.
                </li>
                <li>Spray hundreds of applications. It is built for a considered few, not volume.</li>
                <li>
                  Send your resume, your key, or your history anywhere except the model provider you
                  picked.
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

      <div className="flex flex-wrap items-center gap-4 border-t border-border pt-6">
        {/* Same mode-awareness as the hero CTA above (review finding I3), and the same pair of labels:
            someone who has read the whole page should not have to scroll back up to find the way in,
            and should not meet a different word for the same action down here. */}
        <Link
          href={SAME_ORIGIN_DEPLOYMENT ? "/dashboard" : "/settings"}
          className={buttonVariants()}
        >
          {SAME_ORIGIN_DEPLOYMENT ? "Sign in" : "Connect your instance"}
        </Link>
        {SAME_ORIGIN_DEPLOYMENT ? (
          <a href={ACCESS_REQUEST_MAILTO} className={buttonVariants({ variant: "outline" })}>
            Request access
          </a>
        ) : null}
        {/* Token mode only. In access mode this sentence sat next to a "Sign in" link to the very
            same route, which is one destination with two contradictory framings. In token mode it
            still earns its place: the button beside it goes to /settings, so "head to the dashboard"
            names a different page for someone who has already connected. */}
        {SAME_ORIGIN_DEPLOYMENT ? null : (
          <p className="text-sm text-muted-foreground">
            Already set up? Head to the{" "}
            <Link href="/dashboard" className="text-primary underline underline-offset-4">
              dashboard
            </Link>
            .
          </p>
        )}
      </div>
    </>
  );
}
