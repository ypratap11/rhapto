# Shared job pool and self-service accounts — design

Date: 2026-09-24. Status: approved in chat; plan to follow. Builds on `main` at `e99e9df`
(relevance sort, field filter, ATS headings, Groq provider, landing page).

## 1. Goal

Let more than one person use one Rhapto instance, each with their own profile, tracks, resumes and
pipeline — and let them sign themselves up rather than being added by hand.

Two changes, in this order:

1. **The job pool becomes shared.** A posting is stored once and seen by everyone; everything
   derived from it stays per-user.
2. **Identity comes from Cloudflare Access**, and first sign-in creates the account.

## 2. Why now, and why the pool first

The data layer is already multi-tenant. Verified on 2026-09-23 against the live database: every
table carries `user_id`; every repository filters on it (jobs 16 filters, packages 7, applications
4, searches 6); job dedupe is the partial unique index `uq_jobs_user_source_external (user_id,
source, external_id)`; `packages/{id}/files/{name}` calls `_get_package(session, user_id,
package_id)` before touching disk; `poll_all_sources` already loops `for user_id in await
list_user_ids(session)`; `get_or_create_user(session, email)` already exists. The single
single-tenant seam is `current_user` in `api/deps.py:74`.

So accounts are a small change. The pool is not — and **the pool must come first**, because there
is currently exactly one user. Migrating 1,430 rows into a shared pool today is a relabel. Once
three people each hold their own copy of the same Lever posting, the same migration has to *merge*
duplicates: match on `identity_hash`, reconcile conflicting `unlisted_at`, decide whose
`discovered_at` wins, and repoint every package and application. Same change, several times harder,
and harder again with every user added.

## 3. What sharing buys

Storage is the least of it.

- **`extracted_json` is an LLM call.** It is produced on first tailor and cached on the job row.
  Per-user rows mean ten people looking at the same posting pay for ten extractions; shared, the
  first tailor pays and everyone benefits.
- **`jd_embedding` is computed once.** Fit scoring is 0.6 embeddings, so the expensive half stops
  being per-user and only the cheap cosine-and-keyword pass repeats.
- **Polling collapses.** Today a single user's poll takes 309 seconds. Shared, the union of
  everyone's boards and searches is polled once instead of once per user, and keyless aggregators
  (The Muse, Remotive, RemoteOK, HN) see one caller rather than N from the same IP.
- **The cold start disappears.** A new user currently signs in to an empty app and waits for a
  first poll. With a pool they see the full corpus immediately, ranked against their own tracks.
  Spec `2026-09-22-first-run-onboarding-design.md` names silence and empty screens as the dominant
  failure mode; this removes the worst instance of it.

## 4. Design — the pool

### 4.1 Column split

`jobs` today carries 27 columns. They divide cleanly.

**Shared (the posting as the employer published it):** `source`, `external_id`, `company`, `title`,
`location`, `url`, `jd_text`, `jd_embedding`, `extracted_json`, `dedupe_hash`, `identity_hash`,
`posted_at`, `salary_text`, `repost_of`, `unlisted_at`, `miss_count`, `discovered_at` (when the
pool first saw it).

**Per-user:** `best_fit`, `best_track_id`, `location_tier`, `search_id`, `hidden_at`, `rescued`.

Only six columns move. `job_scores` already holds what most of them represent — `fit_score`,
`track_id`, and `location_tier` inside `rationale_json`.

### 4.2 Tables

`jobs` keeps its primary key and loses `user_id`, gaining:

- `owner_user_id UUID NULL` — `NULL` means pool; set means private to that user.

`user_jobs` is new and **sparse**: a row exists only when a user has state for that job.

```
user_jobs(user_id, job_id, hidden_at, rescued, search_id, first_seen_at)
  primary key (user_id, job_id)
```

Most jobs need no row. The list query becomes
`jobs LEFT JOIN user_jobs LEFT JOIN job_scores`.

`job_scores` is unchanged: it already keys on `(user_id, job_id, track_id)`.

### 4.3 Privacy boundary

`source = 'manual'` marks a hand-pasted JD (4 exist today, including one pasted from a Google
careers page). A recruiter email or an unlisted posting must never become visible to other users,
so **manual jobs get `owner_user_id` set and never enter the pool.** Everything discovered from a
public board or aggregator has `owner_user_id IS NULL`.

The dedupe index changes accordingly: `(source, external_id)` for pool rows, and the per-user
uniqueness for owned rows. Postgres partial unique indexes express both.

### 4.4 `best_fit` is the real work

`best_fit` and `best_track_id` are denormalised onto the job row by `services/scoring.py:77-84`,
and read in eight modules — every sort, `bucket`, `min_fit` and `track` filter depends on them.
They are per-user, so they move to the per-user side.

This is the bulk of the change: the schema edit is small, the query rewrite is not. Both become
derived from `job_scores` for the requesting user, materialised into `user_jobs` on scoring so the
list query stays a join rather than an aggregate.

