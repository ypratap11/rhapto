# Coach (/start) and light homepage — design

Date: 2026-10-08 · Status: revision 4 — owner-approved rev 3 + readiness marker (plan-review C1, architect ruling) ·
Branch: `spec/coach-homepage` · Review: `.superpowers/sdd/coach-homepage/architecture-review.md`

## Why

First tester feedback (2026-10-07): the homepage has too much on it and the message is unclear;
the process reads as technical, not novice-friendly; tailoring itself works well. Search quality,
the third complaint, shipped 2026-10-08 (d99ff9c). The owner wants the product "easy and super
fun".

This serves the October validation gate: at least 6 of 10 testers finish a real resume, at least
3 return within 7 days. The coach exists to raise the first number. It is the only feature work
planned for October.

**Success:** a tester who has never seen Rhapto goes from the homepage to a downloaded, tailored
resume without leaving the coach and without meeting a technical screen. We can count, step by
step, where the ones who did not finish stopped.

## What the owner decided (brainstorm, 2026-10-07 and 2026-10-08)

1. Homepage is cut to: hero, one call to action, three steps, one before/after proof. Everything
   else moves to `/about`.
2. The coach is a scripted, chat-style wizard at `/start` (approach A). It tailors in tune mode,
   on the user's own document. Technical screens go behind "Advanced".
3. The coach leads with job recommendations derived from the resume: resume, then derived target
   role, then one-tap confirm, then the top 5 jobs. Pasting a job is the fallback.
4. Navigation becomes "Tailor a resume · My resumes · Feedback".
5. Measurement is by step events: counts only, read by the funnel script.
6. A user's first resume import is free. Later imports count against the trial as today.
7. A muted line under the hero button states the free limit (owner: keep it).

## What the code already gives us (verified 2026-10-08 by the architect review)

- `POST /api/v1/profile/import-resume` (`routers/profile.py:325`). It takes a .docx, makes one model
  call and returns a proposal: blocks, tracks filtered to the taxonomy, and location. It writes
  nothing except the trial claim. This is the role derivation; no new derivation code is needed.
- Saving a track (`PUT /profile/tracks/{id}`) queues `rescore_jobs`. It runs in the background
  under a per-user lock (if the lock is held, it re-enqueues after 30 s) and commits once, at the
  end. There is no measured duration.
- `GET /api/v1/jobs` supports `sort=fit`, `recommended=true` and `track=<id>`. The `track` filter
  is `Job.best_track_id == track` (`db/repositories/jobs.py:393`). `GET /jobs/empty-reason` shares
  the same filters.
- Tune mode: `POST /jobs/{job_id}/tailor` with `mode: "tune"` and a document stored via
  `POST /profile/resume-document` (.docx, 5 MB or smaller). A pasted job becomes a job through
  `POST /jobs`. `_tune_branch` reads only the document, `profile.answers` and `profile.guardrails`,
  never blocks.
- Trial: `RHAPTO_TRIAL_RUNS` (default 3) is a counter on `users`. The worker claims a run after
  loading the profile and before the first model call. Import-resume claims one synchronously
  (`profile.py:355`).

**Bugs found:**
- **No library, no tune run.** The worker calls `load_profile_from_db` (`worker/tasks.py:201`). It
  raises `ProfileError` when the user has no blocks or no tracks (`services/profile_sync.py:83-89`),
  so a tune run fails before the engine starts. The API returns 202 first. `tailor()` also looks up
  the track before branching (`engine/pipeline.py:172`), and `PATCH /packages/{id}` uses the same
  loader.
- **Unscored jobs count as recommended.** `recommended=true` keeps unscored jobs (`Job.best_fit IS NULL`,
  `jobs.py:295`), and a new account is backfilled with unscored public jobs at bootstrap. So
  "recommended, sorted by fit" returns jobs before any scoring has happened.

## Section 1 — Light homepage

`Landing.tsx` keeps only the following:

