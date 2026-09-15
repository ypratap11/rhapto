# Rhapto portal — design

Date: 2026-09-14. Status: approved in chat; plans to follow. Supersedes `2026-09-14-ui-refresh-design.md`
(branch `ui-refresh`, not merged; see §12 for what is salvaged) and absorbs `2026-09-14-job-portal-design.md`
(its sources and saved searches are prerequisites; §6 adds the live path).

## 1. Goal

Make Rhapto usable by a stranger the way a candidate uses the MyGreenhouse portal: a dashboard that shows where
you stand, a search box that reaches the whole market, a card for every job, and one obvious next step at every
stage. Rhapto's own ideas stay at the centre: the fit score against a career track, tailored resumes that a
human reviews, guardrails, and the rule that a human clicks Apply.

Reference: the user's four MyGreenhouse screenshots (Home, Profile, Applications, Jobs search). Structure is
borrowed; identity is Rhapto's (warm off-white, brick red, Fraunces serif), pushed so nobody thinks it is a copy.

## 2. Principles

1. **Every card has a way forward and a way out.** No stage is a dead end.
2. **Fit is the signature.** Every job shows its fit ring and the track it was scored against.
3. **The dashboard reports facts, not promos.** Headline numbers come from the user's own data.
4. **Human-in-the-loop, unchanged.** Rhapto opens the employer's page; it never submits.
5. **Nothing personal in the repo.** Docs and screenshots use `profile.example/`.

## 3. Navigation and screens

Top bar (56px, surface, hairline bottom border): wordmark "Rhapto" in Fraunces; text links **Dashboard ·
Jobs · Resumes · Pipeline · Profile**, the current one underlined in brick red (2px, offset 6px); right: theme
toggle, Settings gear. No pill tabs. The Find → Tailor → Review → Apply step bar is removed; the flow lives in
each job's page (§4). Old URLs (`/packages`, `/pipeline`) redirect.

Breadcrumbs on every nested page, under the top bar, each segment a link and the last plain text; the
document title matches: `Jobs › Scale AI · Technical Program Manager`, `Resumes › … › v2`, `Pipeline › …`,
`Profile › Blocks`.

### 3.1 Dashboard (`/`)

- **Hero band** (peach, serif headline 32px/500): "{N} new roles fit you this week · {M} resumes waiting for
  review"; buttons Review resumes, Poll now. When both are zero: "Nothing new yet. Add a search or a company
  to your watchlist." with buttons New search, Add company.
- **Left column.** Job search card (§6 form). **Recommended roles**: fit-ranked jobs with no resume and no
  application, not hidden, not "no longer listed"; ten per page, up to five pages; card = fit ring, title,
  company, track chip, location-tier chip, source chip, two-line JD excerpt, buttons Tailor and Not
  interested. **Active applications**: the three most recently updated Pipeline items plus any resume marked
  Ready and not yet applied, as small cards; follow-up reminders due today appear first with a red chip.
- **Right rail.** **Profile checklist** (§7). **Saved searches** with "N new" per search, each linking to
  Jobs with that search loaded.
- **Your pipeline** funnel card — deferred (§13 Later) and built last.

### 3.2 Jobs (`/jobs`)

Mint hero band holding the search form (§6). Below, **Browse jobs**: three-column grid (one column under
768px, two under 1100px) of job cards: logo placeholder (initial in a warm tile), title, company, chips
(track, source, location tier, Remote/Hybrid/On site when known, Reposted when `repost_of`), salary line when
the source gives one, "Posted · {relative}", fit ring top right. Sort: Fit (default) or Newest. Filter chips
from §6. "Save this search" in the band when the current query is not saved. A card opens the job page.

### 3.3 Job page (`/jobs/[id]`, existing route, rebuilt)

Header: breadcrumb, title, company, chips, fit ring with "against {track}", primary action by state (§4).
Left: JD (existing pane). Right: the latest resume summary with Review link, guardrail panel, application
status when one exists. Not interested and Reposted handling per §4.

### 3.4 Resumes (`/resumes`)

The packages list, tabs **Needs review · Ready · Blocked · Applied**, table rows: company, role, fit ring,
version · status pill, mode chip, created, buttons Review / Skip. Review opens the existing review page
(document surfaces, word diff, grouped actions from ui-refresh Task 3 are kept, §12). Row actions: Review,
Mark ready, Regenerate, Skip.

