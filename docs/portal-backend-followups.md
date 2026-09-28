# Portal backend — follow-ups

Written at the end of the portal-backend implementation run (plan
`docs/superpowers/plans/2026-09-14-portal-backend.md`, branch `portal`). Every item here was
found by review, triaged as a follow-up rather than a merge blocker, and left deliberately
undone. Nothing in this list is a known-broken promise to a user; the blockers that were found
are fixed on the branch.

## 1. Decide what a track-less user sees (product call)

A saved search is derived from a track, and aggregators are driven by saved searches. A user who
enables a job source **before** creating any track therefore has nothing to search for.

Today `PUT /api/v1/settings/sources/{source}` is the only writer of an `Aggregator` row and it
always writes `keywords=[]`; nothing else ever sets that column. The keyless sources (The Muse,
Remotive) default to enabled. So "enable a source, then add a track" — a plausible onboarding
order — leaves the poller with no keywords and nothing to do. It skips that source silently:
no run row, no UI signal, only an INFO log.

That silence is deliberate (an aggregator with no query must not be recorded as a failure, or it
would trip the "paused after 3 failures" gate and hand the user advice that cannot help). But
silence is not the same as an answer. Options, cheapest first:

- Show "not searching yet — add a track, or give this source its own keywords" wherever sources
  are listed, and leave the backend as is.
- Let a source carry its own keywords (`Aggregator.keywords` already exists and is already read;
  only the write path is missing).
- Record an informational, non-failure run row so the Runs drawer can explain the skip. This one
  needs a run "kind" the schema does not have yet.

## 2. Worth doing soon

These compound with each other or with the item above.

- A keyed source with no key saved reports "no API key" per poll, and after three polls flips to
  "paused after 3 failures" — the less actionable message wins. Same unactionable-pause shape as
  the item above; fix them together.
- `TaxonomyError` has no named `problem+json` handler, so it falls through to a generic 500. It is
  now reachable from **every track write** (taxonomy validation runs there), and this file's path
  resolution has already broken once (the eager `parents[5]` crash that stopped the containers
  booting). A missing taxonomy file should not look like an unexplained server error.
- `GET /jobs?recommended=true` does not itself exclude hidden jobs; it is correct today only
  because the separate `hidden` filter defaults to false. One explicit predicate removes the
  implicit coupling.
- A blocked package can be demoted to `draft`, which puts it back in the "needs review" count
  while its guardrail report still says `passed: false`. It cannot be marked ready (that path
  checks the report), so this is a display problem, not a safety one.
- `POST /search` with an unknown id in `sources` silently narrows the fan-out to nothing instead
  of returning 422.
- Live-search jobs are never marked "no longer listed": `POST /search` stores them with no
  `search_id`, and every reconciliation is scoped to a search or a company. Errs safe — nothing is
  wrongly retired — but a dead posting keeps offering Tailor.
- `Job.search_id` has no index. It is now filtered in the job list, grouped in the saved-search
  counts, and scoped in unlisted detection. It will want one before the jobs table grows.

## 3. Routine

- Adzuna's credential redaction matches the raw value, but the URL carries the percent-encoded
  one; a key containing `+`, `/`, `=` or a space would survive into a stored error. Adzuna ids are
  hex in practice, so this is latent.
- Jooble builds its key into the URL path unquoted (quoting it would break the adjacent
  redaction) — worth a comment saying so.
- The fake provider's `<blocks>` parsing anchors on the last literal occurrence of the tag; block
  content containing that literal string would break it. Test/demo-only code.
- The fake provider's attribution path digit-checks the block content but not the appended
  attribution string. A digit there produces a *blocked* package, never a dishonest one — the
  metrics guardrail catches it — so this is a tension between two guardrails, not a leak.
- `POST /search`'s per-source `found` count includes jobs that the result list then omits because
  they are hidden, so the count and the list can disagree.