1. **Hero:**
   - Headline, a one-line subhead, and one primary call to action, "Tailor my resume", which goes
     to `/start`.
   - In hosted mode, "Request beta access" stays as a secondary text link under the button, so an
     uninvited visitor still has a way in. The token-mode (self-host) hero branch is unchanged.
   - One muted line states the free limit.
2. **Three steps:** "Upload your resume · Pick a job · Download your tailored resume". Text and
   icons only.
3. **One before/after proof:** a tune-mode catch. A sentence from the user's own document is shown
   with a number the model tried to add, and Rhapto stops it. It leads with `no-new-numbers`,
   which, like `tune-scope`, always runs in tune mode. `no-invented-entities` is user-configurable,
   so it is not the headline claim. Rule names are quoted exactly, as CaughtDemo does.
   - The current `CaughtDemo` shows the blocks-only rules (`provenance`, `no-unverified-metrics`),
     which tune mode skips (`engine/guardrails/tune.py:43`). It moves to `/about` unchanged, where
     it describes the full-profile path.
   - Below the proof, a "How it works in detail" link goes to `/about`.

`/about` currently renders the same `<Landing />` (`app/about/page.tsx:15`). A new
`components/landing/About.tsx` takes these sections in their current order, without content changes, except that its hosted "Sign in" calls to action become "Tailor my resume" → `/start` (owner decision 2026-10-09):

- ProductTour
- the feature-card grid
- JourneyWalkthrough
- CaughtDemo
- the pricing / "What it will not do" / "What you need first" cards
- "For developers & self-hosting"
- the closing call to action

The in-page anchors `#tour`, `#how` and `#honest` move with their sections. Links to `/#tour` and
the others are updated to `/about#…`. `Landing.test.tsx`, `app/page.test.tsx` and
`app/about/page.test.tsx` are updated to match.

## Section 2 — The coach at `/start`

A new route, `apps/web/src/app/start/`. One question per screen, with a chat-style transcript: past
steps stay visible above the current one, short and collapsed. Each step is its own component with
one job.

| # | Screen | What happens |
|---|---|---|
| 1 | "Upload your resume" (.docx) | The upload control is disabled while a request is in flight. **In sequence:** first `POST /resume-document`. If that fails, stop; nothing has been spent. Then `POST /import-resume`. If import fails, the document is already stored, so the user can paste a job. Event `resume_in`. |
| 2 | "Looks like you're aiming for: **{top proposed track}**. Right?" | One tap confirms. "Something else" shows the other proposed tracks plus a typeahead over the `GET /taxonomy` roles (names and titles). On confirm the coach saves **only that one track**, plus the location answers, merged into `answers` the same way `ImportResume` does. It saves **no blocks** (see below). Event `role_confirmed`. |
| 3 | "Finding your best matches…" | Polls `GET /api/v1/coach/readiness?track=<confirmed id>` and `GET /jobs?sort=fit&recommended=true&track=<confirmed id>` together. Rows are shown as they appear (scoring commits every 50 jobs, so early rows are partial), and polling continues until `ready` is true; the top 5 is final only then. After 60 s it offers "Paste a job you like instead" and keeps polling in the background. **Empty handling:** `/jobs/empty-reason` (same query) saying `no_jobs` is final at once: show that reason and the paste option. Otherwise an empty list is real only when `ready` is true: show "No strong matches for {role} yet", with "Paste a job" and "Show other jobs" (the same query without `track`). A rescore that raises entirely never marks ready; the 60 s paste offer covers it. |
| 4 | "Your top 5" | Five cards: title, company, a match label instead of a raw number, and "Tailor this one" (disabled on click). The label is "Strong match" at or above the track's `min_fit`, otherwise "Good match". Every row shown already clears the recommended floor. Before the copy is final, the thresholds are checked against the score spread on the scratch restore; scores cluster between 30 and 60, so with `min_fit` 60 almost nothing would read "Strong". The cards show the runs left when a trial applies. A "Paste a job instead" link is always visible. Event `jobs_shown`. |
| 5 | Tailoring | Tune-mode tailor with the existing progress steps. The task id goes in the URL (`?task=<id>`) so a reload re-attaches to `GET /tasks/{id}`. Event `tailor_started`. |
| 6 | "Your tailored resume" | The coach's own result screen: status in plain words, Download DOCX/PDF, a short "what changed" list (from the package's tune edits) and a "See full details" link to the existing package page. Event `downloaded` on download. If the package is blocked, see §3.5. |
| 7 | "Done. Try another?" | Back to step 4. |