### 3.5 Pipeline (`/pipeline`)

List-detail like the Greenhouse Applications page. Left: search, sort (updated, applied date, company),
tabs **Applied · Screen · Interview · Offer · Closed**, application cards (company, role, status pill,
"Applied · {date}", follow-up chip). Right: the selected application: breadcrumb, header, status control
(§4), notes, follow-up date, status history, the resume used, and the JD. The Kanban board stays reachable at
`/pipeline/board` (deferred toggle, §13).

### 3.6 Profile (`/profile`)

Sand hero band: name, location (from answers), "{k} of 23 blocks verified". Two columns of summary cards,
each with an Edit that opens the existing editor as a sheet: left **Resume template, Tracks, Blocks, Bases**;
right **Contact and answers, Guardrails, Location preferences, Watchlist**. Import/export moves to Settings.

### 3.7 Settings (`/settings`, existing)

Adds **Sources** (from the job-portal spec: enabled, needs key, key set), **Saved searches** (edit, pause,
delete), and **Import / export**.

## 4. Flow and stage actions

States: job `new → tailored | hidden | unlisted`; package `needs_review → ready → applied | blocked |
archived`; application `applied → screen → interview → offer | closed(reason)`.

| Stage | Forward | Out |
|---|---|---|
| Job (grid, recommendations, job page) | **Tailor** | **Not interested** hides the job (`jobs.hidden_at`); Undo toast for 8 s; "Show hidden" toggle on Jobs |
| Resume | **Review** → **Mark ready** → **Apply** | **Skip** archives the package (`packages.archived_at`) and hides the job; **Regenerate** makes a new version; **Blocked** lists violations with a Fix link |
| Apply | Opens the posting in a new tab and downloads the resume; on return the card asks "Did you apply?" **Yes / Not yet / Skip** | Yes creates or updates the application as Applied with today's date |
| Pipeline | **Screen → Interview → Offer**, each with date and optional note | **Closed** with reason `rejected | withdrew | no_response | filled`; **Follow-up** date puts a reminder on the Dashboard |

Closed postings: a job a source no longer returns on two consecutive polls gets `unlisted_at`, leaves
recommendations and the Resumes queue, and shows "No longer listed" on any application. Reposts: `repost_of`
shows a Reposted chip linking the two; Tailor on a repost offers "Reuse resume v{n}".

## 5. Tracks and the field picker

A track is what a job is scored against. The Profile checklist item **Tracks** opens a two-level picker:

- **Fields** (left): Engineering, Data Science, Product, Program and Project Management, Design, Marketing,
  Sales, Finance, Operations, People, Customer Success, Other.
- **Roles** (right, per field), e.g. Engineering: Backend, Frontend, Full stack, Mobile, ML Engineering,
  DevOps and SRE, Security, QA; Data Science: Data Scientist, Data Analyst, Data Engineer, Analytics
  Engineer, ML Research; Program and Project Management: Technical Program Manager, Program Manager, Project
  Manager, Delivery Lead, Scrum Master.

Picking a role creates a track: name = role, keywords = the role's curated list, `min_fit` = 60. Tracks are
editable (name, keywords, threshold) in the same card. The taxonomy is a data file
`packages/schemas/taxonomy.yaml` (field → roles → keywords → source category names), served by
`GET /api/v1/taxonomy`. **Suggested from your resume**: when a resume template is uploaded, the parser's entry
titles are matched against role names and shown as one-tap chips at the top of the picker.

Where tracks appear: the search form's **Field** select (default "My tracks"), the Track filter chip and the
track chip on every card, and one derived saved search per track (job-portal spec §4). The Muse and Adzuna
take the field's category name; keyword sources get the track's keywords.

## 6. Search and saved searches

Form (Dashboard card and Jobs band): title (free text), location (free text, default `location_home`),
Field select, Remote (include | only | exclude), Search. Filter chips below: **Date posted** (24h, 7d, 30d,
any), **Source** (multi), **Fit** (75+, 60+, all). Work type and Salary are not filters in this version
(§13); salary shows on cards when present.

`POST /api/v1/search` `{ query, location, remote, field?, posted_within?, sources? }` → fans out to every
enabled aggregator and watchlist board in parallel (per-source timeout 8 s, cap 30 results per source),
dedupes by `identity_hash`, stores new jobs with `source` and `search_id = null`, enqueues scoring, and returns
`{ jobs: JobOut[], per_source: {source: {found, new, error?}} }` in one response. Known jobs return scored;
new ones return `best_fit: null` and the client refetches `GET /jobs?ids=` every 3 s until scored (the worker
scores a 30-job chunk in seconds).