### 4.5 Polling and scoring

Polling reads the union of every user's watchlist and saved searches, polls each board once, and
writes into the pool. Attribution stays per-user: when a user's saved search surfaced a posting,
that user gets a `user_jobs` row carrying `search_id`.

Scoring stays per-user and runs after a poll for every user whose tracks could match. A new account
triggers a backfill over the existing pool — no LLM calls, shared embeddings, so it is cheap — and
that backfill is what makes their first screen useful.

`unlisted_at` and `miss_count` become genuinely global: a dead posting is dead for everyone.
Reconciliation must therefore key off the board poll, not off a user.

## 5. Design — accounts

`RHAPTO_AUTH_MODE` = `token` (default; self-hosters keep today's behaviour exactly) or
`cloudflare_access`.

In `cloudflare_access` mode, `current_user` verifies the `Cf-Access-Jwt-Assertion` header against
the team JWKS at `https://<team>.cloudflareaccess.com/cdn-cgi/access/certs` — signature, `aud` and
expiry — and calls `get_or_create_user` with the verified email.

**Verify the JWT; do not read `Cf-Access-Authenticated-User-Email`.** The plaintext header is only
trustworthy while the origin has no public port, and that is one firewall change away from an
authentication bypass. The signature check removes the dependency entirely.

New config: `RHAPTO_ACCESS_TEAM_DOMAIN`, `RHAPTO_ACCESS_AUD`. JWKS is cached with a TTL, and the
last good key set is retained so a Cloudflare outage does not fail every request closed.

**Signup is self-service.** The Access policy allows any account authenticated by the configured
identity provider rather than an email allowlist, and first sign-in creates the row. There is no
signup form, no password, no reset flow, and no manual step for the operator.

The web app reads the mode from the API and, in `cloudflare_access` mode, `TokenGate` stops
demanding a bearer token — otherwise every user would need the instance's shared secret.

### 5.1 The bootstrap trap

`app.py`'s lifespan calls `get_or_create_user(settings.rhapto_user_email)` unconditionally. In
access mode that mints an unused row, and changing `RHAPTO_USER_EMAIL` later silently creates a
*second* account whose data appears to vanish — exactly the trap the 2026-09-23 migration hit. The
bootstrap must run only in `token` mode.

## 6. Migration (0010)

One-way, and safe only because there is a single user today:

1. Create `user_jobs`; create `owner_user_id` on `jobs`.
2. For every existing job: insert a `user_jobs` row carrying `hidden_at`, `rescued`, `search_id`
   and the current `best_fit` / `best_track_id`; set `owner_user_id` to the existing `user_id`
   where `source = 'manual'`, else `NULL`.
3. Drop the six per-user columns and `jobs.user_id`; replace the dedupe index.

`jobs.location_tier` is dropped rather than moved — it is already recomputed per user into
`job_scores.rationale_json` on every score.

## 7. Non-goals

- Rate limiting and abuse controls. Named in §8 as required before public signup, specified
  separately.
- Account deletion and data export. Required before this is offered widely; not in this spec.
- Sharing anything derived from a user — profile, blocks, tracks, packages, applications and scores
  all stay strictly per-user.
- Changing the guardrail contract. Untouched.

## 8. Known risks

- **Open signup is open.** Anyone who can authenticate creates an account and consumes polling,
  scoring and storage. Access policy membership stops being the user list, so rate limits and a
  per-user job cap become load-bearing rather than optional.
- **Backups now contain other people's resumes**, and there is no deletion path yet.
- **`DISCOVERY_CHANNEL = "discovery"` is global.** Nothing subscribes today, so it is latent, but it
  must become per-user before anything does.
- **The cron polls users serially** and one user already takes 309 seconds. Sharing the poll fixes
  the fetch, not the per-user scoring pass.
- **The box is small**: 2 vCPU, 3.9 GB, worker resident at 1.87 GB. A handful of active users is the
  ceiling regardless of this design.
- **A new user has no LLM key**, so every tailor fails until they add one. The onboarding checklist
  must catch it.
- **Location preferences are unset by default**, which silently multiplies every score by 0.85–0.9.
  Found on 2026-09-23; it cost this instance 99 of its 122 matches. New users must be prompted.

## 9. Phasing

- **Phase 1 — the pool.** Migration 0010, `user_jobs`, the `best_fit` query rewrite, poll and score
  paths, privacy boundary for manual jobs. Ships alone: single-user behaviour is unchanged.
- **Phase 2 — accounts.** `RHAPTO_AUTH_MODE`, JWT verification, get-or-create, bootstrap fix, web
  passthrough, per-user discovery channel.
- **Phase 3 — safe to invite.** Rate limits, per-user caps, onboarding for key and location,
  deletion path.

Phase 1 is a refactor with one user in the system, so a scoping mistake cannot leak one person's
data to another. That ordering is deliberate and is the main safety property of this plan.
