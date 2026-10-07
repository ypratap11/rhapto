# Search quality: every user scored, role-first ranking, a clean top of the list

Date: 2026-10-07. Status: revision 3, after the architect review and re-review
(`.superpowers/sdd/search-quality/architecture-review.md`, APPROVED WITH CONDITIONS; every condition
is addressed below and traced in section 9).
Sub-project 1 of the tester-feedback work; the coach (`/start`) and the lighter homepage follow it
and depend on it, because the coach leads with "jobs for you".

## 1. Why

Testers (October validation round) said search gives **wrong roles** and **too few / empty**
results. A read-only probe of production on 2026-10-07 (8 accounts, pseudonymised U1-U8) showed
the pool is not the problem -- each account holds 1,500-2,900 jobs, skewed to engineering and
program/project management, which is what the testers want. The ranking and the setup are:

| # | Finding (probe evidence) | Effect |
|---|---|---|
| 1 | U6, U7 have no tracks -> 0 of 2,522 jobs scored; their list is newest-first. U3 has 138 of 1,813 scored, cause unknown. | 3 of 7 testers see an unranked list presented as their jobs |
| 2 | Fit matches topic, not role: an AI-program-manager track ranks "Agentic AI Engineer" and "Senior Software Engineer, GenAI" at 70-72; the QA track ranks "Flight Test", "Mechanical Test", "Head of Consulting". | wrong roles |
| 3 | One Lever board (Shield AI) fills most of the top 15 for U2, U5, U8. | wrong roles, looks broken |
| 4 | The same posting 6x in U1's top 15; HN titles that are locations ("Remote (US only)", "Santa Clara, CA and Berlin, Germany"). | looks broken |
| 5 | Scores sit in 30-60 while tracks require 60: QA tester has 4 jobs >= 50 of 2,687; the PM/Scrum tester's best is 69. | too few |

All 13 tracks in production carry a taxonomy `field` and `role` (probe section 2), so no current
account mixes hand-written and role tracks.

Today: `fit = round(0.6 * semantic + 0.4 * keywords)`, then `round(fit * location_multiplier)`
(`engine/scoring.py:453,457`). `semantic` is a bge-small cosine over `title + jd_text`, dominated by
the description. `keywords` counts 2 for a keyword in the title and 1 for one only in the text
(`engine/scoring.py:17,401-404`), divided by the number of keywords -- so with 7 keywords a single
title hit moves the fit by about 11 points. Nothing asks whether the job's title *is* the role.

## 2. Goals and non-goals

Goals:
- Every account with a target role has every scorable job scored; an account without one is told
  so instead of being shown an unranked list as if it were ranked.
- A job whose title is not the user's role ranks below the jobs whose title is.
- The top of the list has no duplicates, no single-company flood, and no location-as-title rows.
- Measured before/after on the real production data, judged blind (section 6).

Non-goals (October): new job sources or paid keys, LLM re-ranking, seniority matching, the coach and
the role-from-resume derivation (sub-project 2), changing the location multiplier, changing live
search's phrase matching, a "why this score" UI (rationale data is recorded, the UI is later).

## 3. A -- every user scored

**A1. Find why U3 stalled at 138 / 1,813, and fix it.** Root-cause first (systematic debugging) on a
reproduction, not by guessing. Leading candidates, both from the code:
- *Rollback expiry.* `score_and_store` in incremental mode calls `session.rollback()` after a failed
  chunk and continues (`services/scoring.py:141-156`). A rollback expires every loaded ORM instance;
  the next chunk then reads `job.jd_embedding` (`services/scoring.py:72`) on an expired `Job`, an
  implicit lazy load that raises in an `AsyncSession`. If so, every chunk after the first failure
  fails. The existing test (`tests/unit/test_scoring_service.py:178-207`) fails only the last chunk,
  so it cannot see this.