`/start` fires `started` on first render. Every screen has a "Skip to the full app" link to
`/dashboard`.

**Why the coach saves no blocks.** Tune mode never reads the block library. Imported block ids are
model-chosen slugs, and `PUT /profile/blocks/{id}` is an upsert, so saving them could silently
replace a returning tester's verified blocks with unverified copies. That would strip their metrics
in blocks mode. The full import-and-confirm flow, `ImportResume` with `ConfirmMetrics`, stays under
Advanced → Profile. The coach uses its own small `saveCoachRole` helper, not
`ImportResume.handleAccept` (which writes every proposed track and every block). A track picked from
the taxonomy takes its keywords from the taxonomy and `resume_base` `imported-default`, as
ImportResume does. It uses the taxonomy's `min_fit` of 60. That value is written into the track, so
the label in step 4 follows it.

**Where the coach starts.** Server state decides; the URL step is only a hint, capped at the
furthest step that server state allows.

| Server state | Start at |
|---|---|
| A running task id in the URL | 5 (re-attach) |
| Stored document and at least one track | 4, using the coach's last confirmed track id (kept per user in `localStorage`), falling back to `tracks[0]`; the API's `Track` model has no `updated_at` |
| Stored document, no track, a cached import proposal | 2 |
| Stored document, no track, no cached proposal | 2, as the taxonomy role picker without a suggestion |
| No stored document | 1 |

The import proposal is cached in `sessionStorage`, keyed by user id. A reload between steps 1 and 2
then does not mean importing again and paying for it.

A returning tester (tracks and blocks, no stored document) starts at 1. Their upload becomes their
stored document, and step 2 suggests a role, which can be one they already have. A re-upload replaces
any stored document; the step 1 screen says so when one exists.

**Navigation (`components/shell/TopBar.tsx`):**
- The main tabs become "Tailor a resume" (`/start`), "My resumes" (`/resumes`) and "Feedback"
  (`/feedback`).
- An "Advanced" menu holds Dashboard, Jobs, Pipeline and Profile. It uses the two-row mobile
  treatment from PR #6.
- Settings and Help keep their icons.
- The logo links to `/start` in hosted mode and stays `/dashboard` in token mode.
- `TopBar.test.tsx` is updated to match.

## Section 3 — Backend changes, errors, measurement

### 3.1 Tune mode runs on a document alone (bug fix)

- `load_profile_from_db` gets a `require_library: bool = True` parameter. When it is False:
  - It returns answers and guardrails (falling back to `default_guardrails()`).
  - It returns whatever blocks and tracks exist, possibly none.
  - It does not raise on an empty library.
- The worker passes False for tune runs. The tune path of `PATCH /packages/{id}` passes False too.
  It currently loads the profile (`packages.py:390`) before computing `tune` (`:392`), so the
  check moves above the load.
- `tailor()` resolves the track only in the blocks branch. In tune mode it looks the track up
  leniently: it accepts no track, an unknown `track_id`, or a stale `job.best_track_id`.
- A tune package with no resolvable track records `track_id = ""`. This needs no migration, schema
  change or codegen: the column stays NOT NULL, and the JSON schema has no `minLength`. Two web
  changes go with it:
  - `RegenerateDialog` maps `""` to `null` before sending and hides its track picker when the user
    has no tracks.
  - The package page hides "track" when it is empty.