- `fernet_for(settings)` is caught and degraded on the live-search path but uncaught on
  `PUT /settings/sources/{source}` and the source test endpoint — the same misconfiguration is a
  warning in one place and a 500 in another.
- The dashboard's seven reads run sequentially; `asyncio.gather` would cut first-screen latency.
- `needs_review_count` and `due_followups` join without an explicit `Job.user_id` filter, relying
  on the package/application scoping. Safe today; an explicit filter is cheap.
- Missing tests, all inert by inspection: cross-user isolation for `/searches` and
  `/settings/sources` (the pattern exists elsewhere now), re-marking an already-ready package,
  promoting an archived-but-latest package, the `MAX_SUGGESTIONS` cap, and four sources' identical
  malformed-item skip paths.
- Small cleanups: field/role id uniqueness is enforced by test but not by schema or loader;
  `roles_by_name()` rebuilds per request; duplicated `SOURCES[...].info` lookups in the poller and
  in the settings router; a stray leading space in two docstrings; migration 0006 names a
  constraint the other migrations leave unnamed.

## 4. Not verified

- The README's docker + curl walkthrough (`## Find jobs across the whole market`) was written but
  never executed — it rebuilds the stack, calls live third-party APIs, and runs a paid tailor.
  Run it once before trusting it.
- The five new sources are exercised against fixtures only. The first live run may find mapping
  surprises; malformed items degrade to skipped rows rather than failures.
- The fake provider's end-to-end behaviour is proven by unit tests and one manual Docker run, not
  by an automated e2e suite — that belongs to the portal-ui plan.

## 5. From the final whole-branch review (portal-ui, 2026-09-19)

Two items the review found and triaged as follow-ups, not blockers for this branch:

