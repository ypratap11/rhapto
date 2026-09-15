# Market-Wide Job Search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jobs from the whole market arrive from the user's saved searches across keyless and keyed aggregator APIs, company boards found in results join the watchlist automatically, and every job enters the existing Find → Tailor → Review → Apply flow.

**Architecture:** Aggregator sources take a `SearchSpec` (keywords, location, remote) instead of a bare keyword list; a `searches` table holds the user's searches (derived from tracks on first use); the poller runs every active search against every enabled aggregator, ingests through the existing dedupe, and auto-adds ATS boards recognised in result URLs; credentials for keyed sources are Fernet-encrypted rows; the web adds a Searches tab, a Job sources settings section, and source chips.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy/Alembic, arq, httpx; Next 16 / React 19 / TanStack Query / vitest.

**Spec:** `docs/superpowers/specs/2026-09-14-job-portal-design.md`

## Global Constraints

- CLAUDE.md rules: never submit an application (applying stays the existing Review → Mark applied flow); nothing personal and no keys in the repo; secrets via `.env` or encrypted rows; max 3 LLM calls per tailoring run (discovery makes none).
- Import-linter: `engine` imports none of config/profile/db/services/worker/api/cli; `services` never import worker/api/cli.
- Every outbound request goes through `DiscoveryHttp` (SSRF checks, size cap, redirect checks). Sources never build URLs from user text without URL-encoding it (`urllib.parse.quote`/`urlencode`).
- Source ids (verbatim): `themuse`, `remotive`, `adzuna`, `jooble`, `jsearch`; existing `remoteok`, `hn-hiring`. Labels: "The Muse", "Remotive", "Adzuna", "Jooble", "JSearch (Google Jobs)". Credential fields: adzuna → `app_id`, `app_key`; jooble → `api_key`; jsearch → `rapidapi_key`; the others none. Per search per source cap: `SEARCH_CAP = 100`.
- Remote values (verbatim): `include`, `only`, `exclude`. Search defaults: remote `include`, active true.
- Board auto-discovery patterns (host + first path segment): `boards.greenhouse.io/<slug>`, `job-boards.greenhouse.io/<slug>` → greenhouse; `jobs.lever.co/<slug>` → lever; `jobs.ashbyhq.com/<slug>` → ashby; `<prefix>.myworkdayjobs.com/<lang>/<site>` or `/wday/cxs/<tenant>/<site>` → workday with board `<prefix>/<site>`.
- Python checks before every commit (from `apps/api`): `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, pytest in two foreground runs (memory is tight; never two at once, never in the background): `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py` then `uv run pytest -q -p no:cacheprovider tests/api tests/db`. Web (from `apps/web`): `npx vitest run --testTimeout=90000`, `pnpm typecheck`, `pnpm lint` (one accepted warning in `TaskProgress.tsx`), `pnpm build`.
- Generated files never hand-edited: `apps/api/src/rhapto/models/**`, `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts` via `bash scripts/codegen.sh` from the repo root; commit with the change that caused them.
- Commit messages end with the two attribution lines given in the session.

## File Structure

```
apps/api/src/rhapto/services/discovery/search.py            NEW SearchSpec, derive_searches
apps/api/src/rhapto/services/discovery/sources/base.py      SourceInfo gains needs_key, fields; AggregatorSource protocol (fetch_search)
apps/api/src/rhapto/services/discovery/sources/{themuse,remotive,adzuna,jooble,jsearch}.py   NEW
apps/api/src/rhapto/services/discovery/sources/{remoteok,hn_hiring}.py   accept SearchSpec (keywords only)
apps/api/src/rhapto/services/discovery/boards.py            NEW board_from_url
apps/api/src/rhapto/services/discovery/poller.py            searches × aggregators; auto-discovery; per-search run rows
apps/api/alembic/versions/0006_searches.py                  searches, source_credentials, jobs.search_id, watchlist.discovered
apps/api/src/rhapto/db/models.py                            SearchRow, SourceCredentialRow, Job.search_id, Watchlist.discovered
apps/api/src/rhapto/db/repositories/{searches,source_credentials}.py   NEW
packages/schemas/profile/watchlist.json                     aggregators enum + discovered flag
apps/api/src/rhapto/api/routers/{searches,settings}.py      searches CRUD + derive; /settings/sources
apps/api/src/rhapto/api/schemas.py                          SearchOut/In, SourceSettingOut/In, SourceTestOut, JobOut.search_name
apps/api/src/rhapto/api/routers/packages.py                 answers already in PackageOut (no change)
apps/web/src/components/profile/SearchesTab.tsx             NEW
apps/web/src/components/settings/JobSourcesSection.tsx      NEW
apps/web/src/components/queue/{JobCard,NextUp}.tsx          source chip, "via <search>"
apps/web/src/lib/api/queries.ts                             hooks
README.md                                                   portal section
```

---

### Task 1: SearchSpec, aggregator protocol, five new sources

**Files:** Create `services/discovery/search.py`, `sources/themuse.py`, `sources/remotive.py`, `sources/adzuna.py`, `sources/jooble.py`, `sources/jsearch.py`, tests `tests/unit/test_discovery_search_sources.py`; modify `sources/base.py`, `sources/remoteok.py`, `sources/hn_hiring.py`, `sources/__init__.py`, `tests/unit/test_discovery_aggregators.py`.

**Interfaces:**
- `search.py`: `@dataclass(frozen=True) class SearchSpec: keywords: tuple[str, ...]; location: str | None; remote: Literal["include","only","exclude"]; name: str = ""`; `def query_text(spec) -> str` (keywords joined with " OR " for sources that accept boolean text, else the first keyword; each source decides); `def remote_matches(spec, location_text: str | None, remote_flag: bool | None) -> bool` (`only` requires remote; `exclude` rejects remote; `include` accepts all).
- `base.py`: `SourceInfo` gains `needs_key: bool = False` and `fields: tuple[str, ...] = ()`; new `class AggregatorSource(Protocol): info; async def fetch_search(self, http, spec: SearchSpec, credentials: dict[str, str]) -> list[Posting]`. Board sources keep `fetch(board, keywords)`. `remoteok` and `hn_hiring` gain `fetch_search` that delegates to their existing logic with `spec.keywords` (their `fetch` stays for compatibility).
- `sources/__init__.py`: `aggregator_sources() -> list[SourceInfo]` and `get_aggregator(name) -> AggregatorSource` (raise `SourceError` for a board source).
- Source request shapes (exact):
  - themuse: `GET https://www.themuse.com/api/public/jobs?page={n}&location={quote(spec.location)}` (omit location when empty), pages 1.. until `page_count` or cap; result fields `id`, `name` (title), `company.name`, `locations[].name`, `refs.landing_page` (url), `contents` (html), `publication_date`. Filter by `matches_keywords(spec.keywords, name, text)`; remote = any location name containing "Remote"/"Flexible".
  - remotive: `GET https://remotive.com/api/remote-jobs?search={quote(first keyword)}&limit=100`; fields `id`, `title`, `company_name`, `candidate_required_location`, `url`, `description` (html), `publication_date`; all results are remote (skip when `remote == "exclude"`); location = `candidate_required_location`.
  - adzuna: `GET https://api.adzuna.com/v1/api/jobs/us/search/{page}?app_id=..&app_key=..&what={quote(keyword)}&where={quote(location)}&results_per_page=50&content-type=application/json`, one call per keyword, page until cap; fields `id`, `title`, `company.display_name`, `location.display_name`, `redirect_url`, `description`, `created`.
  - jooble: `POST https://jooble.org/api/{api_key}` body `{"keywords": <keyword>, "location": <location>, "page": n}`; fields `id`, `title`, `company`, `location`, `link`, `snippet`, `updated`. The key is in the URL: `DiscoveryHttp` must never log full URLs for this source (the SSRF checker already only inspects host); redact when raising `SourceError` (replace the key with `…`).
  - jsearch: `GET https://jsearch.p.rapidapi.com/search?query={quote(f"{keyword} in {location}")}&page=1&num_pages=2&remote_jobs_only={true|false}` with headers `x-rapidapi-key`, `x-rapidapi-host: jsearch.p.rapidapi.com` — `DiscoveryHttp.get_json` gains an optional `headers: dict[str, str] | None` parameter (merged over defaults; keys never logged); fields `job_id`, `job_title`, `employer_name`, `job_city`/`job_state`/`job_country`, `job_apply_link`, `job_description`, `job_posted_at_datetime_utc`, `job_is_remote`.
- Errors: HTTP 401/403 or a body saying the key is invalid → `SourceError("<label>: check the API key")`; everything else as today.

- [ ] **Step 1: Failing tests.** For each source with `FakeDiscoveryHttp` routes: mapping of every field, the cap (a fake returning 150 items → 100 postings), keyword filtering where the API does no filtering (themuse), remote handling for the three `remote` values, location quoting (a location with a space and comma produces `%20`/`%2C` in the recorded URL), 401 → `SourceError` mentioning the key, one malformed item skipped, `needs_key`/`fields` per source, `aggregator_sources()` lists seven sources in registration order, `get_aggregator("greenhouse")` raises. `remote_matches` and `query_text` unit tests. Jooble: the recorded `SourceError` text does not contain the key. JSearch: the recorded headers carry the key and the fake's `calls` entry does not.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement** per Interfaces (add `headers` to `DiscoveryHttp.get_json`/`_get` and to the fake, recording headers separately in `fake.headers: list[dict]`).
- [ ] **Step 4: Checks and commit** (`feat(discovery): saved-search aggregator sources (The Muse, Remotive, Adzuna, Jooble, JSearch)`).

---

### Task 2: Storage: searches, source credentials, job search link, discovered boards

**Files:** Create `alembic/versions/0006_searches.py`, `db/repositories/searches.py`, `db/repositories/source_credentials.py`, `tests/db/test_searches_repo.py`; modify `db/models.py`, `packages/schemas/profile/watchlist.json` (+ codegen), `profile/loader.py` if watchlist rows are validated there, `profile.example/watchlist.yaml` (no change needed unless `discovered` must be present; it defaults false).

**Interfaces:**
- Migration `0006`: `searches(id, user_id fk cascade, name String(100), keywords JSONB list, location String(200) null, remote String(10) default 'include', active bool default true, derived_from_track_id String(100) null, timestamps)`; `source_credentials(id, user_id, source String(50), credentials_encrypted Text, timestamps, unique(user_id, source))`; `jobs.search_id uuid null fk searches on delete set null`; `watchlist.discovered bool default false not null`. Downgrade reverses.
- Models: `SearchRow`, `SourceCredentialRow`, `Job.search_id`, `Watchlist.discovered`.
- Repos: `list_searches(session, user_id) -> list[SearchRow]` (ordered by created_at), `create_search(session, user_id, *, name, keywords, location, remote, active, derived_from_track_id)`, `update_search(session, row, **fields)` (clears `derived_from_track_id` when keywords/location/remote change), `delete_search(session, user_id, search_id) -> bool`; `get_credentials(session, settings, user_id, source) -> dict[str, str]` (decrypts; `{}` when none), `put_credentials(session, settings, user_id, source, values: dict[str, str])` (encrypt JSON; upsert ON CONFLICT), `delete_credentials(...)`.
- Schema: `watchlist.json` aggregators enum gains the five new ids; watchlist entries gain `discovered: boolean default false`. Regenerate models.

- [ ] **Step 1: Failing tests** (db): search CRUD and ordering; `update_search` clearing the derived link; credentials round trip never storing plaintext (assert the row's `credentials_encrypted` does not contain the value); `Watchlist.discovered` default; `jobs.search_id` set null on search delete.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement**; `uv run alembic upgrade head`, `downgrade -1`, `upgrade head`.
- [ ] **Step 4: Checks and commit** (`feat(db): searches, source credentials, discovered boards`).

---

### Task 3: Poller: searches × aggregators, board auto-discovery, derivation

**Files:** Create `services/discovery/boards.py`, `tests/unit/test_discovery_boards_autodiscover.py`; modify `services/discovery/search.py` (`derive_searches`), `services/discovery/poller.py`, `tests/unit/test_poller.py`, `services/discovery/errors.py` if needed.

**Interfaces:**
- `boards.py`: `def board_from_url(url: str) -> tuple[str, str] | None` returning `(source, board)` per the Global Constraints patterns (host compared case-insensitively; slug segment validated `[A-Za-z0-9._-]+`; workday returns `<prefix>/<site>` where prefix is the host minus `.myworkdayjobs.com`).
- `search.py`: `async def derive_searches(session, user_id) -> list[SearchRow]` creates one search per track when the user has none: name = track name, keywords = first six track keywords, location = first `location_preferred` keyword if set else `location_home` else None, remote = `include` if `remote_ok` is not no else `exclude`, `derived_from_track_id` = track id. Returns the created rows (empty list when searches already exist).
- Poller: `build_specs` gains, for each active search × each enabled aggregator (aggregator rows from `profile_repo.list_aggregators` with `enabled`; keyed sources need credentials present or they are skipped with a run row `status="skipped", error="no API key"`), a `SourceSpec(source=<agg>, board=None, company=None, keywords=search.keywords, search=SearchSpec(...), search_id=search.id, credentials=...)`. Polling an aggregator spec calls `fetch_search`. Ingest sets `job.search_id` for new jobs. After ingest, for each new job, `board_from_url(job.url)` → if a match and no watchlist row `(source, board)` exists, insert a row `company=job.company, keywords=search.keywords, discovered=True`. Run rows carry `search_id` (add the column in Task 2's migration: `poll_runs.search_id uuid null`) so the drawer can show per-search counts. The legacy path (aggregator rows with keywords but no searches) still works: when the user has zero searches, `derive_searches` runs first inside the poll.

- [ ] **Step 1: Failing tests.** `board_from_url` for every pattern (mixed case, trailing paths, query strings) and non-matches (`linkedin.com`, `greenhouse.io` without a slug, `evil.myworkdayjobs.com.attacker.net`). `derive_searches` from two tracks and the example answers; idempotent. Poller: two active searches × two enabled aggregators → four fetches with the right specs (fake sources registered in the test); keyed source without credentials → skipped run row; a result whose URL is a Lever board adds a discovered watchlist row once (second poll does not duplicate); `job.search_id` set.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Checks and commit** (`feat(discovery): saved searches drive aggregators; boards discovered from results`).

---

### Task 4: API: searches, source settings, job fields

**Files:** Create `api/routers/searches.py`, `tests/api/test_searches_api.py`, `tests/api/test_source_settings_api.py`; modify `api/routers/settings.py`, `api/schemas.py`, `api/app.py`, `api/routers/jobs.py`, `db/repositories/jobs.py` (join search name), `tests/api/test_jobs_api.py`; codegen.

**Interfaces:**
- `/api/v1/searches`: `GET` → `list[SearchOut]` (`id, name, keywords, location, remote, active, derived_from_track_id, created_at`); `POST SearchIn(name, keywords: list[str] (1..10, each 1..60 chars), location: str | None (≤200), remote, active=True)` → 201; `PUT /{id}`; `DELETE /{id}` → 204; `POST /derive` → `list[SearchOut]` created (empty when some exist).
- `/api/v1/settings/sources`: `GET` → `list[SourceSettingOut(id, label, needs_key, fields: list[str], enabled, key_set)]` (enabled from the aggregators rows, created on demand with `enabled` default true for keyless and false for keyed sources); `PUT /{source}` body `SourceSettingIn(enabled: bool, credentials: dict[str,str] | None)` (credentials merged: omitted keys keep stored values; keyed source enabled without all fields set → 422 "<label> needs <field>"); `POST /{source}/test` → `SourceTestOut(ok, found: int | None, error)` running `fetch_search` with `SearchSpec(("program manager",), None, "include")` capped at 1 page, never 500.
- `JobOut` gains `search_name: str | None` (joined from `searches.name`); `PackageOut.answers` already exists.
- Credentials never appear in any response, log, or error text (reuse `services/llm.redact` for the test endpoint's error).

- [ ] **Step 1: Failing tests.** Searches CRUD, validation (empty keywords → 422), derive creates per track then returns empty; per-user scoping (another user's search → 404). Source settings: GET lists seven with correct `needs_key`/`fields`; PUT enabling adzuna without keys → 422; PUT with keys → `key_set` true and no key in the body; test endpoint ok/error with a fake source; `JobOut.search_name` after a poll with a fake source.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement**; codegen.
- [ ] **Step 4: Checks and commit** (`feat(api): saved searches, job source settings, search name on jobs`).

---

### Task 5: Web: Searches tab, Job sources settings, source chips

**Files:** Create `components/profile/SearchesTab.tsx` (+test), `components/settings/JobSourcesSection.tsx` (+test); modify `lib/api/queries.ts`, `app/profile/page.tsx`, `app/settings/page.tsx`, `components/queue/JobCard.tsx`, `components/queue/NextUp.tsx`, `components/profile/WatchlistTab.tsx` (discovered chip), tests for each.

**Interfaces:**
- Hooks: `useSearches`, `useCreateSearch`, `useUpdateSearch`, `useDeleteSearch`, `useDeriveSearches`, `useSourceSettings`, `usePutSourceSetting`, `useTestSource`.
- Searches tab: table (name, keywords as chips, location, remote select, active switch, "derived" chip), inline add row, edit dialog, delete with confirm; "Derive from tracks" button shown when the list is empty.
- Job sources section (Settings, below AI provider): one row per source: label, switch, key inputs (`type=password`, placeholder `…set` when `key_set`), Test button with inline result, Save per row.
- JobCard / NextUp: zinc chip with the source label (a small label map matching the API labels), "via <search_name>" muted text; the existing state button (Tailor / Review / Mark applied) stays the only action. Watchlist tab: "discovered" chip on rows with `discovered`.

- [ ] **Step 1: Failing tests.** Searches tab: renders rows, add sends the body, toggling active calls update, delete confirms; derive button when empty. Job sources: switch and key save body, test result shown, no key echoed. JobCard/NextUp: chip label and via text; Watchlist discovered chip.
- [ ] **Step 2: Run to verify failure.**
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Web checks and commit** (`feat(web): searches, job sources, source chips`).

---

### Task 6: README and end-to-end

- [ ] **Step 1:** README: a "Find jobs across the market" section (searches derive from tracks; keyless sources on by default; keyed sources and where to get free keys: Adzuna developer portal, Jooble API page, RapidAPI JSearch; auto-discovered boards; then the usual flow: Tailor → Review → download → apply on the employer's site → Mark applied; nothing is submitted for you).
- [ ] **Step 2:** Rebuild api, worker, web one at a time; poll from the app with the user's derived searches (keyless sources only unless the user supplies keys); confirm new jobs from The Muse/Remotive appear with source chips and that at least one discovered board row was added; tailor one of them through the normal flow.
- [ ] **Step 3: Commit** (`docs: market-wide search and the apply flow`).

---

## Self-review notes

- Spec coverage: §3 sources and credentials (T1, T2, T4), §4 searches and derivation (T2, T3, T4), §5 auto-discovery (T3), §6 applying (unchanged flow, no task), §7 UI (T5), §8 tests (each task), docs (T6).
- Type consistency: `SearchSpec(keywords, location, remote, name)`, `fetch_search(http, spec, credentials)`, `board_from_url`, `derive_searches`, `SearchOut/In`, `SourceSettingOut/In`, `SourceTestOut`, `JobOut.search_name` used by the same names in every task; `poll_runs.search_id` added in T2 for T3.
- Judgement calls for the executor: exact pagination fields per API (verify against the live keyless endpoints with one manual request each, never in tests); whether `AnswersPane` is new or an extension of the existing answers rendering.