`POST /api/v1/searches` saves the current form as a saved search (job-portal spec §4 table plus
`last_viewed_at`); the worker polls it on the normal schedule with the background cap of 100. "N new" =
jobs with `search_id` and `discovered_at > last_viewed_at`; opening the search's results sets
`last_viewed_at`.

## 7. Dashboard data

`GET /api/v1/dashboard` returns in one call: `new_fit_count` (jobs discovered in the last 7 days with
`best_fit >= track.min_fit`, not hidden/unlisted), `needs_review_count`, `checklist` (six booleans plus
`verified_blocks`/`total_blocks`), `saved_searches[] {id, name, new_count}`, `due_followups[]`.

Checklist items and their tests: resume template uploaded; contact answers complete (name, email, phone,
location, links); at least one track; verified blocks exist (shown as "18 of 23 verified"); guardrails set;
location preferences set (`location_home`, `location_preferred`, `remote_ok`). Each row: check or empty
circle, label, one-line detail, Edit link to the Profile card.

"New": a job is new until opened, tailored, hidden, or seven days old. Opening the grid does not clear it.

## 8. Visual system

Fonts: headings Fraunces (`--font-fraunces`, weight 500, `tracking-tight`), body Inter, mono JetBrains Mono
(ring numbers, versions). Hero headlines 32px, page titles 24px, card titles 16px/600 (Inter).

Tokens (`globals.css`, light / dark):

| token | light | dark |
|---|---|---|
| background | `#faf8f5` | `#191614` |
| surface | `#ffffff` | `#221e1b` |
| surface-muted | `#f1ece4` | `#2b2622` |
| border | `#e7e1d8` | `#3a332e` |
| foreground | `#1c1917` | `#f3ede6` |
| muted-foreground | `#6b6259` | `#b3a89c` |
| primary | `#b4432e` | `#e0715a` |
| primary-foreground | `#ffffff` | `#191614` |
| primary-hover | `#9a3826` | `#e98a76` |
| ring | `#b4432e` | `#e0715a` |
| destructive | `#a32d2d` | `#f08a8a` |
| band-peach | `#f8e3d2` | `#3a2a22` |
| band-mint | `#d9efe6` | `#1f3029` |
| band-sand | `#f1ece4` | `#2b2622` |
| fit-high / bg | `#2f7d4f` / `#dff0e5` | `#7fd19a` / `#1f3d2b` |
| fit-mid / bg | `#a65f0f` / `#f8e9cf` | `#f0b35a` / `#3f2d10` |
| fit-low / bg | `#6b6259` / `#f1ece4` | `#b3a89c` / `#2b2622` |

Radii: cards 10px, controls 8px, chips 6px (square-ish, unlike the 999px pills of ui-refresh). Shadows:
`0 1px 2px rgb(28 25 23 / .05), 0 4px 14px rgb(28 25 23 / .06)`; hover adds `0 8px 24px rgb(28 25 23 / .09)`.
Hero bands: full-width, 160px on Dashboard, 120px elsewhere, no artwork; a faint stitched-line motif in the
band's right third (SVG, 8% opacity) is Rhapto's own mark. Status pills use the fit and primary tokens
(remapped `StatusBadge`). Focus ring 2px `ring` with 2px offset on every interactive element; transitions
150 ms; `prefers-reduced-motion` disables transforms. Every text/background pair passes WCAG AA, enforced by
`scripts/check-contrast.mjs` (salvaged, §12) extended with a grep gate that fails on raw palette classes
outside `globals.css`. If a spec value fails AA, the implementer adjusts it and comments the deviation at
the token.

Differentiators from Greenhouse, deliberately: brick-red underline nav instead of green; fit rings on every
card; data headlines in the bands; the stitched motif; 6px chips; serif only for headlines.

## 9. Data model changes

