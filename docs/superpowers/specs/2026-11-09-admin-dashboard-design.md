# Admin dashboard: design

Status: draft for builder check, then owner approval. Then the delivery pipeline (architect, plan, code, QA, final review, delivery).

## Why

Open sign-up went live on 2026-11-08 with 3 lifetime free runs per account and a $50 app-wide monthly budget. The launch is about to put strangers on the owner's key. Today every answer ("how much is spent", "why did this person's run fail", "reset this account") needs SQL over ssh. The owner wants one page where they can see how the site is doing and fix user problems without asking for a command.

Success: during launch week the owner opens one page, sees what needs attention, and resolves a user's complaint without ssh.

## Who

One person: the owner. There are no admin roles and no team features.

## Decided by the owner

- A general admin dashboard, "similar to other websites", where issues with the site and its users can be solved.
- Three user fixes: **reset free runs**, **block a user**, **see their failed runs**.
- The mockup layout (`.superpowers/brainstorm/*/content/admin-layout-v2.html`): overview numbers, "Needs your attention", searchable user list, one page per user.
- Same theme as the rest of Rhapto.
- The intelligence is **rules-based**. No LLM calls.

## Goals

**Overview (`/admin`)**
- Sign-ups: total and today.
- Free spend this UTC month against `RHAPTO_MONTHLY_FREE_BUDGET_USD`, read from `free_spend`.
- Sign-in limit: account count against 50, labelled as an estimate. The real seat count lives in Cloudflare.
- "Want more resumes": distinct users whose quick feedback text starts with `Wants more resumes` (the constant `WANT_MORE_RUNS_TEXT` in the web app).
- Failed runs in the last 7 days.

**Needs your attention**, each item computed by a deterministic rule and shown only when it fires:

| Alert | Rule |
|---|---|
| Budget runs out early | Average daily `free_spend` over the last 3 days, projected forward, reaches the budget before the 1st of next month. Shows the projected date. |
| Accounts that look like one person | Two or more accounts whose address is identical after removing the `+tag` from the local part. |
| Failed runs jumped | Today's failed tailor tasks are at least 5 and at least 3 times the daily average of the prior 7 days. Shows the most common failure category. |
| Ready to be asked about paying | Users with no runs left who also asked for more. Shows the count against the owner's trigger of 10 people paying or 30 asking. |
| Sign-in limit close | Account count at or above 40 of 50. |

**Users**
- Search by email; a paged list with runs used, failed count, last seen, status.
- User page: joined date, runs used, free spend, whether they asked for more, failed runs (when, type, plain reason), admin action history.
- **Reset free runs:** sets `trial_runs_used` to a value the owner chooses, 0 to the current value. Never raises it. A failed run consumes a run with no refund path by design (`services/trial.py`), so this is the intended remedy.
- **Suggested fix** on the user page: when the user has failed tailor runs and no runs left, suggest resetting that many runs. It is a suggestion; the owner clicks.
- **Block / unblock:** a blocked account gets a plain "this account has been blocked" response on every API request and cannot start runs.
- Every reset, block and unblock is written to an append-only history with who, when, what and the before and after values.

## Non-goals

- Payments, credit packs or plans.
- Editing a user's profile, resumes or settings, and viewing their resume, profile or job content. Support needs the failure, not the person's documents.
- Impersonating a user.
- Deleting accounts.
- Managing Cloudflare seats, or calling the Cloudflare API.
- Multiple admins or roles.
- Charts beyond the progress bars in the mockup.
- Emails or push alerts.
- Any AI call.

## Anti-goals (failure even if it works)

- Anyone but the owner can read the page or call its API. Hiding a link is not access control.
- Admin routes leak addresses or stored keys into logs, error bodies or URLs.
- A provider's raw error text, an exception, or a user's resume content reaches the admin screen.
- A blocked user keeps spending the owner's key.
- Any code path that submits an application (CLAUDE.md rule 1).
- An alert that claims more than the data supports. Estimates say they are estimates.

## Constraints

- Authorisation is on the server, on every admin route: the signed-in principal's email must be in a new `RHAPTO_ADMIN_EMAILS` setting, in access mode only. Anyone else gets 404, so the area does not reveal itself. Empty means no admin area. The app-side `RHAPTO_OPEN_SIGNUP` flag has no bearing on it.
- This reverses a stated boundary: `routers/feedback.py` and `repositories/feedback.py` record that no cross-user read is reachable under `rhapto.api`. The architect must rule on how admin reads are isolated from user-scoped code, and those comments must be updated to stay true.
- Block check belongs in `current_user` (`api/deps.py`), which every endpoint depends on and which must stay fast; `ensure_account` already loads the row. Admins cannot block themselves.
- Schema: one migration after `0015`, adding `users.blocked_at` and an `admin_actions` table. It needs the backup and owner approval at delivery.
- `tasks.error` is not safe to show verbatim; failures are shown as plain categories, reusing the sentence allowlist approach in `apps/web/src/lib/coach/errors.ts`.
- Must work at phone width with the existing tokens in `apps/web/src/app/globals.css`.
- Must be protected from cross-site request forgery on the state-changing routes to the same standard as the rest of the API.

## Delivered by whoever builds it (builder's call)

- Route and component structure, pagination size, query shape, and how the 5 alerts are tested. Each alert needs a test on known-bad data and on data that must not fire.
- Whether the sidebar shows an Admin link to the owner.

## Settled after the builder check (Claude's calls)

- **Blocked users' work in progress.** The block is also checked in the worker just before a tailor task claims a free run, and that task fails with a plain message. A model call already under way finishes. Queued work therefore stops spending; at most one call per running task does not.
- **Failed runs.** A failed run is a task with `status = 'failed'`. Failed-run counts and alerts use `tailor_job` tasks only. `tasks` does not record whether a failure consumed a run (the claim comes after the job, profile and document checks in `worker/tasks.py`), so the suggested fix says "up to N" and the owner decides.
- **Failure categories.** Classify `tasks.error` by matching known sentences and patterns; anything unmatched shows as "Other (see server logs)". No new column on `tasks`.
- **Retention.** The architect must check whether tasks are pruned and state the effect on the 7-day counts and user history.
- **Cross-site requests.** Admin state-changing routes reject a request whose `Origin` does not match the site. The API has no such check today, so this is explicit rather than inherited.
- **Token mode.** No admin area and no block enforcement; it is single-user.
- **Duplicate-account rule.** Removes `+tag` and ignores case. It does not remove Gmail dots, to limit false alarms.
- **Admin email match.** Uses the same case-insensitive comparison as `is_allowed_email`.

## Calls made by Claude, for the owner to check

- Only the owner's account can open it, listed in `RHAPTO_ADMIN_EMAILS`.
- Non-admins see "not found".
- Blocking takes effect on the next request.
- The thresholds in the alert table (3-day pace, 5 failures and 3 times, 40 of 50).
- No viewing of resumes or profile content.
- Reset can only lower the runs used.