- **`GET /api/v1/jobs` has no `limit`/`offset`.** The whole corpus is re-fetched on every filter
  change on the Jobs page (client-side paging over the full result set — see `BROWSE_PAGE_SIZE` in
  `apps/web/src/app/jobs/page.tsx`). Two things make this worse than it looks: `JobOut` carries the
  full `jd_text` for every row, not a summary, so each response is heavier than the list actually
  needs; and `useRecommendedJobs` (`apps/web/src/lib/api/queries.ts`) has the identical problem —
  it also fetches its whole recommended set in one call and pages client-side, for the same
  "the schema has no limit/offset param" reason (see that function's own comment). Real
  server-side pagination needs a schema change (`GET /jobs` query params, `JobOut` trimmed for
  list views) big enough to be its own piece of work, not a fix folded into a review-response wave.
- **Dead-weight cleanup**: `apps/web/src/components/jobs/RunsDrawer.tsx` and
  `apps/web/src/components/jobs/AddJobDialog.tsx` are unreferenced outside their own files and
  tests — nothing in `apps/web/src/app/**` imports either. Also worth checking: `queries.ts` for
  exports nothing else calls. Not removed here because
  `apps/web/src/lib/no-queue.test.ts:15` currently *asserts both components must exist*
  (`for (const file of [..., "RunsDrawer.tsx", "AddJobDialog.tsx"]) expect(jobs).toContain(file)`)
  — deleting the components without first updating that test would just trade one inconsistency
  for another, and the test itself is what a future cleanup pass needs to touch first.

## 6. From the failure-visibility branch (2026-09-27)

- **`poll_runs` grows without bound and now has a grouped read over it.** Condition C6 of
  `.superpowers/sdd/2026-09-27-failure-visibility/architecture.md`. `search_run_stats`
  (`apps/api/src/rhapto/db/repositories/discovery.py`) aggregates
  `poll_runs WHERE user_id = :u AND search_id IS NOT NULL GROUP BY search_id`, and is called by
  `GET /searches`, `GET /dashboard` and `GET /jobs/empty-reason`. `poll_runs` has **no retention
  policy**: it gains one row per (source x active search) per poll, forever. It is the one query on
  this branch that grows without bound.

  Not a blocker today — the existing `ix_poll_runs_lookup (user_id, source, board, started_at DESC)`
  already restricts the scan to one user, and the table holds thousands of rows. Two ways to fix it
  when it matters, in the order they are worth doing:
  1. A covering index on `(user_id, search_id, started_at DESC)`, which is the exact shape of this
     query.
  2. A retention job -- and the architect's §12.5 ruling (2026-09-28) makes this an order, not a
     preference. Deleting old rows changes an *answer*, not a cost. `ever_found` is
     `max(found) > 0` over the *whole history*, so pruning the run that once found something makes
     a working search report "has never returned a job" -- manufacturing, gradually and silently as
     history ages out, the exact false negative this branch was built to eliminate. No test would
     fail.

     Therefore: **a per-search success summary (`searches.first_found_at`, or a flag written at
     ingest) is a precondition of retention, not an optimisation of it.** That is a migration, so
     no retention job may run against `poll_runs` until it exists. Do the index first; retention
     only after the summary column.

     If retention ever ships without one, `SearchOut.ever_found` and
     `JobsEmptyReasonOut.search_ever_found` must become `bool | None`, where `None` renders as
     "not known" and never as "never found anything". Degrading to unknown is honest; degrading to
     `false` is a confident lie.

- **The keyless-source default disagrees with what the poller actually polls.** Condition C4; found
  by the architecture pass on this branch and deliberately **not** fixed here, because the fix is a
  behaviour decision for the owner.
  - `GET /settings/sources` reports `enabled = KEYLESS_DEFAULT_ENABLED and not needs_key` for a
    user with no `aggregators` row (`apps/api/src/rhapto/api/routers/settings.py`).
  - `build_specs` takes `enabled = [a for a in list_aggregators(...) if a.enabled]` and **returns
    early with board specs only when that list is empty**
    (`apps/api/src/rhapto/services/discovery/poller.py`). A user with zero `aggregators` rows
    therefore polls **no aggregators at all**, while Settings shows four keyless sources as on.

  This branch makes it visible (`SourceSettingOut.runnable = false`, `checklist.job_sources = false`,
  "No source can run yet") and changes nothing about what gets polled. The two candidate fixes are
  seeding `aggregators` rows on bootstrap, or making `build_specs` honour the display default — the
  second starts calling four external APIs for every account that never opened Settings, which is
  why it is the owner's call and not this branch's.

## 7. Provider model lists have gone stale (queued 2026-09-28)

`apps/api/src/rhapto/engine/providers/registry.py` hard-codes a `models` tuple and a `default` per
provider. Those were written months ago and vendors retire ids quietly, so the dropdown a new user
picks from offers models that are dead or several generations old.

Confirmed against live vendor catalogues on 2026-09-27/28:

- **Gemini** ships `("gemini-2.5-pro", "gemini-2.5-flash")`, default `gemini-2.5-pro`. Google's own
  `v1beta/models` currently serves `gemini-3.8-flash`, `3.7`, `3.6`, `3.5-flash`, `3.1-pro-preview`
  and more. Three generations behind.
- **Groq** ships `llama-3.3-70b-versatile` as its default; that id and `moonshotai/kimi-k2-instruct`
  both returned `model_not_found` for a real key. The default is dead on arrival.
- **OpenRouter** ships `meta-llama/llama-3.3-70b-instruct`; unverified, same risk.

Two fixes, and the second is the one that lasts:

1. Refresh each provider's tuple and default against its live catalogue.
2. Prefer vendor-maintained rolling aliases as the default wherever one exists -- Google publishes
   `gemini-flash-latest` and `gemini-pro-latest`, which do not rot. A pinned id in a registry is a
   thing that must be maintained forever; an alias is maintained by the vendor.

Why it matters beyond tidiness: a new account's first action is choosing a provider and model, and a
dead default produces a `model_not_found` at the first tailor -- after the LLM call has been paid
for, deep in the worker. That is the cold-start failure the failure-visibility branch exists to
remove, arriving through the one door that branch does not cover.
