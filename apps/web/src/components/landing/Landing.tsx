/** Rhapto's pitch: what it does, why it is not a chatbot, the five steps, and what it costs.
 *
 * Rendered at two mounts, which is why it is a component and not just a page: `/about` (its own
 * URL, linkable, readable by someone already connected) and `/` via `TokenGate` for anyone who
 * is NOT connected -- a stranger arriving at the root should meet the explanation, not a bearer
 * token field. Keep it free of client hooks: `TokenGate` is a client component and this has to
 * render inside it, while `/about` stays a server component. */
import Link from "next/link";
import {
  Ban,
  BadgeCheck,
  Coins,
  Compass,
  FileUp,
  Fingerprint,
  Hand,
  KeyRound,
  Radar,
  Send,
} from "lucide-react";
import { HeroBand } from "@/components/shell/HeroBand";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";


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
    body: "A metric only prints once you have marked that fact verified. Until then Rhapto writes “several teams,” never “fifteen teams.” It cannot round up on your behalf.",
  },
  {
    icon: Hand,
    title: "The last click is yours",
    body: "Rhapto opens the employer’s own page and hands you the file. There is no code path in it that submits an application, and there never will be.",
  },
] as const;

const STEPS = [
  {
    icon: KeyRound,
    title: "Connect",
    body: "Point Rhapto at your own instance and add one LLM provider key. It runs on your machine — your resume and your key stay there.",
  },
  {
    // Describes what `main` does TODAY. Resume -> block library is the `resume-import` branch; when
    // that merges, this becomes "Upload a .docx and Rhapto breaks it into blocks you own, every
    // number unverified until you confirm it." Promising it before it ships would make this page
    // the one thing on the site that overstates what Rhapto does.
    icon: FileUp,
    title: "Bring your resume",
    body: "Upload a .docx and Rhapto tailors that document in place, editing your own wording rather than writing over it. Or build a library of blocks — roles, projects, achievements — and let it compose from those.",
  },
  {
    icon: Compass,
    title: "Pick a track",
    body: "Choose a field and a role. That is the target every job gets scored against, with curated keywords and a fit threshold you control.",
  },
  {
    icon: Radar,
    title: "Let the jobs come to you",
    body: "Search when you want to, or let Rhapto poll company boards and job aggregators in the background and score everything it finds against your tracks.",
  },
  {
    icon: Send,
    title: "Tailor, review, apply",
    body: "One click drafts a resume and cover note for one posting. The guardrails run before you ever see it. You read it, you decide, and you are the one who applies.",
  },
] as const;

export function Landing() {
  return (
    <>
      <HeroBand tone="peach" height="tall">
        <p className="text-xs font-medium tracking-[0.14em] text-muted-foreground uppercase">
          Open source &middot; Human in the loop
        </p>
        <h1 className="max-w-3xl font-heading text-4xl leading-tight font-medium sm:text-5xl">
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
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <Link href="/settings" className={buttonVariants({ size: "lg" })}>
            Get started
          </Link>
          <a href="#how" className={buttonVariants({ size: "lg", variant: "outline" })}>
            See the five steps
          </a>
        </div>
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

      {/* A 6-column grid so five cards land 3-then-2 instead of leaving a ragged hole in the last
          row of a 3-column grid: the first three span 2 columns each, the last two span 3. */}
      <section aria-labelledby="how-heading" className="mb-12 scroll-mt-20" id="how">
        <h2 id="how-heading" className="font-heading text-2xl font-medium">
          How it works
        </h2>
        <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
          Five steps from a cold install to a resume you would put your name on. The first three you
          do once; the last two you repeat per job.
        </p>
        <ol aria-labelledby="how-heading" className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-6">
          {STEPS.map(({ icon: Icon, title, body }, i) => (
            <li key={title} className={i < 3 ? "lg:col-span-2" : "lg:col-span-3"}>
              <Card className="h-full">
                <CardHeader>
                  <div className="mb-1 flex items-center gap-2.5">
                    <span
                      aria-hidden
                      className="flex size-7 items-center justify-center rounded-full bg-primary font-mono text-xs font-medium text-primary-foreground"
                    >
                      {i + 1}
                    </span>
                    <Icon className="size-4 text-muted-foreground" aria-hidden />
                  </div>
                  <CardTitle className="text-base">{title}</CardTitle>
                </CardHeader>
                <CardContent className="text-sm text-muted-foreground">{body}</CardContent>
              </Card>
            </li>
          ))}
        </ol>
      </section>

      <section aria-labelledby="honest" className="mb-10">
        <h2 id="honest" className="font-heading text-2xl font-medium">
          Before you start
        </h2>
        <div className="mt-6 grid gap-4 md:grid-cols-2">
          <Card className="h-full">
            <CardHeader>
              <span className="mb-1 flex size-9 items-center justify-center rounded-card bg-band-sand text-foreground">
                <Coins className="size-4.5" aria-hidden />
              </span>
              <CardTitle className="text-base">What it costs</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-muted-foreground">
              <p>
                Rhapto itself is free and AGPL-3.0 licensed. There is no account and no
                subscription. The only bill is your own LLM provider&rsquo;s.
              </p>
              <p>
                A tailored resume takes two model calls. Measured on a real run, that is{" "}
                <strong className="font-medium text-foreground">29&ndash;36&cent;</strong> on Claude
                Opus 5, or{" "}
                <strong className="font-medium text-foreground">5.8&cent;</strong> on Haiku 4.5, at
                today&rsquo;s list prices.
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
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-4 border-t border-border pt-6">
        <Link href="/settings" className={buttonVariants()}>
          Connect your instance
        </Link>
        <p className="text-sm text-muted-foreground">
          Already set up? Head to the{" "}
          <Link href="/" className="text-primary underline underline-offset-4">
            dashboard
          </Link>
          .
        </p>
      </div>
    </>
  );
}
