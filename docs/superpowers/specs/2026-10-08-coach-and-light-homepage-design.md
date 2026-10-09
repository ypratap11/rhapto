# Coach (/start) and light homepage — design

Date: 2026-10-08 · Status: draft for owner review · Branch: `spec/coach-homepage`

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

## What the code already gives us (verified 2026-10-08)

- `POST /api/v1/profile/import-resume` (`routers/profile.py:325`). It takes a .docx, makes one model
  call and returns a proposal: blocks, tracks filtered to the taxonomy, and location. It writes
  nothing. This is the role derivation; no new derivation code is needed.
- Saving a track (`PUT /profile/tracks/{id}`) queues `rescore_jobs`, which runs in the background
  under a per-user lock. There is no measured duration.
- Top jobs come from `GET /api/v1/jobs?sort=fit&recommended=true`. The empty-list reason comes
  from `GET /jobs/empty-reason`.
- Tune mode: `POST /jobs/{job_id}/tailor` with `mode: "tune"` and a document stored via
  `POST /profile/resume-document` (.docx, 5 MB or smaller). A pasted job becomes a job through
  `POST /jobs`.
- Trial: `RHAPTO_TRIAL_RUNS` (default 3) is a counter on `users`. The worker claims a run before
  the first model call, after the profile has loaded. Import-resume claims one synchronously
  (`profile.py:355`).

**Bug found.** `tailor()` calls `profile.get_track(request.track_id)` before branching into tune
(`engine/pipeline.py:172`). A user with no tracks gets a 202 from the API, then a task that fails
in the worker with "profile has no tracks". In tune mode the track is used only to stamp
`track_id` on the package (`pipeline.py:136`).

## Section 1 — Light homepage

`apps/web/src/components/landing/Landing.tsx` keeps:

1. **Hero:** headline, one-line subhead, and one primary call to action, "Tailor my resume",
   which goes to `/start`. The second call to action (to `/settings`) is removed. Below the
   button, one muted line states the free limit so the trial cap is never a surprise.
2. **Three steps:** "Upload your resume · Pick a job · Download your tailored resume". Text and
   icons only.
3. **One before/after proof:** the existing `CaughtDemo` component, unchanged.

ProductTour, the feature-card grid, JourneyWalkthrough, the pricing / "What it will not do" /
"What you need first" cards and the closing call to action move to `/about`, in that order and
without content changes. Their existing tests move with them. A small "How it works in detail"
link under the proof points to `/about`.

Signed-out visitors who click the call to action reach Cloudflare Access as they do today, then
land on `/start`.

## Section 2 — The coach at `/start`

A new route, `apps/web/src/app/start/`. One question per screen, with a chat-style transcript:
past steps stay visible above the current one, short and collapsed. Each step is its own component
with one job. The coach holds state in the URL step plus server data, so a page reload resumes
at the right step. It derives that from the server: stored document, saved track, packages.

| # | Screen | What happens |
|---|---|---|
| 1 | "Upload your resume" (.docx) | The one file is sent to `import-resume` and to `resume-document`, so the user uploads once. Event `resume_in`. |
| 2 | "Looks like you're aiming for: **{top proposed track}**. Right?" | One tap confirms. "Something else" shows the other proposed tracks plus free text matched to the taxonomy. On confirm the coach saves the track and the imported blocks through the existing endpoints, as `ImportResume.tsx` does today. Event `role_confirmed`. |
| 3 | "Finding your best matches…" | Polls `GET /jobs?sort=fit&recommended=true` until results appear. After 60 s it offers "Paste a job you like instead". If there are no results it shows the plain reason from `/jobs/empty-reason` and the paste option. |
| 4 | "Your top 5" | Five cards: title, company, fit score, "Tailor this one". A "Paste a job instead" link is always visible. Event `jobs_shown`. |
| 5 | Tailoring | Tune-mode tailor with the existing progress steps, then the existing review and download. Events `tailor_started`, `downloaded`. |
| 6 | "Done. Try another?" | Back to step 4. |