- *Concurrent rescores.* `rescore_jobs` is enqueued with no arq `_job_id`
  (`services/enqueue.py:52-54`) and the worker runs `max_jobs = 2` (`worker/main.py:82`). Saving two
  roles in a row runs two full rescores for one user at once, both upserting into
  `UNIQUE (user_id, job_id, track_id)` -- which produces chunk failures, which hit the path above.

Required regardless of which is the cause:
- a test with 3 or more chunks that fails the **middle** chunk and asserts the third is scored;
- one user's rescores never run in parallel, and none is ever dropped. Not via arq `_job_id`: that
  silently discards any enqueue while one is queued, running, or for `keep_result` after it (re-review
  R-1), so a second role saved in that window would never be scored. Instead `rescore_jobs` tries a
  **non-blocking, session-level** Postgres advisory lock keyed on the user, in its own key namespace
  (distinct from the poll's `with_user_poll_lock`, `worker/tasks.py:76`), on a dedicated connection
  held for the whole run -- session-level because `commit_each_chunk` commits would release a
  transaction-level lock after the first chunk. If the lock is held, the task re-enqueues itself
  deferred by ~30 s (no `_job_id`) and returns, so it neither occupies one of the two worker slots
  nor burns its 600 s timeout waiting (revision-3 review R3-1). The lock is released and the
  connection invalidated in `finally`. A re-run recomputes from the then-current tracks. A test
  proves two concurrent rescores for one user serialise and both complete.

**A2. No target role = say so.** For an account with zero tracks, the Jobs page and the dashboard's
recommendations show a short prompt -- "Pick the role you want and we'll rank these for you" -- with
a button to the existing role picker, and the list beneath is labelled "Newest jobs, not ranked
yet". No API change: both pages already call `useTracks()` (`app/jobs/page.tsx:78`,
`app/dashboard/page.tsx:27`). The coach will later fill the role in from the resume; this prompt
is the fallback.

**A3. Deleting a track rescores.** `DELETE /profile/tracks/{id}` (`routers/profile.py:186-191`)
today leaves `best_fit`, `best_track_id` and that track's `job_scores` rows in place, so a user who
deletes their last track keeps a stale ordering that A2 would mislabel. The delete now also deletes
that track's `job_scores` rows and enqueues `rescore_jobs` (deduplicated as in A1); with no tracks
left, the rescore clears `best_fit` (`services/scoring.py:78-79`).

(Scoring the bootstrap backfill was dropped from revision 1: bootstrap runs once, on a brand-new
account that has no tracks yet, so it would never fire. A2 plus the existing rescore on track save
cover it.)

## 4. B -- role-first ranking

**B1. Job titles per role, with exclusions.** Each role in `packages/schemas/taxonomy.yaml` gains:
- `titles`: job-title phrases that mean this role;
- `exclude_titles` (optional): words or phrases that, when present in the title, mean it is *not* this
  role even though a `titles` phrase matched.

A title is a match when it contains a `titles` phrase **and** no `exclude_titles` phrase. Matching
reuses `keyword_matches` (whole word, case-insensitive, `engine/select.py:50-56`). Examples (the plan
drafts all 63 roles; the owner reviews them):

```yaml
- id: qa
  titles: [QA engineer, QA analyst, quality assurance, quality engineer, test engineer, SDET,
           test automation engineer, software tester]
  exclude_titles: [mechanical, flight, hardware, manufacturing, supplier, structural, electrical,
                   chemical, civil, construction, clinical, food safety]
- id: technical-program-manager
  titles: [technical program manager, TPM, program manager]
  exclude_titles: [construction, clinical, nursing, facilities, real estate, manufacturing]
- id: project-manager
  titles: [project manager, project lead, project coordinator, delivery manager]
  exclude_titles: [construction, civil, electrical, mechanical, field, site, clinical]
- id: scrum-master
  titles: [scrum master, agile coach, agile delivery lead]
```

