# Concepts

The words below mean something specific in Rhapto. This page defines each one once so the rest of
the docs can use them without re-explaining.

## Roles you want (tracks)

A track, shown in the app as one of your **Roles you want**, is a named target role that jobs are scored against — for example "Data Program
Management" or "AI Product/Program". Each track carries a name, a set of keywords, a resume base
to build from, and a fit threshold (`min_fit`). You create one with the field/role picker on the
Profile page (Profile → Roles you want → **Pick a field and role**): choosing a role from the taxonomy
creates a track with that role's curated keywords and a fit threshold of 60. Tracks stay editable
afterward — name, keywords, and threshold — in the same card.

## Fit

Fit is a 0–100 score for how well a job matches your *best* track, computed without ever calling
an LLM. It is then scaled by a location-priority multiplier — preferred area ×1.0, remote ×0.95,
US ×0.85, abroad ×0.60, unknown ×0.90 — so a great role on the wrong continent cannot outrank a
good one close to home. As a rule of thumb, 75 and above is a strong fit; 60 and above is worth a
look. A job that hasn't been scored yet shows a dashed ring instead of a number.

## Your experience (blocks)

A block, shown in the app as an item in **Your experience**, is one fact about your career: a role,
an achievement, a project, or a credential. In Full rewrite, Your experience (Profile → Your
experience) is the only material a generated resume may draw lines from - every line carries a
`source_block_id` that must resolve to a real item, and the renderer rejects any line that doesn't.
Light touch works on your uploaded resume file instead.

## Verified metrics

A block may carry a `metric` (a number, like "cut warehouse cost 18%"), and in Full rewrite it is
used only if that block is also marked `verified: true` (confirmed by you in the app). In Light
touch, a number must already appear in your uploaded resume file. Either way the check runs before
a resume is shown, so nothing in your output is a number you never actually confirmed.

## Writing rules (guardrails)

Guardrails, shown in the app as **Writing rules** and as the truth check on a resume, are the rules
that check a generated resume before it's shown to you: no unverified
metrics, no invented entities (employers, products, tools not in your blocks), date consistency,
correct attribution, and visibility context. When a rule fails, the resume's status becomes
**Needs attention** (stored as `blocked`) rather than being silently fixed - My resumes shows a
Needs attention tab, and the job and resume pages list every line that did not pass with a link
to jump straight to it. The provenance and no-unverified-metrics checks always run; they are not
switches.

## Resumes / packages

A "package" is one tailored version of a resume for one job. Packages are versioned — regenerating
or editing a package creates a new version rather than overwriting the old one — and built in one
of two modes: **Full rewrite** (stored as blocks mode) rebuilds a resume from Your experience, with
each line citing its source; **Light touch** (stored as tune mode, the default once you've uploaded
your own resume file) rewords a few lines of your own document in place. A package moves through
**To review → Ready to send → applied** as you work it: it starts needing your review, you press
**Mark ready to send** once you're happy with it, and it becomes applied once you confirm you sent
it. A truth-check failure diverts it to **Needs attention** instead of ready.

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