- **The blocks-mode guard is the API's job.** `tailor.py` first resolves the mode
  (`body.mode or ("tune" if has_document else "blocks")`). If the mode is blocks and the user has no
  blocks or no tracks, it returns a 422 with a plain message. The check sits with the other
  validation 422s, before the key check (the house order), instead of returning a 202 that fails
  later.
- `test_no_key_anywhere_is_still_llm_not_configured` moves to the `imported_profile` fixture. Its
  intent, the ordering of the key checks, is unchanged. Every other blocks-mode tailor test posted
  without a profile is found and fixed the same way: `test_tailor_api.py`,
  `test_fake_provider_api.py`, `test_packages_api.py`, and `conftest.py:249`.

**Guardrails stay unconditional.** Tune mode has its own document-based rules (`no-new-numbers`,
`no-invented-entities`, and the rest of `engine/guardrails/tune.py`). They stand in for provenance
and no-unverified-metrics, which are block rules with nothing to check when there is no block
selection. A tune package whose report fails still persists no DOCX. Nothing in this design adds a
switch to any rule.

### 3.2 First import free

- A new nullable column, `users.free_import_used_at`, in Alembic migration 0014.
- In `import-resume` only:
  1. `limit = await trial_limit_for(...)`.
  2. If `limit is None` (own key, fake provider, or cap disabled), make no claim and leave the
     column untouched.
  3. If `limit == 0`, refuse as today.
  4. If `limit > 0`, run the new repository function `claim_free_import`:
     `UPDATE users SET free_import_used_at = now() WHERE id = :uid AND free_import_used_at IS NULL RETURNING id`.
     If no row comes back, fall through to `claim_trial_run` as today.
  5. Commit before the model call, as now.
- Existing users start with the column empty, so each gets one free import even if they have
  imported before. That is accepted.
- `test_importing_a_resume_consumes_exactly_one_run` and
  `test_importing_a_resume_past_the_limit_is_refused_without_a_model_call` change to "the second
  import consumes one run" and "past the limit, after the free one".

### 3.3 Scoring readiness (plan-review C1, architect ruling)

Rescoring commits every `SCORE_CHUNK` (50) jobs (`services/scoring.py:182-218`), so the presence of
any score is not a completion signal, and `tracks.updated_at` cannot serve either: it changes on
every ORM update, including the rescore's own embedding writes (`db/base.py:22-24`).

- Migration 0014 adds `tracks.score_requested_at timestamptz NOT NULL DEFAULT now()` and
  `tracks.scored_at timestamptz NULL`.
- Only `upsert_track` writes `score_requested_at = now()` (covers `PUT /profile/tracks/{id}` and
  profile replace).
- `rescore_user` reads `started` from the database's `now()` before loading tracks; after
  `score_and_store` returns it sets `scored_at = started` with one Core UPDATE on exactly the track
  ids it loaded. A rescore that started before the latest save can never mark that save ready.
- Ready means `scored_at IS NOT NULL AND scored_at >= score_requested_at`.
- `GET /api/v1/coach/readiness?track=<id>` returns `{ready: bool}`, scoped to the current user;
  404 for an unknown or another user's track.
- Tests: a real multi-chunk rescore (`SCORE_CHUNK` patched small) is not ready after chunk 1 and
  ready at the end; the stale-start race; an embedding-only write leaves readiness unchanged; the
  cross-user 404.

### 3.4 Step events

- A new table in migration 0014: `coach_events (id, user_id, step, day, created_at)`.
  - `user_id` is a foreign key with `ON DELETE CASCADE`, indexed (as in 0013).
  - `day date NOT NULL DEFAULT (now() AT TIME ZONE 'UTC')::date`, so "day" means the UTC day.
  - `step` has a CHECK for `started | resume_in | role_confirmed | jobs_shown | tailor_started | downloaded`.
  - `UNIQUE (user_id, step, day)`.