Every screen has a "Skip to the full app" link to `/dashboard`.

**Returning users.** A user who already has a stored document and a saved track starts at
step 4. A user with packages still sees `/start` from "Tailor a resume" and starts at step 4.

**Navigation (`components/shell/TopBar.tsx`).** The main tabs become "Tailor a resume" (`/start`),
"My resumes" (`/resumes`) and "Feedback" (`/feedback`). An "Advanced" menu holds Dashboard, Jobs,
Pipeline and Profile. Settings and Help keep their icons. The Rhapto logo links to `/start`.

## Section 3 — Backend changes, errors, measurement

### 3.1 Tune mode without a track (bug fix)

When `request.mode == "tune"`, `tailor()` does not require a track. If the profile has tracks it
uses the requested or default track as now. If it has none, the package's `track_id` is recorded
as empty. The API also stops accepting a blocks-mode tailor from a user with no tracks: it returns
a 422 with a plain message instead of a 202 that fails later.

Plan-time check: whether `ApplicationPackage.track_id` and its DB column can be empty, and every
reader of `track_id`. If making it nullable is wider than the engine and package model, record
the coach's saved track instead. The coach always saves one before step 4 anyway.

### 3.2 First import free

A new nullable column, `users.free_import_used_at`, in Alembic migration 0014. In `import-resume`,
if the column is empty, set it and skip `consume_trial_run`; otherwise claim a run as today. Both
paths commit before the model call, as now. Users with their own key, or with the cap disabled,
are unaffected: they never consume runs.

### 3.3 Step events

A new table, `coach_events (id, user_id, step, created_at)`, in the same migration. `step` is
checked against `started | resume_in | role_confirmed | jobs_shown | tailor_started | downloaded`.
A new endpoint, `POST /api/v1/coach/events {step}`, is authenticated, returns 204 and is
idempotent per (user, step, day). The web client fires it and forgets; a failed event never blocks
the coach. Counts only: no resume text, job text or scores. The funnel script (October plan, item
2) reads this table.

### 3.4 Errors (plain words, always one way forward)

| Case | Message direction | Way forward |
|---|---|---|
| Not a .docx, or larger than 5 MB | "Rhapto reads Word (.docx) files up to 5 MB" | Re-upload |
| Import fails (422) | "We couldn't read this resume" | Re-upload, or paste a job (tune still needs the stored document) |
| Import proposes no track in the taxonomy | "What role are you aiming for?" | Free-text role step |
| Trial used up (409) | Existing trial sentence | Link to Settings → add your own key |
| No model key (409) | "Rhapto isn't set up to tailor yet" | Feedback link |
| Tailor task fails | The task's reason | Retry; the run is not consumed when failure is before the claim |
| No matches after scoring | Reason from `/jobs/empty-reason` | Paste a job |

## Testing

- **API (pytest, GitHub Actions CI; no local Docker):** first import free, then counted; own-key
  user unaffected; tune tailor for a user with no tracks completes; blocks-mode tailor with no
  tracks returns 422; event endpoint validation, auth and idempotence; migration up and down.
- **Web (vitest + Testing Library):** each step component, including error and empty states;
  resume-at-step logic from server state; TopBar tabs and Advanced menu; Landing has exactly hero,
  steps and proof; `/about` contains the moved sections.
- **End to end:** one Playwright run on prod with a test account after deploy. It goes from the
  homepage to a downloaded resume. Screenshots of every step go to the owner early, before the
  final gate.

## Out of scope

The funnel script itself (separate item). Changing the import model or prompt. Making Jobs,
Pipeline or Profile novice-friendly; they sit behind Advanced. Payments. Interview prep. Any new
job source.

## Delivery

Full pipeline (functional architect → architect → senior dev → coder → QA → final manager →
delivery), executed with subagent-driven development. Owner gates: this spec, then the deploy OK.
