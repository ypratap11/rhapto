# Market-wide job search ("job portal") — design

Date: 2026-09-14. Status: approved in chat; plan to follow. Builds on main after the Workday source (efcce65) and
the location-priority branch (in progress; this spec assumes `jobs.location_tier` and the `region` filter).

## 1. Goal

Make Rhapto feel like a job portal driven by the user's own criteria: jobs from the whole market arrive from
saved searches, company boards are discovered automatically, and every job enters the existing Find → Tailor →
Review → Apply flow. The user's stated aim: easy to search, then the same tailor-review-apply flow.

## 2. Non-goals

Scraping LinkedIn, Indeed or Glassdoor pages; submitting applications (never; a human clicks Apply on the
employer's site); ranking changes beyond the existing fit score and location tiers; paid sources beyond an
optional key the user supplies.

## 3. Sources

Two tiers, both implemented as `aggregator` sources in the existing registry
(`services/discovery/sources`, `SourceInfo(kind="aggregator")`), each taking a `SearchSpec` instead of a bare
keyword list:

- Zero-setup (enabled by default): `themuse` (public API, `https://www.themuse.com/api/public/jobs`, location
  and category aware, US coverage), `remotive` (`https://remotive.com/api/remote-jobs?search=`), plus the
  existing `remoteok` and `hn-hiring`.
- Keyed (disabled until a key is saved): `adzuna` (`api.adzuna.com/v1/api/jobs/us/search/{page}` with
  `app_id`+`app_key`), `jooble` (`https://jooble.org/api/{key}`, POST), `jsearch` (RapidAPI
  `jsearch.p.rapidapi.com/search`, header key; Google Jobs data covering LinkedIn/Indeed/Glassdoor listings).

Each source maps results to the existing `Posting` (external id = the source's own id, `url` = the apply or
posting URL, `jd_text` from the description, `posted_at` when given). Per search per source cap: 100 results
(paging stops early). Sources that return HTML descriptions go through `html_to_text`.

The on/off flag stays on the existing per-user aggregator rows; credentials live in a new `source_credentials`
table (user_id, source, credentials_encrypted with the same Fernet secret as LLM keys). `GET/PUT
/api/v1/settings/sources` lists every registered aggregator with `enabled`, `needs_key`, `key_set`, and the
per-source `fields` (Adzuna needs two values). Keys never leave the server.

## 4. Saved searches

`searches` table: id, user_id, name, keywords (list of phrases, OR-ed), location (free text, may be empty),
remote ("include" | "only" | "exclude"), active bool, derived_from_track_id (nullable), timestamps.

Derivation: on first poll (or when the Searches tab is opened and no searches exist) one search per track is
created: name = the track name, keywords = the track's keywords (first six), location = the user's
`location_home` answer's metro (the first preferred keyword when set, else the home string), remote =
"include" when `remote_ok` is yes. Derived searches carry `derived_from_track_id`; editing them clears it.

Poll: for every active search and every enabled aggregator, `fetch(http, spec)` runs; results are ingested by
the existing dedupe (`identity_hash`) and scored like any job. `jobs` gains `search_id` (nullable) and
`source` already exists; the poll run summary reports per-source found/new. Discovery of a search's results
stops at the cap; searches are polled in the user's order.

## 5. Auto-discovered company boards

After ingest, every new job's URL is matched against the ATS patterns: `boards.greenhouse.io/<slug>`,
`job-boards.greenhouse.io/<slug>`, `jobs.lever.co/<slug>`, `jobs.ashbyhq.com/<slug>`,
`<prefix>.myworkdayjobs.com/<lang>/<site>` (also `/wday/cxs/<tenant>/<site>`). A match not already on the
watchlist adds a row `{company, source, board, keywords: <the search's keywords>, discovered: true}`. The
watchlist schema gains `discovered` (bool, default false); the Watchlist tab shows a "discovered" chip and lets
the user remove or keep the row. Discovered rows are polled like any other from the next run.

## 6. Applying

Applying stays the existing guided flow: Find (Jobs, Next up) → Tailor → Review (downloads, Open posting) →
Apply (Mark applied, Pipeline). The portal work only feeds that flow with more and better-ranked jobs; no new
apply mechanism is added and nothing is ever submitted by Rhapto.

## 7. UI

- Jobs page: a **Source** chip (The Muse, Remotive, Adzuna, ...) and, when present, "via <search name>" on
  each card; the region filter (from location priority) defaults to "US and remote".
- Profile → **Searches** tab: table of searches (name, keywords, location, remote, active, derived), add /
  edit / pause / delete; a "Derive from tracks" button when none exist.
- Settings → **Job sources**: one row per aggregator with an on/off switch, key fields for keyed sources
  (masked, never echoed), and a "Test" button that runs a one-result search.
- Runs drawer lists the new sources with per-search counts.

## 8. Testing

Per-source unit tests with fixture responses (mapping, caps, keyless vs keyed, error → `SourceError`);
`SearchSpec` derivation from tracks and answers; board auto-discovery from each URL pattern and non-matches;
dedupe across two sources returning the same posting; source settings API (enable/disable, key never
returned, test endpoint both outcomes); searches API CRUD; poller integration with the fake HTTP client; web:
Searches tab, Job sources settings, source chips. No network in tests.

## 9. Constraints carried over

Never submit an application; nothing personal or no keys in the repo; secrets via `.env` or encrypted rows;
engine purity; services never import worker/api/cli; SSRF checks on every outbound request; max 3 LLM calls per
tailoring run (unchanged; discovery makes no LLM calls).
