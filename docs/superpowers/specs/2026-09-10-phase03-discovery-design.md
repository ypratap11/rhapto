# Phase 0.3: Job discovery and track classification — design

Date: 2026-09-10. Status: approved in brainstorming; implementation plan to follow.
Builds on `2026-09-09-rhapto-architecture-design.md` (stages 1 to 3, merged to main at 530d719).

## 1. Goal

"Wake up to a scored queue." Rhapto polls the ATS boards of the companies on the user's watchlist and two
public aggregators, dedupes what it finds, classifies every job against the user's tracks with a 0 to 100 fit
score, and shows the result in the queue sorted by fit. Nothing is tailored and nothing is submitted without a
human action.

Decisions taken with the user:

- Discovery sources: watchlist companies via Greenhouse, Lever, and Ashby, plus the RemoteOK feed and the
  Hacker News "Who's Hiring" thread. Work at a Startup is out (no public API). LinkedIn and Indeed stay out of
  core per FR-1.6.
- Automation stops at classify and score. No auto-tailoring in 0.3.
- Architecture: the poller runs inside the existing arq worker (approach A), not a separate service.

## 2. Non-goals

Auto-tailoring, LLM judgment in scoring (FR-2.2's third signal is deferred), deadline or compensation
extraction, multi-user scheduling, SmartRecruiters and Workable adapters (schema enum keeps them; adapters are
the documented extension), any scraping of sites that forbid it.

## 3. Data model

One Alembic migration `0002_discovery`:

`jobs` (existing) gains:

| column | type | meaning |
|---|---|---|
| `external_id` | text, nullable | the source's posting id; `(user_id, source, external_id)` unique when not null |
| `posted_at` | timestamptz, nullable | as reported by the source |
| `best_track_id` | text, nullable | track with the highest score |
| `best_fit` | int, nullable | that score, 0 to 100 |
| `repost_of` | uuid FK jobs.id, nullable | set when a posting's dedupe hash matches an earlier job under a new external id |
| `rescued` | bool, default false | user moved a low-fit job into the fit bucket |

`tracks` (existing) gains `embedding` (vector, nullable): the cached embedding of the track description,
recomputed on every track PUT and on profile import.

`job_scores` (new): `job_id` FK cascade, `track_id` text, `fit_score` int, `rationale_json` jsonb,
`scored_at` timestamptz; unique `(job_id, track_id)`.

`poll_runs` (new): `id`, `user_id`, `source` text, `board` text nullable, `started_at`, `finished_at` nullable,
`found` int, `new` int, `error` text nullable. Index on `(user_id, source, board, started_at desc)`.

The `source` column on `jobs` takes the values `manual`, `url`, and each registered source name.

## 4. Profile schema changes

`watchlist.yaml`:

```yaml
watchlist:
  - { company: ExampleCo, source: greenhouse, board: exampleco, keywords: ["program manager"] }  # keywords optional
aggregators:
  - { source: remoteok, enabled: true, keywords: [] }      # empty list = union of all track keywords
  - { source: hn-hiring, enabled: true }
```

`packages/schemas/profile/watchlist.json` gains the optional `keywords` array per entry and the optional
`aggregators` list. The `source` enum for watchlist entries is generated from the board-source registry; the
aggregator enum from the aggregator registry. Pydantic models and TypeScript types regenerate through
`scripts/codegen.sh` as before. `tracks.yaml` is unchanged.

## 5. Sources

Package `apps/api/src/rhapto/engine/discovery/`:

```
discovery/
  __init__.py
  posting.py        Posting model (external_id, company, title, location, url, jd_text, posted_at)
  http.py           fetch_json(url) / fetch_text(url): SSRF guard, 5 MB cap, 20 s timeout, one retry
  sources/
    __init__.py     SOURCES registry: name -> class; BOARD_SOURCES, AGGREGATOR_SOURCES views
    base.py         Source protocol: name, kind ("board" | "aggregator"), async fetch(entry, keywords, http)
    greenhouse.py   boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true
    lever.py        api.lever.co/v0/postings/{board}?mode=json
    ashby.py        api.ashbyhq.com/posting-api/job-board/{board}
    remoteok.py     remoteok.com/api, filtered by keywords in title or tags
    hn_hiring.py    hn.algolia.com: newest "Ask HN: Who is hiring?" story, comments filtered by keywords
  dedupe.py         normalize_title, dedupe_hash (reuses db.hashing), repost detection
  scoring.py        score_job(jd_text, embedding, tracks, track_embeddings) -> list[TrackScore]
  poller.py         poll_sources(...) orchestration used by the worker task and the CLI
```

Rules for every adapter:

- Returns `Posting` objects only. HTML descriptions are converted to plain text with the existing
  `services/jobtext.py` extractor before leaving the adapter.
- Never raises for a single bad posting; skips it and counts it. Raises `SourceError` for a failed request,
  which the poller records on the run.
- Has a recorded fixture under `tests/fixtures/discovery/<source>.json` and passes the shared contract test
  (non-empty id, title, text; absolute https URL; no HTML tags; `posted_at` timezone-aware or None).

Adding a source: one module implementing the protocol, one registry entry, one fixture. The schema enums,
API validation, web dropdowns, poller, dedupe, scoring, and UI follow from the registry.

## 6. Scoring

Deterministic, no LLM call. For a job and each track:

- `semantic`: cosine similarity between the JD embedding and the embedding of `track.description` (falling
  back to the track name plus keywords when the description is empty). Track embeddings are computed once per
  profile version and cached in the `tracks` row (`embedding` vector column added in the same migration).
  Mapped linearly from cosine 0.20 to 0.80 onto 0 to 100 and clamped.
- `keywords`: `hits / len(track.keywords)` where a keyword found in the title counts 2 and in the text counts
  1, capped at 1.0, times 100. Matching reuses `engine/select.py: keyword_matches`.
- `fit_score = round(0.6 * semantic + 0.4 * keywords)`. Weights are module constants.
- `rationale_json = {"semantic": s, "keywords": k, "matched": [...], "weights": {...}}`.

Best track is the argmax; ties resolve by track order in the profile. `bucket` is `fit` when
`best_fit >= track.min_fit` or `rescued` is true, else `low`. Manual and URL jobs are scored on creation. Saving a track (PUT)
enqueues `rescore_jobs` for that user. Golden classification cases: `tests/golden/classification/` with 20
fictional JDs and expected `best_track` and `bucket` against `profile.example`.

## 7. Poller and scheduling

Worker additions (`worker/tasks.py`):

- `poll_all_sources(ctx)`: arq cron every `RHAPTO_POLL_INTERVAL_HOURS` (default 6, 0 disables). For each user
  (single user today): load watchlist and aggregators from the database, run `poll_sources`.
- `poll_now(ctx, task_id)`: the same, enqueued by the API; progresses through the existing task and SSE
  machinery with steps `fetch`, `dedupe`, `score`, `done`.
- `rescore_jobs(ctx, user_id)`: recompute `job_scores`, `best_track_id`, `best_fit` for all jobs.

`poll_sources` per source entry: open a `poll_runs` row, fetch with a 20 s timeout, dedupe, insert new jobs
(`source`, `external_id`, `url`, `jd_text`, `posted_at`, `discovered_at = now`), embed and score them, close
the run with `found`, `new`, and `error`. Failures of one source never abort the run. A source entry whose last
three runs errored is skipped with `error = "paused after 3 failures"` until its watchlist entry is saved again.
After the run, publish `discovery.finished {new: n}` on the event bus.

Dedupe order: `(source, external_id)` exact match means already known, skip. Otherwise compute the existing
company plus normalized title plus location hash; a match under a different external id inserts the job with
`repost_of` pointing at the earlier one and marks it in the UI; it does not create an application row.

## 8. API

All under the existing bearer auth and RFC 7807 errors.

- `POST /api/v1/discovery/poll` → 202 `{task_id}`; enqueues `poll_now`.
- `GET /api/v1/discovery/runs` → latest `poll_runs` row per `(source, board)`.
- `GET /api/v1/discovery/sources` → registry metadata (name, kind, needs_board) for the web forms.
- `GET /api/v1/jobs` gains `track: str | None`, `bucket: "fit" | "low" | None`, `sort: "fit" | "newest"`
  (default `fit`). `JobOut` gains `source`, `best_track_id`, `best_fit`, `bucket`, `repost_of`, `posted_at`,
  and `scores: list[{track_id, fit_score, rationale}]`.
- `POST /api/v1/jobs/{id}/rescue` → sets a `rescued: bool` flag on the job so it lists in the fit bucket.
- Profile watchlist endpoints accept the new fields; `PUT /api/v1/profile/tracks/{id}` enqueues `rescore_jobs`.

## 9. Web

Queue (`/`): fit badge (score and track name; bands: 75+ green, `min_fit`..74 amber, below slate), source
chip, re-post marker, filter bar (track select, Fit / Low fit toggle, sort toggle), "Poll now" button with the
existing step progress and a refresh on `done`, status line "Last poll 2h ago, 3 new" opening a runs drawer
with per-source results and errors, "Rescue" on low-fit cards, and Tailor preselecting the best track.

Profile (`/profile`): Watchlist tab gains a keywords column and an Aggregators section (switches per aggregator
plus a shared keyword field, placeholder showing the track-keyword default). Sources and aggregator lists come
from `GET /discovery/sources`.

Pipeline: unchanged. Discovered jobs do not create application rows until the user acts.

## 10. CLI

- `rhapto discover --profile ./profile [--source S --board B] [--out jobs.json]`: one poll against the
  profile's watchlist (or a single source), prints new postings with best track and score. Uses the same
  `poll_sources` with an in-memory store when no database is configured.
- `rhapto score --jd file --profile ./profile`: prints the per-track breakdown for one JD.

## 11. Configuration

`.env.example` gains `RHAPTO_POLL_INTERVAL_HOURS=6` and `RHAPTO_DISCOVERY_USER_AGENT="rhapto-discovery/0.3"`
(users who publish a fork can point it at their repository).
Vendor APIs are called with that user agent, a 20 s timeout, and one retry on 5xx. No API keys are needed for
any of the five sources.

## 12. Testing

- Unit: adapter contract test parametrized over the registry with recorded fixtures; scorer with a fake
  embedder (band mapping, keyword weighting, threshold, tie order); dedupe and repost; pause-after-three rule;
  poller orchestration with a fake source that raises.
- Golden: 20 classification cases.
- API: poll enqueue, runs listing, jobs filters and sort, rescue, manual job scoring, track PUT rescoring.
- Web: filter bar, fit badge bands, poll-now flow, runs drawer, watchlist aggregator form.
- Smoke: `scripts/smoke-api.sh` gains a `discover` step against a local fixture HTTP server started by the
  script; CI never calls a vendor API.

## 13. Error handling and safety

- Every network fetch goes through `discovery/http.py`: SSRF guard (public IPs only), size cap, timeout.
- A failing source is recorded, surfaced, and paused after three consecutive failures; it never blocks others.
- Postings with empty descriptions are stored with `jd_text` set to the title and location and flagged in the
  rationale so the user knows the score is weak.
- No code path here submits an application. Discovery creates jobs, not applications.

## 14. Open questions resolved

- Poll interval default 6 hours; user-configurable via environment and the UI's Poll now.
- Aggregator keyword default: union of all track keywords.
- Re-posts flagged, not re-queued (FR-1.5).
- Track filter on the queue arrives here, as noted in the stage 3 follow-ups.
