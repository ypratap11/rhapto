# Concepts

The words below mean something specific in Rhapto. This page defines each one once so the rest of
the docs can use them without re-explaining.

## Tracks

A track is a named target role that jobs are scored against — for example "Data Program
Management" or "AI Product/Program". Each track carries a name, a set of keywords, a resume base
to build from, and a fit threshold (`min_fit`). You create one with the field/role picker on the
Profile page (Profile → Tracks → **Pick a field and role**): choosing a role from the taxonomy
creates a track with that role's curated keywords and a fit threshold of 60. Tracks stay editable
afterward — name, keywords, and threshold — in the same card.

## Fit

Fit is a 0–100 score for how well a job matches your *best* track, computed without ever calling
an LLM. It is then scaled by a location-priority multiplier — preferred area ×1.0, remote ×0.95,
US ×0.85, abroad ×0.60, unknown ×0.90 — so a great role on the wrong continent cannot outrank a
good one close to home. As a rule of thumb, 75 and above is a strong fit; 60 and above is worth a
look. A job that hasn't been scored yet shows a dashed ring instead of a number.

## Blocks

A block is one fact about your career: a role, an achievement, a project, or a credential. The
block library (Profile → Blocks) is the only material a generated resume is allowed to draw
bullets from — every bullet in a tailored resume carries a `source_block_id` that must resolve to
a real block, and the renderer rejects any bullet that doesn't.

## Verified metrics

A block may carry a `metric` (a number, like "cut warehouse cost 18%"), but only if that block is
also marked `verified: true`. The guardrail validator enforces this: a metric that doesn't trace
back to a verified block is rejected before it can appear in a resume, so nothing in your output
is a number you never actually confirmed.

## Guardrails

Guardrails are the rules that check a generated resume before it's shown to you: no unverified
metrics, no invented entities (employers, products, tools not in your blocks), date consistency,
correct attribution, and visibility context. When a rule fails, the resume's status becomes
**Blocked** rather than being silently fixed — the Resumes page shows a Blocked tab, and the job
and review pages show a guardrail panel listing every violation with a link to jump straight to
it.

## Resumes / packages

A "package" is one tailored version of a resume for one job. Packages are versioned — regenerating
or editing a package creates a new version rather than overwriting the old one — and built in one
of two modes: **blocks mode** composes a new resume from your block library; **tune mode** (used
automatically once you've uploaded your own resume document) edits your own document's wording in
place. A package moves through **needs review → ready → applied** as you work it: it starts
needing your review, you mark it ready once you're happy with it, and it becomes applied once you
confirm you sent it. A guardrail failure diverts it to **blocked** instead of ready.

## Your applications

The Dashboard's **Your applications** list tracks what you've actually applied to, independent of the resume that got you there.
An application moves **applied → screen → interview → offer**, or is **closed** with one of four
reasons (rejected, withdrew, no response, filled). Every application keeps notes, a status history,
and an optional follow-up date.

## Saved searches

A saved search is a search (title, location, field, remote preference) that Rhapto polls on its
normal schedule, the same way it polls your watchlist. Rhapto derives one saved search per track
automatically the first time it polls, and you can save any search from the Jobs page too. Each
saved search tracks "N new" — jobs it discovered since you last opened its results — which clears
the moment you open that search's results, not just by existing.
