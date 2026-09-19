# What Rhapto is

Rhapto is an open-source, human-in-the-loop job-application copilot. It discovers roles from the
whole market and from the company boards you follow, scores each one against your own career
tracks, and — when a role is worth pursuing — tailors a resume package with an LLM and queues it
for you to review. It does not automate the application itself: Rhapto's job ends at a package you
can trust, not at a submitted form.

## Who it is for

Rhapto is for someone running their own search who wants quality over volume: a handful of
well-targeted, carefully reviewed applications rather than hundreds of identical ones. It expects
you to keep a small library of facts about your own career — the blocks described in
[`concepts.md`](concepts.md) — and to spend a few minutes reviewing every resume before it goes
out. If what you want is a bot that fires off applications unattended, Rhapto is the wrong tool by
design.

## The human-in-the-loop rule

Rhapto opens the employer's own application page and downloads the tailored resume for you; the
last click — the one that actually submits — is always yours. No code path in this repository
submits an application on your behalf. This is rule 1 of
[`CLAUDE.md`](../../CLAUDE.md#non-negotiable-product-rules), and every screen in the portal is
built around it: Apply opens a new tab and asks "Did you apply?" afterward rather than assuming
the answer.

## What it is not

- **Not an auto-apply bot.** Nothing in Rhapto fills out or submits an employer's application
  form.
- **Not a scraper of LinkedIn, Indeed, or Glassdoor.** Those sites' own terms forbid it. Rhapto
  reads from open aggregator APIs (The Muse, Remotive, RemoteOK, HN Who's Hiring, Adzuna, Jooble,
  JSearch) and from the ATS boards companies publish themselves (Greenhouse, Lever, Ashby,
  Workday) — see [`sources.md`](sources.md).
- **Not a resume-writing service that invents experience.** Every fact and every metric in a
  generated resume traces back to something you wrote yourself; guardrails reject anything that
  doesn't. See [`concepts.md`](concepts.md).

## Where to start

If you want to use Rhapto rather than read about its design, start with
[`../user-guide/getting-started.md`](../user-guide/getting-started.md).