- A new endpoint, `POST /api/v1/coach/events {step}`:
  - It is authenticated through `current_user`, and returns 204.
  - `step` is a Python `Literal` that mirrors the CHECK, so a typo returns 422, not 500.
  - It inserts with `ON CONFLICT DO NOTHING`.
- The web client fires the event and forgets it; a failed event never blocks the coach.
- Counts only: no resume text, job text or scores.
- The funnel script (October plan, item 2) reads this table. It is an operator tool, never an API.
- The migration downgrade drops the column and all coach events; the docstring says so.

### 3.5 Errors (plain words, always one way forward)

| Case | Message direction | Way forward |
|---|---|---|
| Not a .docx, or larger than 5 MB | "Rhapto reads Word (.docx) files up to 5 MB. In Word or Google Docs, use Save as / Download as .docx" | Re-upload |
| Import fails (422) | "We couldn't read the roles in this resume" | Taxonomy role picker, or paste a job (the document is stored, so tune works) |
| Import proposes no track in the taxonomy | "What role are you aiming for?" | Taxonomy role picker |
| Not on the allowlist (403 after sign-in) | "Rhapto is invite-only right now" | Request-access link |
| Trial used up (409) | Existing trial sentence | Settings → add your own key |
| No model key (409) | "Rhapto isn't set up to tailor yet" | Feedback link |
| Tailor waiting in the queue | "Still working, others are ahead of you" | Wait (the worker runs 2 jobs at a time) |
| Tailor task fails | The task's reason | Retry; no run is consumed when the failure comes before the claim |
| **Package blocked by a guardrail** | "Rhapto stopped this draft because it added something that isn't in your resume" | Try again (a fresh tune run on the same job, **without** `parent_package_id`, so the model never sees the blocked edit; owner decision 2026-10-09; this costs a run, and the screen says so), or pick another job |
| No matches after scoring | Reason from `/jobs/empty-reason` | Paste a job |

## Testing

- **API (pytest, GitHub Actions CI; no local Docker):**
  - A tune tailor completes for a user with a document and (a) no tracks, (b) no blocks and no
    tracks, (c) a `best_track_id` naming a deleted track. A tune PATCH works for (b).
  - A package with `track_id ""` round-trips through `package_row_to_model`, a tune PATCH and a
    regenerate.
  - A blocks-mode tailor without blocks or tracks returns 422, with resolved-mode coverage
    (no `mode` in the body, no document).
  - First import is free, then counted. Own-key and cap-disabled users are untouched. With a cap of
    0, import is refused. Two concurrent imports give exactly one free.
  - Event endpoint: validation, auth, idempotence and the 204 on conflict.
  - Migration 0014 round-trip on a scratch database (`test_migrations_0014.py`).
- **Web (vitest + Testing Library):**
  - Each step component, including every §3.5 row.
  - The start-step derivation table.
  - The upload order, and a document failure stopping before import.
  - The double-click guards.
  - TopBar tabs, the Advanced menu, and the logo per mode.
  - Landing has exactly hero, steps and proof; `/about` has the moved sections and anchors.
  - RegenerateDialog with `""`.
- **Timing check (plan task, before UI copy is final):** time `rescore_user` on the scratch restore
  of a ~2.5k-job account, and set the step 3 wait from it. 60 s is the placeholder.
- **End to end:** one Playwright run on prod with a test account after deploy, from the homepage to
  a downloaded resume. Screenshots of every step go to the owner early, before the final gate.

## Out of scope

- The funnel script itself (a separate item).
- Changing the import model or prompt.
- Making Jobs, Pipeline or Profile novice-friendly; they sit behind Advanced.
- Saving imported blocks from the coach.
- Payments, interview prep, and any new job source.

## Delivery

Full pipeline: functional architect → architect → senior dev → coder → QA → final manager →
delivery. Executed with subagent-driven development. Owner gates: this spec, then the deploy OK.
Migration 0014 is additive and runs at deploy time. The nightly-backup action item should land
before the deploy.
