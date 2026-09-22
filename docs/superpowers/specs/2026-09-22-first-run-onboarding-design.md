# First-run onboarding and honest failure reporting — design

Date: 2026-09-22. Status: approved in chat; plan to follow. Builds on `main` at `e2997b1`
(usage tracking, 90-day job window, constrained composer, taxonomy on tracks).

## 1. Goal

Let someone who is not the author get from a cold install to a tailored resume and a populated job
list without a maintainer in the loop — and, when something is empty or broken, tell them why in
words they can act on.

Two audiences, one build:

- **Self-hosters** — technical, clone the repo, run Docker, hold their own `.env`.
- **Job seekers** — not technical, care about a resume and a job list, not YAML.

Both bring their own API keys. The project cannot fund anyone's API usage, so every screen that
costs money says what it costs before it spends it.

## 2. Why this, and why now

Rhapto works. A session on 2026-09-21/22 produced a guardrail-clean, provenance-traced resume for a
real posting at ~19¢, and grew the corpus from ~750 jobs across 6 companies to 1,206 across 334.

None of that was reachable by a stranger. Getting there required: assigning taxonomy nobody
documents, discovering Adzuna scores `"San Francisco Bay Area"` at 0 and `"San Francisco, CA"` at
2,769, knowing a RapidAPI subscription is distinct from a RapidAPI key, and hand-building fifteen
blocks. Every one of those failures was **silent** — the UI said "No jobs yet" and nothing more.

Two findings from that session drive this design:

1. **The block library is the product.** Every quality jump came from block content; none came from
   the engine. A user with an empty library gets a thin resume and concludes the tool is bad.
2. **Silence is the dominant failure mode.** Wrong track on every resume ever generated, zero jobs
   from one bad location string, blocked packages, a Field filter that could only ever return zero —
   all invisible without reading Postgres.

## 3. Non-goals

- Hosting anyone's instance, or paying for anyone's API usage.
- Distribution (one-click cloud deploy, desktop bundle). Separate project; this design assumes the
  app is already running.
- New job sources. Supply is solved: six aggregators plus board polling.
- Changing the guardrail contract. Provenance and verified-metrics rules are the product's
  differentiator and are strengthened here, never relaxed.

## 4. Shape: wizard first, checklist after

A dedicated `/welcome` route covers first run in three screens. Anything skipped, and anything that
later breaks, surfaces in the existing dashboard `ProfileChecklist`, which grows to cover setup
beyond the profile.

The wizard gets someone to a first resume and a first poll. The checklist keeps it honest
afterwards. Neither alone is sufficient: a wizard has nowhere to report that an Adzuna location went
stale in week three, and a checklist gives a stranger with an empty everything no obvious first move.

`/welcome` is shown when the checklist reports nothing configured, and is reachable thereafter from
Settings. It never blocks navigation — a user may leave and return; progress is whatever is already
persisted, not wizard-local state.

## 5. Screen 1 — Connect

**Purpose:** reach a working LLM call. Nothing downstream functions without one.

- **Connection** (self-host only; skipped when API URL and token already resolve): API URL and
  bearer token, the values `TokenGate` reads today.
- **LLM provider**: Anthropic, OpenAI or Google, each listed with its models and a **per-resume cost
  estimate** computed from `services/pricing.py` and the measured shape of a real run (~7.9K input,
  ~9.7K output, 2 LLM calls). At current rates that is roughly 19¢ on `claude-opus-5`, 8¢ on
  `claude-sonnet-5`, 4¢ on `claude-haiku-4-5`.
- **Key entry**, then a **Test** that makes one real call. The screen does not advance until it
  passes.

**Honesty requirements.** This is the paywall, and the design states it plainly rather than
demanding a key: what it is for, what it costs per resume, and that the key is stored encrypted and
never leaves the user's own instance.

**Provider risk.** Only Anthropic has ever made a live call in this codebase.
`engine/providers/openai.py` and `gemini.py` exist and are untested against a real endpoint.
Offering all three by price will send cost-sensitive strangers down untested paths.

The resolution is to **label, not gate**: Anthropic is marked tested, OpenAI and Google are marked
"untested — reports welcome", and all three remain selectable. Labelling is honest, costs nothing,
and does not make the author responsible for two providers before anyone has asked for them.
Hardening either one is a separate piece of work, justified by a user actually choosing it. The
per-provider **Test** on this screen is what protects the user in the meantime: an untested provider
that fails does so on screen 1, before any work is invested, not silently on their first tailoring
run.

## 6. Screen 2 — You

**Purpose:** turn an existing resume into a block library, tracks and location.

1. **Upload** a DOCX (reusing the tune-mode parser) or PDF.
2. **Parse into blocks** with one LLM call: typed (`role` / `project` / `achievement` / `skill` /
   `credential`), carrying `org`, `role`, `period` and `content`.
3. **Propose tracks** from the parsed roles, each with a taxonomy `field` and `role` from
   `services/taxonomy`. A track without a field silently empties every Field filter, so the wizard
   never creates one.
4. **Location**: `location_home`, `location_preferred`, `remote_ok` — the keys fit scoring and
   location tiers depend on, and the ones the author's own profile still lacked after months.