`packages/schemas/taxonomy.json` gets both fields as **optional** arrays of strings (default empty),
so a custom `RHAPTO_TAXONOMY_PATH` file without them still loads; `scripts/codegen.sh` regenerates
`models/taxonomy.py`, `openapi.json` and the web's `schema.d.ts`. The shipped taxonomy gives every role
a non-empty `titles` (a test asserts this). `tests/unit/test_taxonomy.py` fixtures gain the fields.

**B2. Title score, and when it applies.** `services/scoring.py` resolves each track's phrases through
`services.taxonomy.find_role(field, role)` (`services/taxonomy.py:98`) and passes them to
`engine.score_job`; `engine/` stays free of service imports. `title = 100` on a match, else `0`. The
role-first blend (B3) applies only when **all** of these hold; otherwise the track is scored with
today's blend, unchanged:
- the track has a `role`, and `find_role` returns it (a role id removed from the taxonomy falls back);
- that role has a non-empty `titles`;
- the taxonomy loaded (a `TaxonomyError` in the worker is logged once per run and every track falls
  back -- it never stops scoring);
- the job has a non-empty title (a hand-added job with no title is not penalised for it).

Mixed accounts (a hand-written track beside a role track) are possible: `best_track` takes the
maximum (`engine/scoring.py:468-471`), so the hand-written track's old-blend score can lift a
wrong-role job. None exist today (section 1); the evaluation includes a synthetic one so the effect is
measured, not assumed.

**B3. The blend.**

```
raw  = 0.45 * title + 0.35 * semantic + 0.20 * keywords
fit  = round(raw * location_multiplier)
if title == 0: fit = min(fit, TITLE_MISS_CAP)        # TITLE_MISS_CAP = 45, applied last
```

The cap is applied **after** the location multiplier, so 45 is a true ceiling. Worked numbers for a
title match with an ordinary description (semantic 50, keywords 30, raw 68.5): `preferred` 68,
`remote` 65, `unknown` 62, `country` 58 (Python rounds half to even; multipliers at
`engine/scoring.py:25`, waived for users with no location preference, `:421-432`). So for a user with
a location preference, a US-but-not-preferred title match can still sit just under `min_fit` 60;
section 6 reports matches-above-`min_fit` per tier so the weights are tuned on that evidence, never
by eye.