- `jobs`: `hidden_at`, `unlisted_at`, `search_id` (job-portal spec), `salary_text` (nullable, from source).
- `packages`: `archived_at`.
- `applications`: `closed_reason` (`rejected | withdrew | no_response | filled`, nullable), `follow_up_at`.
- `searches`: `last_viewed_at` (in addition to the job-portal spec's columns).
- `tracks`: `field` (taxonomy field id, nullable), `role` (taxonomy role id, nullable).
- New file `packages/schemas/taxonomy.yaml`.

## 10. API changes

`POST /search`; `POST/GET/PATCH/DELETE /searches`; `GET /dashboard`; `GET /taxonomy`;
`POST /jobs/{id}/hide` and `/unhide`; `POST /packages/{id}/archive`; `PATCH /applications/{id}` gains
`closed_reason`, `follow_up_at`; `GET /jobs` gains `ids`, `hidden`, `search_id`, `sort=fit|newest`,
`posted_within`, `sources`, `field`; `GET /packages?status=` gains `archived`. All under `/api/v1`.

## 11. Delivery

Two plans, executed in order on branch `portal` from `main`:

1. **portal-backend**: the job-portal plan's six tasks (sources, credentials, saved searches, derived
   searches, auto-discovered boards, settings API) plus: live search endpoint, taxonomy file and endpoint,
   flow fields and endpoints (§9–10), dashboard endpoint, unlisted detection.
2. **portal-ui**: tokens and shell, Dashboard, Jobs, job page, Resumes, Pipeline, Profile and field picker,
   Settings additions, e2e flow tests, screenshot walkthrough, documentation (§14–15).

## 12. Salvaged from `ui-refresh`

Kept by re-applying on `portal` (not by merging): `scripts/check-contrast.mjs` (+ grep gate),
`components/ui/theme-toggle.tsx` and the layout boot script, `EmptyState`, `DocumentSurface`, `FitRing`
(recoloured), the review page's word diff (Before/After split, textarea on focus, `tabIndex=-1` when not
editable), grouped `PackageActions`, `TableSkeleton`, the bounded sticky table panel, dialog/sheet surface
classes. Dropped: indigo tokens, Geist, pill nav, progress rail, the queue-style Jobs page.

## 13. Later (deliberately not in this version)

Snooze; Not-interested reasons; applications-per-week sparkline; Closed-reasons chart; the pipeline funnel
card (build last, only if time allows in portal-ui; otherwise next); Board toggle on Pipeline; Work-type
filter; Salary filter; animated nav indicator.

## 14. Testing

- Unit: vitest for every component and hook; API pytest for every endpoint, including the live search
  fan-out with fake sources, timeouts, and dedupe.
- **Per-page flow tests (required).** Playwright in `apps/web/e2e/`, run against the Docker Compose stack
  seeded with `profile.example/` and the API's fake LLM provider, one spec per page: Dashboard (numbers,
  recommendation → Tailor → resume appears), Jobs (search with a fake source → grid → Save search → rail
  count), Job page (Tailor → Review → Mark ready → Apply → Did-you-apply → Pipeline), Resumes (Skip archives
  and hides; Blocked shows violations), Pipeline (status changes, Closed with reason, follow-up on
  Dashboard), Profile (field picker creates a track; checklist flips; suggestions from resume). Run manually
  and in CI when Docker is available.
- **Screenshot walkthrough (deliverable).** `scripts/screenshots.mjs` captures every page in both themes,
  with correct routes, into `docs/user-guide/images/` using `profile.example` data; the controller opens
  each image and reports what it shows. The same images illustrate the user guide.
- Checks before every commit: vitest, typecheck, lint (one accepted warning), build, contrast + palette gate.

## 15. Documentation

- **Product docs** `docs/product/`: `overview.md` (what Rhapto is, who it is for, the human-in-the-loop
  rule), `concepts.md` (tracks, fit, blocks, verified metrics, guardrails, resumes, pipeline),
  `flow.md` (the stage table from §4 with screenshots), `sources.md` (each source, what it needs, limits),
  `architecture.md` (short, links to `requirements-architecture.md`), `privacy.md` (what is stored, keys
  encrypted, nothing sent anywhere but the sources and the LLM).
- **User guide** `docs/user-guide/`: `getting-started.md` (install with Docker, first run, upload resume,
  pick tracks, first search), `dashboard.md`, `jobs-and-search.md`, `resumes.md`, `pipeline.md`,
  `profile-and-tracks.md`, `settings-and-sources.md`, `faq.md`. Written for a stranger, one task per
  section, every page illustrated from the walkthrough images. README links both sets; a Help link in the
  top bar's Settings menu opens the guide.
- All examples use `profile.example/`; no real names, employers or keys.