5. **Guided metric confirmation.** Every parsed number is shown with its sentence and asked
   "is this accurate and defensible?" — confirm, edit or drop, one at a time.

**Blocks import unverified. Always.** Auto-verifying a user's own resume would put an inflated figure
they wrote once onto every future resume with Rhapto's blessing — the precise failure the guardrails
exist to prevent. The confirmation pass is also where a user learns what "verified" means, by doing
it once on their own numbers.

The cost of that choice is visible and was measured: unverified, output reads "many departments" and
"enterprise customers with recurring revenue"; after confirmation, "15+ departments and 10+
cross-functional teams" and "10+ enterprise customers and $2M ARR". The wizard shows that difference
rather than describing it, so the user understands what confirming buys.

**Dates are never invented.** A block whose period cannot be read from the resume is created without
one and listed as needing a date. Fabricating employment dates on a CV is not a recoverable error.

## 7. Screen 3 — Jobs

**Purpose:** end setup with jobs actually on screen.

- **Keyless sources on by default**: The Muse, Remotive, RemoteOK, HN Who's Hiring. They need no
  signup and were all switched off in the author's own instance for weeks.
- **Optional keyed sources** with per-source field hints and a **Test**: Adzuna (`app_id`,
  `app_key`) and Jooble (`api_key`), both free tiers, together 397 of 490 jobs in one measured poll.
  JSearch is offered only with a warning: its free plan does not include `/search`, which is the only
  endpoint Rhapto uses.
- **Searches derived** from tracks and location — and **location-validated before saving**. A
  candidate location is run against a live source; if it returns nothing, the wizard says so and
  offers alternatives rather than saving a search that silently matches zero.
- **Finish runs a real poll** and shows the count arriving.

**Screen 3 ends with a poll, not a "Finish" button.** Every silent failure of that session — dead
location, disabled sources, empty searches, a source paused after three failures — would have
surfaced immediately if setup had ended by fetching jobs and reporting what came back.

## 8. Failure visibility

An empty state must distinguish "nothing matched" from "this cannot ever match", and say which.

| Where | Today | Required |
|---|---|---|
| Jobs, Field filter | "No jobs yet" | "You have no tracks in Engineering. Your tracks are in Program & Project Management." |
| Jobs, any filter | "No jobs yet" | Which filter excluded everything, and a one-click widen |
| Saved search | silent zero | "This search has never returned a job. Its location may not be recognised." |
| Job source | silent zero, or paused | "Adzuna returned 0 for 'San Francisco Bay Area'. Try 'San Francisco, CA'." |
| Paused source | buried in a run row | Visible state plus a Resume control |
| Blocked package | "blocked" | Which rule, which bullet, and what to do |
| Dateless blocks | invisible | Counted on the checklist |

The dashboard `ChecklistOut` grows beyond its six profile checks to cover `llm_key`, `job_sources`,
`saved_searches` and `jobs_found`, so a stranger always has a next action. Each row keeps the
existing deep-link pattern (`/profile?card=…`, `/settings`).

## 9. Data and API

Mostly reuse. New surface:

- `POST /api/v1/profile/import-resume` — upload, parse, return proposed blocks, tracks and location
  **without persisting**, so the user confirms before anything is written.
- `POST /api/v1/searches/validate-location` — run a candidate location against a live source and
  report the match count.
- `GET /api/v1/settings/cost-estimate` — per-model per-resume estimate from `pricing.py`.
- `ChecklistOut` gains the four setup fields above.

Existing endpoints cover the rest: `/profile/blocks`, `/profile/tracks`, `/profile/answers`,
`/searches`, `/settings/sources`, `/settings/llm`, `/discovery/poll`.

No migration is required beyond the `ChecklistOut` additions, which are computed, not stored.

## 10. Testing

- **Parser**: a fixture resume yields expected block types, orgs and periods; a resume with no dates
  yields blocks with `period = None` and never a guessed date.
- **Verification**: imported blocks are `verified = false` without exception; a metric in an
  unverified block does not reach rendered output; the same block verified does.
- **Taxonomy**: a wizard-created track always carries a valid `field` and `role`.
- **Location validation**: a location returning zero is reported as invalid and not silently saved.
- **Empty states**: each row of §8 asserted against its real condition.
- **Wizard resumption**: leaving after screen 2 and returning preserves what was persisted.
- **E2E**: a Playwright run from empty profile to a poll returning at least one job.

## 11. Risks

1. **Untested providers** (§5) — the one blocking unknown.
2. **Parse quality varies by resume.** Every parsed block is shown for confirmation before it is
   written; nothing is persisted unreviewed.
3. **The wizard is a second path into the same state**, which can drift from the Profile editors.
   Mitigated by the wizard calling the same endpoints the editors call, never writing directly.
4. **A stranger without an API key cannot finish screen 1.** Accepted — it is the honest floor of a
   bring-your-own-key product, and saying so early is kinder than after the work.

## 12. Open question for implementation

Whether resume parsing is one LLM call returning all blocks, or one call per section. One call is
cheaper and simpler; per-section is more accurate on long resumes and gives better progress
feedback. Decide with a measurement against a real resume during implementation, not here.