What the cap does in today's UI (the review corrected revision 1 here): neither list filters on
`min_fit`. The Jobs page's fit filter defaults to "all" and uses fixed 75/60 thresholds client-side
(`search-state.ts:32,61-66`); the dashboard's recommendations are `GET /jobs?recommended=true&sort=fit`
(`queries.ts:962`) and `_recommended_clause` has no fit condition (`db/repositories/jobs.py:279-284`).
Capped jobs therefore **sort lower**; they are not removed. In addition, `recommended=true` now
excludes scored jobs with `best_fit <= TITLE_MISS_CAP`, so the dashboard's recommendations hold only
title matches (or old-blend tracks' jobs above 45).

**B4. Record why.** `TrackScore` gains `title_match: str | None` (the phrase that matched) and
`blend: "role" | "legacy"`, stored in the existing `rationale_json` (JSONB, no migration). `rationale()`
stops hard-coding the old weights (`engine/scoring.py:492`) and reports the blend actually used.

**B5. Rescore everyone, safely.** After the preview passes (section 6), every account is rescored with
the existing `rescore_jobs` (local embeddings, no model cost; job embeddings are reused).
- Accounts are enqueued one at a time; per-user runs are serialised (A1).
- **Before** B5, the plan times one real-size rescore on the droplet (the largest account, ~2.9k jobs)
  against arq's `job_timeout = 600` (`worker/main.py:83`). A timeout cancels the coroutine mid-queue
  and would leave that account's tail on the old scale. If the measured time is not comfortably
  under 600 s, the plan raises the timeout for `rescore_jobs` or splits the work into per-chunk tasks
  before B5 runs.
- A title-list change only takes effect after a rescore and an image rebuild (the taxonomy is copied
  at build, `apps/api/Dockerfile:13`, and `lru_cache`d, `services/taxonomy.py:86`); the rollout
  checklist says so.

## 5. C -- a clean top of the list

**Where it applies:** `GET /jobs` when `sort=relevance` (the Jobs page default) **or**
`recommended=true` (the dashboard, which sorts by fit). It does **not** apply when the request carries
`ids=` (live search re-fetches its results that way, `queries.ts:731`, and must get every row it asked
for). Other sorts are untouched.

**How:** one pure Python function, `arrange(jobs, *, sort)`, applied after `repo.list_jobs` over the
full list (`GET /jobs` has no pagination, `api/routers/jobs.py:246-248`; both clients page on the
client side). The same function is what the preview (section 6) calls, so what is evaluated is what
ships. `empty-reason`'s counts stay pre-collapse.

**C1. Collapse duplicates.** Jobs with the same normalised company and title (lower-case, collapsed
whitespace, trailing requisition ids like "(R5803)" stripped) show as one row: the one that ranks
highest under the request's own ordering (relevance key or fit), ties to the newest. The row carries
`also_ids: list[UUID]` (the others, additive to `JobOut`, computed not stored). The web shows
"+N similar postings" and opens them with the existing `GET /jobs?ids=…` (capped at 200,
`api/routers/jobs.py:45-59`). The label says "similar postings", not "locations", because copies can
come from different sources.

**C2. At most two per company at the top.** After C1, within the request's ordering, a company's third
and later rows sort after every row that is within the first two of its own company. Nothing is
removed.

**C3. HN titles.** `parse_header` (`services/discovery/sources/hn_hiring.py:22-27`) picks the role from
the segments after the company, skipping a segment that reads as a location or work mode: it contains
remote / onsite / hybrid / visa, or a place from `engine/scoring.py`'s `US_STATES`, `NON_US_COUNTRIES`
or `NON_US_CITIES` (two-letter state codes matched case-sensitively, so "Software Engineer,
Infrastructure" is not taken for a place). If no segment qualifies, the posting is skipped. Existing
junk rows cannot be re-parsed -- `jd_text` is stored without the header line (`hn_hiring.py:52-53`) --
so they age out under the 90-day window.

## 6. How we know it worked

**`rhapto rank-preview`** (a new top-level CLI command; `rhapto score` already exists,
`cli/main.py:569`). For every account with tracks it prints, per pseudonymous user, the top 15 under
the current scores and under the new ones, each **with and without** `arrange`, so the blend's effect
is not confounded with de-duplication.
- New scores are computed with the same `engine.score_job` the worker uses, from track embeddings
  computed in memory, and ordered with `arrange`.
- The relevance ordering today exists only in SQL (`db/repositories/jobs.py:440-458`), which the
  preview cannot apply to in-memory scores (re-review R-2). So the relevance key becomes one Python
  function, `relevance_key(job, now)`, used by the preview, and a **parity test** runs the SQL ordering
  and the Python key over the same fixture set (mixed ages past the 90-day cap, NULL fits, ties) and
  asserts an identical order. The SQL stays as the production path; the test fails if either drifts.
- It runs inside `SET TRANSACTION READ ONLY` and rolls back, so any accidental flush raises; a test
  proves the database is byte-for-byte unchanged after a run.
- Pseudonyms reuse the HMAC scheme of `rhapto feedback report` (`cli/main.py:278-290`); no emails.
- It is CLI-only, run on the server over SSH. It reads all accounts, so it never gets an HTTP route.

**Blind judging.** For each tester with a role, the old and new top 15 are shuffled and labelled X and
Y. A judge who did not write the code (a fresh subagent; the owner spot-checks two testers) sees
company, title, location and a ~300-character description excerpt for each job, plus the tester's role
names, and marks each job relevant or not. It never sees the title-phrase lists, so it does not share
their blind spots. A synthetic mixed account (one hand-written track beside one role track) is
included.

**Acceptance** (raw per-tester counts are reported; about five testers have roles, so it is a small
gate):
- every tester with a role: new list >= 10 of 15 relevant, and no tester's count goes down;
- no duplicate (C1) and at most two per company (C2) in any new arranged top 15;
- after A1 and once the queue is idle: zero accounts with tracks that have unscored jobs, excluding
  jobs the scorer skips by design (`jd_embedding` is None, `services/scoring.py:78`);
- reported, not gated: jobs >= `min_fit` per tester, before vs after, split by location tier.

**Unit tests from known-bad inputs.** Each negative test uses a title that **contains an accepted
phrase**, and each is shown to fail when the role's `exclude_titles` is removed:
- `qa` vs "Flight Test Engineer", "Mechanical Test Engineer", "Supplier Quality Engineer": <= 45;
- `technical-program-manager` vs "Program Manager, Construction": <= 45;
- `technical-program-manager` vs "Agentic AI Engineer" (no accepted phrase): <= 45;
- positives with an ordinary description at `preferred` tier: "Senior QA Engineer",
  "Technical Program Manager, Platform" >= 60;
- fallbacks: a track with a stale role id, a taxonomy load failure, and a job with no title all score
  exactly as today's blend;
- HN: "Remote (US only)" and "Santa Clara, CA and Berlin, Germany" never become a title;
  "Acme | Software Engineer, Infrastructure | NYC" keeps its role;
- `arrange`: six copies of one posting -> one row with five `also_ids`; a company's third row sorts
  after the others' first two; an `ids=` request is returned unarranged;
- scoring: 3 chunks, middle one fails, third is scored; two concurrent rescores for one user
  serialise and both complete (A1).

## 7. Rollout

Branch -> PR -> merge -> deploy to the droplet (`git archive` + `docker compose build && up -d`;
the rebuild is what picks up the new taxonomy) -> time one real-size rescore (B5) -> `rhapto
rank-preview`, judged -> only if accepted, rescore every account, one at a time -> rerun the probe and
show the owner the before/after. If the judged result fails, the blend or the title lists are tuned
and the preview rerun; production is not rescored until it passes. The deploy and the rescore are
each confirmed with the owner first.

## 8. Risks

- **Title lists too narrow** -> real matches capped (e.g. "Release Manager" for a delivery lead).
  Mitigated by owner review of the lists, the blind judging, and capped jobs only sorting lower.
- **Exclusions too broad** -> a real match excluded (e.g. "Hardware QA" for someone who wants it). The
  same review and judging catch it; exclusions are per role, so a fix is one line.
- **Mixed accounts** defeat the cap through `best_track`'s maximum; none exist today, and the synthetic
  account in section 6 measures it.
- **Collapsing hides a genuinely different job** with an identical title at the same company; it is one
  click away through "+N similar postings".

## 9. Architect conditions -> where addressed

C-1 exclusions and true negative tests: B1, section 6 unit tests. I-1: A1. I-2: B3 worked numbers and
per-tier reporting. I-3: B3 "What the cap does". I-4: section 5 "Where it applies" / "How". I-5: C1
`also_ids`. I-6: B2 fallbacks, mixed accounts. I-7: A3. I-8: section 6 `rank-preview`. Re-review R-1 and R3-1: A1 non-blocking advisory lock with deferred re-enqueue. R-2: section 6 `relevance_key` parity test. I-9: B5.
M-1: C3 place lists. M-2: C3 age-out. M-3: B4, UI moved to non-goals. M-4: B1 fixtures, B5 rebuild and
rescore. M-5: A2 dropped. M-6: acceptance. M-7: C1 representative, with/without `arrange`. M-8: section
1, verified on the probe.
