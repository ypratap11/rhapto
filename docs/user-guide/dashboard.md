# Dashboard

The Dashboard (`/`) is where you land, and it reports facts about your own search rather than
promotional copy.

![Dashboard](images/dashboard-light.png)

## What the headline means

The hero band shows two numbers, both from one call to the API: how many new roles fit you this
week, and how many resumes are waiting for your review. "New" means discovered in the last 7 days
with a fit at or above your track's threshold, and not hidden or no-longer-listed. When both
numbers are zero, the headline changes to "Nothing new yet" with buttons to start a new search or
add a company to your watchlist instead.

## When a refresh fails

The Dashboard is careful to distinguish "nothing to show" from "couldn't refresh." If a background
refresh of the dashboard fails — the API is briefly unreachable, for instance — and you already
have data on screen from an earlier successful load, that content stays exactly as it was: the
headline numbers, the profile checklist, and the saved searches rail all keep showing what they
last loaded, stale but genuine. A banner appears above the hero band telling you the refresh
failed, so the staleness is visible rather than silent, but nothing is cleared out from under you.
Only when there is truly nothing cached yet — for example, the very first load fails — does a panel
fall back to its own "Couldn't load" message instead of real content.

## Recommended roles

Below the search card, **Recommended roles** lists fit-ranked jobs that have no resume and no
application yet, aren't hidden, and aren't marked no-longer-listed — ten per page, up to five
pages. Each card is the same card the Jobs grid uses: fit ring, title, company, track chip,
location-tier chip, source chip, a two-line excerpt of the description, and Tailor / Not interested
buttons.

## Active applications

This panel shows your three most recently updated pipeline applications, plus any resume that's
ready but not yet marked applied. Any of those with a follow-up due today sort to the front with a
red "Follow up today" chip — the follow-up reminder set from the Pipeline page surfaces here rather
than in a separate list you'd have to check on its own.

## Profile checklist

The right rail's checklist has six rows, each either checked or open, with an Edit link into the
matching Profile card:

1. **Resume template** — a `.docx` uploaded.
2. **Contact and answers** — name, email, phone, location, and links filled in.
3. **Tracks** — at least one track exists.
4. **Verified blocks** — shown as "{verified} of {total} verified"; passes once at least one block
   is verified.
5. **Guardrails** — at least one guardrail rule configured (Rhapto's defaults count).
6. **Location preferences** — home location, preferred areas, and remote preference all set.

## Saved searches

The rail also lists your saved searches, each with an "N new" count — jobs discovered since you
last opened that search's results. Opening a saved search's results from here (or from Jobs) is
what clears its count; the count doesn't clear just because time has passed.
