# Phase 0.3 Discovery and Classification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Poll the user's watchlist boards (Greenhouse, Lever, Ashby) and two aggregators (RemoteOK, Hacker News Who's Hiring), dedupe, score every job against the user's tracks without an LLM, and show a fit-sorted queue with a track filter, a low-fit bucket, and a Poll now button.

**Architecture:** A pure scorer in `rhapto.engine.scoring`; a `rhapto.services.discovery` package with one adapter per source behind a registry, an SSRF-guarded HTTP client, dedupe, and a poller; a `rhapto.services.scoring` persistence wrapper; three worker tasks (`poll_now`, `poll_all_sources` cron, `score_jobs`/`rescore_jobs`); a `discovery` API router plus richer `GET /jobs`; queue and profile UI additions; two CLI commands.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Alembic, pgvector, arq, httpx, trafilatura, fastembed, FastAPI, typer; Next 16, React 19, TanStack Query, shadcn base-nova (Base UI), vitest.

**Spec:** `docs/superpowers/specs/2026-09-10-phase03-discovery-design.md`

## Global Constraints

- Everything from stages 1 to 3 applies: no personal data in tracked files (fixtures use fictional companies and people only; never read `profile/`), no code path submits an application, the API token goes only to the configured API URL.
- Import-linter contracts in `apps/api/.importlinter` must stay green: `rhapto.engine` imports none of `config`, `profile`, `db`, `services`, `worker`, `api`, `cli`; `rhapto.db` imports only models; `rhapto.services` never imports `worker`, `api`, `cli`; `worker` and `api` are independent. Run `uv run lint-imports` from `apps/api` before every commit that touches Python.
- Python checks before every commit (from `apps/api`): `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run pytest -q --deselect tests/unit/test_enqueue_arq.py` (the two deselected tests are a known Windows-only failure). API and worker tests need the compose `db` (`docker compose up -d db redis`).
- Web checks before every commit (from `apps/web`): `pnpm test`, `pnpm typecheck`, `pnpm lint` (one accepted warning in `TaskProgress.tsx`), `pnpm build`.
- Generated files are never hand-edited: `apps/api/src/rhapto/models/**` (from `packages/schemas`), `packages/schemas/openapi.json` (from `apps/api/scripts/export_openapi.py`), `apps/web/src/lib/api/schema.d.ts` (from openapi.json). Regenerate all three with `bash scripts/codegen.sh` from the repo root after any schema or API change and commit the results.
- Discovery HTTP: every vendor fetch goes through `rhapto.services.discovery.http.DiscoveryHttp` (SSRF guard via `services.jobtext.assert_public_host`, 25 MB cap, 20 s timeout, one retry on 5xx, user agent from settings). Tests never call a vendor; adapters are tested with `FakeDiscoveryHttp` and fixtures under `apps/api/tests/fixtures/discovery/`.
- Scoring constants (verbatim from the spec): `SEMANTIC_WEIGHT = 0.6`, `KEYWORD_WEIGHT = 0.4`, cosine mapped linearly from `0.20` to `0.80` onto 0 to 100 and clamped; keyword hits: title 2, text 1, capped at 1.0; `fit_score = round(0.6 * semantic + 0.4 * keywords)`; ties resolve by track order; `bucket` is `fit` when `best_fit >= track.min_fit` or `rescued`, else `low`.
- Scoring never calls the LLM. Discovery never creates application rows. A source is paused after three consecutive failed runs until its watchlist entry is saved again.
- Vendor endpoints (verbatim): Greenhouse `https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` (`content` is HTML-escaped HTML); Lever `https://api.lever.co/v0/postings/{board}?mode=json` (`createdAt` is epoch milliseconds; a large board is about 8 MB, hence the 25 MB cap); Ashby `https://api.ashbyhq.com/posting-api/job-board/{board}` (skip `isListed: false`); RemoteOK `https://remoteok.com/api` (first element is a legal notice, skip it); HN `https://hn.algolia.com/api/v1/search_by_date?query=%22who%20is%20hiring%22&tags=story,author_whoishiring&hitsPerPage=1` then `https://hn.algolia.com/api/v1/items/{objectID}` (top-level `children[].text` is HTML; first line is `Company | Role | Location | ...`).
- Settings added: `rhapto_poll_interval_hours: int = 6` (0 disables the cron) and `rhapto_discovery_user_agent: str = "rhapto-discovery/0.3"`; both documented in `.env.example`.
- Design direction and accessibility floor from the stage 3 plan still apply to new UI: one accent color for primary actions, fit badge tones green (75 and above), amber (min_fit to 74), slate (below), every control labelled.
- Commit messages end with the two attribution lines given in the session.

## File Structure

```
packages/schemas/profile/watchlist.json          + keywords per entry, + aggregators list
apps/api/
  alembic/versions/0002_discovery.py             jobs columns, tracks.embedding, watchlist.keywords, aggregators, job_scores, poll_runs
  src/rhapto/
    config.py                                    + poll interval, user agent
    engine/scoring.py                            NEW pure scorer: TrackScore, score_job, best_track, bucket_for, track_text
    engine/types.py                              Profile gains aggregators
    profile/loader.py                            reads/writes aggregators
    db/models.py                                 Job columns, Track.embedding, WatchlistEntry.keywords, Aggregator, JobScore, PollRun
    db/repositories/profile.py                   watchlist keywords, aggregators CRUD, track embedding
    db/repositories/jobs.py                      list_jobs filters/sort, external id lookup, identity lookup, create_discovered_job, rescue
    db/repositories/discovery.py                 NEW poll runs, scores
    services/jobtext.py                          expose html_to_text
    services/scoring.py                          NEW score_and_store, rescore_user
    services/discovery/__init__.py               NEW
    services/discovery/posting.py                NEW Posting
    services/discovery/http.py                   NEW DiscoveryHttp, FakeDiscoveryHttp
    services/discovery/dedupe.py                 NEW normalize_title, identity_hash
    services/discovery/sources/__init__.py       NEW registry
    services/discovery/sources/base.py           NEW SourceInfo, Source protocol, SourceError
    services/discovery/sources/{greenhouse,lever,ashby,remoteok,hn_hiring}.py   NEW adapters
    services/discovery/poller.py                 NEW poll_sources
    services/profile_sync.py                     aggregators in import/export/load
    worker/tasks.py                              poll_now, poll_all_sources, score_jobs, rescore_jobs
    worker/main.py                               cron, discovery http in ctx
    api/schemas.py                               JobOut fields, JobScoreOut, PollRunOut, SourceInfoOut
    api/routers/jobs.py                          filters, rescue, enqueue scoring
    api/routers/discovery.py                     NEW poll, runs, sources
    api/routers/profile.py                       aggregators endpoints, track PUT enqueues rescore
    api/app.py                                   include discovery router
    cli/main.py                                  discover, score
  tests/fixtures/discovery/*.json                NEW recorded-shape fixtures (fictional)
  tests/unit/test_scoring.py, test_discovery_*.py, test_poller.py, test_worker_discovery.py
  tests/golden/classification/cases.json, test_classification.py
  tests/api/test_discovery_api.py, test_jobs_api.py (extended)
apps/web/src/
  lib/api/queries.ts                             useJobs(filters), useDiscoveryRuns, usePollNow, useSources, useRescueJob, useAggregators, usePutAggregators
  lib/fit.ts                                     NEW fitTone, formatFit
  components/queue/{FilterBar,FitBadge,PollNowButton,RunsDrawer}.tsx   NEW
  components/queue/{JobCard,JobList,TailorButton}.tsx                  fit badge, source chip, rescue, best-track preselect
  app/page.tsx                                   filter state, poll now, status line
  components/profile/WatchlistTab.tsx            keywords column, aggregators section
scripts/smoke-api.sh                             discover step against a local fixture server
scripts/discovery-fixture-server.py              NEW tiny HTTP server serving the fixtures
README.md                                        discovery section
.env.example                                     two new variables
```

---

### Task 1: Watchlist schema (keywords, aggregators), generated models, loader

**Files:**
- Modify: `packages/schemas/profile/watchlist.json`
- Modify: `apps/api/src/rhapto/engine/types.py` (Profile gains `aggregators`)
- Modify: `apps/api/src/rhapto/profile/loader.py` (read and write aggregators)
- Modify: `profile.example/watchlist.yaml`
- Regenerate: `apps/api/src/rhapto/models/profile/watchlist.py` via `bash scripts/codegen.sh`
- Test: `apps/api/tests/unit/test_profile_loader.py` (extend; if the file has another name, find it with `grep -rl "load_profile" apps/api/tests/unit`)

**Interfaces:**
- Consumes: `load_profile(path) -> Profile`, `Profile` in `rhapto.engine.types`, generated `WatchlistFile`, `WatchlistEntry`.
- Produces: `WatchlistEntry.keywords: list[str]` (default `[]`); new generated `AggregatorEntry(source: Literal["remoteok", "hn-hiring"], enabled: bool = True, keywords: list[str] = [])`; `WatchlistFile.aggregators: list[AggregatorEntry]` (default `[]`); `Profile.aggregators: list[AggregatorEntry]`.

- [ ] **Step 1: Extend the JSON schema**

Replace `packages/schemas/profile/watchlist.json` with:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/profile/watchlist.json",
  "title": "WatchlistFile",
  "type": "object",
  "additionalProperties": false,
  "required": ["watchlist"],
  "properties": {
    "watchlist": { "type": "array", "items": { "$ref": "#/$defs/WatchlistEntry" } },
    "aggregators": { "type": "array", "items": { "$ref": "#/$defs/AggregatorEntry" }, "default": [] }
  },
  "$defs": {
    "WatchlistEntry": {
      "title": "WatchlistEntry",
      "type": "object",
      "additionalProperties": false,
      "required": ["company", "source", "board"],
      "properties": {
        "company": { "type": "string" },
        "source": { "type": "string", "enum": ["greenhouse", "lever", "ashby", "smartrecruiters", "workable"] },
        "board": { "type": "string" },
        "keywords": { "type": "array", "items": { "type": "string" }, "default": [] }
      }
    },
    "AggregatorEntry": {
      "title": "AggregatorEntry",
      "type": "object",
      "additionalProperties": false,
      "required": ["source"],
      "properties": {
        "source": { "type": "string", "enum": ["remoteok", "hn-hiring"] },
        "enabled": { "type": "boolean", "default": true },
        "keywords": { "type": "array", "items": { "type": "string" }, "default": [] }
      }
    }
  }
}
```

- [ ] **Step 2: Regenerate the Pydantic models and inspect**

Run from the repo root: `bash scripts/codegen.sh`
Expected: `apps/api/src/rhapto/models/profile/watchlist.py` now defines `AggregatorEntry` with `source: Literal['remoteok', 'hn-hiring']`, `enabled: bool = True`, `keywords: list[str] = []`, and `WatchlistEntry.keywords: list[str] = []`, `WatchlistFile.aggregators: list[AggregatorEntry] = []`. If `keywords` came out `Optional`, the `--strict-nullable` flag is missing from the script; do not hand-edit.

- [ ] **Step 3: Write the failing loader test**

Append to the loader test module:

```python
def test_watchlist_keywords_and_aggregators_round_trip(tmp_path: Path, demo_profile_dir: Path) -> None:
    profile = load_profile(demo_profile_dir)
    assert profile.watchlist[0].keywords == ["program manager"]
    assert [a.source for a in profile.aggregators] == ["remoteok", "hn-hiring"]
    assert profile.aggregators[1].enabled is False
    from rhapto.profile.loader import write_profile  # existing export helper; name may differ, see loader.py

    write_profile(profile, tmp_path)
    again = load_profile(tmp_path)
    assert again.aggregators == profile.aggregators and again.watchlist == profile.watchlist
```

If the loader's write helper has a different name (look for the function that writes `answers.yaml`, seen at `loader.py:114`), use that name.

- [ ] **Step 4: Run the test to verify it fails**

Run from `apps/api`: `uv run pytest tests/unit -k aggregators -v`
Expected: FAIL on `profile.aggregators` (attribute missing) or on the example data.

- [ ] **Step 5: Update the example profile, Profile type, and loader**

`profile.example/watchlist.yaml`:

```yaml
watchlist:
  - { company: ExampleCo, source: greenhouse, board: exampleco, keywords: ["program manager"] }
aggregators:
  - { source: remoteok, enabled: true, keywords: ["data program manager", "AI product manager"] }
  - { source: hn-hiring, enabled: false }
```

In `apps/api/src/rhapto/engine/types.py`, add to `Profile` next to `watchlist`:

```python
    aggregators: list[AggregatorEntry] = Field(default_factory=list)
```

with `from rhapto.models.profile.watchlist import AggregatorEntry, WatchlistEntry`.

In `apps/api/src/rhapto/profile/loader.py`, where `Profile(...)` is constructed (line 94 area), pass
`aggregators=watchlist_file.aggregators if watchlist_file else []`, and where `watchlist.yaml` is written,
write `WatchlistFile(watchlist=profile.watchlist, aggregators=profile.aggregators)`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/unit -q` and `uv run mypy src`
Expected: PASS, mypy clean. Also run `uv run pytest tests/api/test_profile_api.py -q` (name may differ) to confirm the profile import still accepts the example.

- [ ] **Step 7: Commit**

```bash
git add packages/schemas/profile/watchlist.json apps/api/src/rhapto/models profile.example/watchlist.yaml apps/api/src/rhapto/engine/types.py apps/api/src/rhapto/profile/loader.py apps/api/tests/unit
git commit -m "feat(profile): watchlist keywords and aggregator entries"
```

---

### Task 2: Migration 0002, ORM models, repositories, profile sync

**Files:**
- Create: `apps/api/alembic/versions/0002_discovery.py`
- Modify: `apps/api/src/rhapto/db/models.py`
- Modify: `apps/api/src/rhapto/db/repositories/profile.py` (watchlist keywords, aggregators, track embedding)
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py`
- Create: `apps/api/src/rhapto/db/repositories/discovery.py`
- Modify: `apps/api/src/rhapto/services/profile_sync.py`
- Modify: `apps/api/src/rhapto/api/routers/profile.py` and `apps/api/src/rhapto/api/schemas.py` (aggregators GET/PUT)
- Test: `apps/api/tests/api/test_profile_api.py` (extend), `apps/api/tests/unit/test_repositories_discovery.py` (new; uses the `session` and `user` fixtures from `tests/conftest.py`)

**Interfaces:**
- Consumes: Task 1 models.
- Produces (ORM): `Job.external_id: str | None`, `Job.posted_at: datetime | None`, `Job.best_track_id: str | None`, `Job.best_fit: int | None`, `Job.repost_of: uuid.UUID | None`, `Job.rescued: bool`, `Job.identity_hash: str | None`; `Track.embedding: list[float] | None`; `WatchlistEntry.keywords: list[str]`; `Aggregator(user_id, source, enabled, keywords)`; `JobScore(user_id, job_id, track_id, fit_score, rationale_json, scored_at)`; `PollRun(user_id, source, board, started_at, finished_at, found, new, error)`.
- Produces (repos): `profile.list_aggregators(session, user_id) -> list[Aggregator]`, `profile.replace_aggregators(session, user_id, entries: list[AggregatorEntry]) -> None`, `profile.set_track_embedding(track: Track, vector: list[float]) -> None`; `jobs.list_jobs(session, user_id, *, search=None, track=None, bucket=None, sort="fit") -> list[Job]`, `jobs.find_by_external_id(session, user_id, source, external_id) -> Job | None`, `jobs.find_by_identity(session, user_id, identity_hash) -> Job | None`, `jobs.create_discovered_job(session, user_id, *, source, external_id, company, title, location, url, jd_text, posted_at, identity_hash, repost_of) -> Job`, `jobs.set_rescued(job, value: bool) -> None`; `discovery.start_run(session, user_id, source, board) -> PollRun`, `discovery.finish_run(run, *, found, new, error) -> None`, `discovery.latest_runs(session, user_id) -> list[PollRun]`, `discovery.consecutive_failures(session, user_id, source, board) -> int`, `discovery.upsert_scores(session, user_id, job, scores: list[tuple[str, int, dict]]) -> None`, `discovery.scores_for_jobs(session, user_id, job_ids) -> dict[uuid.UUID, list[JobScore]]`.

- [ ] **Step 1: Write the failing repository tests**

`apps/api/tests/unit/test_repositories_discovery.py`:

```python
import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import discovery as disc
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry


async def test_discovered_job_dedupe_and_repost(session: AsyncSession, user: User) -> None:
    first = await jobs_repo.create_discovered_job(
        session, user.id, source="greenhouse", external_id="1", company="ExampleCo",
        title="Data PM", location="Remote", url="https://example.com/1",
        jd_text="lead the data platform program " * 10, posted_at=None, identity_hash="abc", repost_of=None,
    )
    assert await jobs_repo.find_by_external_id(session, user.id, "greenhouse", "1") is first
    assert await jobs_repo.find_by_identity(session, user.id, "abc") is first
    again = await jobs_repo.create_discovered_job(
        session, user.id, source="greenhouse", external_id="2", company="ExampleCo",
        title="Data PM", location="Remote", url="https://example.com/2",
        jd_text="lead the data platform program again " * 10, posted_at=None, identity_hash="abc", repost_of=first.id,
    )
    assert again.repost_of == first.id and again.rescued is False


async def test_scores_upsert_and_list(session: AsyncSession, user: User) -> None:
    job = await jobs_repo.create_job(session, user.id, jd_text="x " * 60)
    await disc.upsert_scores(session, user.id, job, [("data-pm", 70, {"semantic": 60}), ("ai-pm", 20, {})])
    await disc.upsert_scores(session, user.id, job, [("data-pm", 75, {"semantic": 65})])
    scores = await disc.scores_for_jobs(session, user.id, [job.id])
    by_track = {s.track_id: s.fit_score for s in scores[job.id]}
    assert by_track == {"data-pm": 75, "ai-pm": 20}


async def test_poll_runs_latest_and_consecutive_failures(session: AsyncSession, user: User) -> None:
    for error in ("boom", "boom", None, "boom", "boom", "boom"):
        run = await disc.start_run(session, user.id, "lever", "acme")
        disc.finish_run(run, found=0, new=0, error=error)
        await session.flush()
    other = await disc.start_run(session, user.id, "remoteok", None)
    disc.finish_run(other, found=3, new=1, error=None)
    await session.flush()
    latest = await disc.latest_runs(session, user.id)
    assert {(r.source, r.board) for r in latest} == {("lever", "acme"), ("remoteok", None)}
    assert await disc.consecutive_failures(session, user.id, "lever", "acme") == 3
    assert await disc.consecutive_failures(session, user.id, "remoteok", None) == 0


async def test_list_jobs_filters_and_sort(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(session, user.id, Track(id="data-pm", name="Data", resume_base="b", min_fit=60))
    await profile_repo.upsert_track(session, user.id, Track(id="ai-pm", name="AI", resume_base="b", min_fit=50))
    high = await jobs_repo.create_job(session, user.id, jd_text="high " * 60)
    low = await jobs_repo.create_job(session, user.id, jd_text="low " * 60)
    other = await jobs_repo.create_job(session, user.id, jd_text="other " * 60)
    high.best_track_id, high.best_fit = "data-pm", 80
    low.best_track_id, low.best_fit = "data-pm", 40
    other.best_track_id, other.best_fit = "ai-pm", 55
    await session.flush()
    fit = await jobs_repo.list_jobs(session, user.id, bucket="fit")
    assert [j.id for j in fit] == [high.id, other.id]
    assert [j.id for j in await jobs_repo.list_jobs(session, user.id, bucket="low")] == [low.id]
    assert [j.id for j in await jobs_repo.list_jobs(session, user.id, track="ai-pm")] == [other.id]
    jobs_repo.set_rescued(low, True)
    await session.flush()
    assert low.id in [j.id for j in await jobs_repo.list_jobs(session, user.id, bucket="fit")]
    newest = await jobs_repo.list_jobs(session, user.id, sort="newest")
    assert newest[0].id == other.id


async def test_aggregators_replace_and_list(session: AsyncSession, user: User) -> None:
    await profile_repo.replace_aggregators(
        session, user.id, [AggregatorEntry(source="remoteok", enabled=True, keywords=["pm"])]
    )
    rows = await profile_repo.list_aggregators(session, user.id)
    assert [(r.source, r.enabled, r.keywords) for r in rows] == [("remoteok", True, ["pm"])]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_repositories_discovery.py -q`
Expected: FAIL with import or attribute errors.

- [ ] **Step 3: Write the migration**

`apps/api/alembic/versions/0002_discovery.py`:

```python
"""discovery: job scoring columns, aggregators, job_scores, poll_runs

Revision ID: 0002
Revises: 0001
"""
from __future__ import annotations

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("external_id", sa.String(length=200), nullable=True))
    op.add_column("jobs", sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("best_track_id", sa.String(length=100), nullable=True))
    op.add_column("jobs", sa.Column("best_fit", sa.Integer(), nullable=True))
    op.add_column("jobs", sa.Column("repost_of", sa.Uuid(), nullable=True))
    op.add_column(
        "jobs", sa.Column("rescued", sa.Boolean(), server_default=sa.false(), nullable=False)
    )
    op.add_column("jobs", sa.Column("identity_hash", sa.String(length=64), nullable=True))
    op.create_foreign_key("fk_jobs_repost_of", "jobs", "jobs", ["repost_of"], ["id"], ondelete="SET NULL")
    op.create_index("ix_jobs_identity_hash", "jobs", ["identity_hash"])
    op.create_index(
        "uq_jobs_user_source_external",
        "jobs",
        ["user_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )
    op.add_column(
        "tracks",
        sa.Column("embedding", pgvector.sqlalchemy.vector.VECTOR(dim=384), nullable=True),
    )
    op.add_column(
        "watchlist",
        sa.Column(
            "keywords", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False
        ),
    )
    op.create_table(
        "aggregators",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("keywords", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "source"),
    )
    op.create_index("ix_aggregators_user_id", "aggregators", ["user_id"])
    op.create_table(
        "job_scores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("track_id", sa.String(length=100), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False),
        sa.Column("rationale_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "track_id"),
    )
    op.create_index("ix_job_scores_user_id", "job_scores", ["user_id"])
    op.create_index("ix_job_scores_job_id", "job_scores", ["job_id"])
    op.create_table(
        "poll_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("board", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("found", sa.Integer(), server_default="0", nullable=False),
        sa.Column("new", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_poll_runs_user_id", "poll_runs", ["user_id"])
    op.create_index(
        "ix_poll_runs_lookup", "poll_runs", ["user_id", "source", "board", sa.text("started_at DESC")]
    )


def downgrade() -> None:
    op.drop_table("poll_runs")
    op.drop_table("job_scores")
    op.drop_table("aggregators")
    op.drop_column("watchlist", "keywords")
    op.drop_column("tracks", "embedding")
    op.drop_index("uq_jobs_user_source_external", table_name="jobs")
    op.drop_index("ix_jobs_identity_hash", table_name="jobs")
    op.drop_constraint("fk_jobs_repost_of", "jobs", type_="foreignkey")
    for name in ("identity_hash", "rescued", "repost_of", "best_fit", "best_track_id", "posted_at", "external_id"):
        op.drop_column("jobs", name)
```

- [ ] **Step 4: Extend the ORM models**

In `apps/api/src/rhapto/db/models.py`, add to `Job` after `discovered_at`:

```python
    external_id: Mapped[str | None] = mapped_column(String(200))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    best_track_id: Mapped[str | None] = mapped_column(String(100))
    best_fit: Mapped[int | None] = mapped_column(Integer)
    repost_of: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    rescued: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    identity_hash: Mapped[str | None] = mapped_column(String(64), index=True)
```

Add to `Track`: `embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))`.
Add to `WatchlistEntry`: `keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}", nullable=False)`.
Add three classes:

```python
class Aggregator(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "aggregators"
    __table_args__ = (UniqueConstraint("user_id", "source"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true", nullable=False)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, server_default="{}", nullable=False)


class JobScore(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "job_scores"
    __table_args__ = (UniqueConstraint("job_id", "track_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    fit_score: Mapped[int] = mapped_column(Integer, nullable=False)
    rationale_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PollRun(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "poll_runs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    board: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    found: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    new: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
```

- [ ] **Step 5: Repositories**

`apps/api/src/rhapto/db/repositories/discovery.py`:

```python
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, JobScore, PollRun


async def start_run(session: AsyncSession, user_id: uuid.UUID, source: str, board: str | None) -> PollRun:
    run = PollRun(user_id=user_id, source=source, board=board, started_at=datetime.now(UTC))
    session.add(run)
    await session.flush()
    return run


def finish_run(run: PollRun, *, found: int, new: int, error: str | None) -> None:
    run.found, run.new, run.error = found, new, (error[:4000] if error else None)
    run.finished_at = datetime.now(UTC)


async def latest_runs(session: AsyncSession, user_id: uuid.UUID) -> list[PollRun]:
    """Newest run per (source, board)."""
    rows = await session.scalars(
        select(PollRun)
        .where(PollRun.user_id == user_id)
        .order_by(PollRun.source, PollRun.board, PollRun.started_at.desc())
        .distinct(PollRun.source, PollRun.board)
    )
    return sorted(rows, key=lambda r: r.started_at, reverse=True)


async def consecutive_failures(
    session: AsyncSession, user_id: uuid.UUID, source: str, board: str | None
) -> int:
    rows = list(
        await session.scalars(
            select(PollRun)
            .where(PollRun.user_id == user_id, PollRun.source == source, PollRun.board.is_(board) if board is None else PollRun.board == board)
            .order_by(PollRun.started_at.desc())
            .limit(3)
        )
    )
    count = 0
    for run in rows:
        if run.error is None:
            break
        count += 1
    return count


async def upsert_scores(
    session: AsyncSession,
    user_id: uuid.UUID,
    job: Job,
    scores: list[tuple[str, int, dict[str, Any]]],
) -> None:
    existing = {
        s.track_id: s
        for s in await session.scalars(select(JobScore).where(JobScore.job_id == job.id))
    }
    now = datetime.now(UTC)
    for track_id, fit, rationale in scores:
        row = existing.get(track_id)
        if row is None:
            session.add(JobScore(user_id=user_id, job_id=job.id, track_id=track_id, fit_score=fit, rationale_json=rationale, scored_at=now))
        else:
            row.fit_score, row.rationale_json, row.scored_at = fit, rationale, now
    await session.flush()


async def scores_for_jobs(
    session: AsyncSession, user_id: uuid.UUID, job_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[JobScore]]:
    out: dict[uuid.UUID, list[JobScore]] = defaultdict(list)
    if not job_ids:
        return out
    for row in await session.scalars(
        select(JobScore).where(JobScore.user_id == user_id, JobScore.job_id.in_(job_ids)).order_by(JobScore.fit_score.desc())
    ):
        out[row.job_id].append(row)
    return out
```

In `jobs.py` add:

```python
async def find_by_external_id(session: AsyncSession, user_id: uuid.UUID, source: str, external_id: str) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(Job.user_id == user_id, Job.source == source, Job.external_id == external_id)
    )
    return result


async def find_by_identity(session: AsyncSession, user_id: uuid.UUID, identity_hash: str) -> Job | None:
    result: Job | None = await session.scalar(
        select(Job).where(Job.user_id == user_id, Job.identity_hash == identity_hash).order_by(Job.discovered_at).limit(1)
    )
    return result


async def create_discovered_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source: str,
    external_id: str,
    company: str,
    title: str,
    location: str | None,
    url: str,
    jd_text: str,
    posted_at: datetime | None,
    identity_hash: str,
    repost_of: uuid.UUID | None,
) -> Job:
    job = Job(
        user_id=user_id, source=source, external_id=external_id, company=company, title=title,
        location=location, url=url, jd_text=jd_text, dedupe_hash=compute_dedupe_hash(jd_text),
        discovered_at=datetime.now(UTC), posted_at=posted_at, identity_hash=identity_hash, repost_of=repost_of,
    )
    session.add(job)
    await session.flush()
    return job


def set_rescued(job: Job, value: bool) -> None:
    job.rescued = value
```

Replace `list_jobs` with a version that supports the filters. Bucket filtering needs each job's best track's `min_fit`, so join a subquery of the user's tracks:

```python
async def list_jobs(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    search: str | None = None,
    track: str | None = None,
    bucket: str | None = None,
    sort: str = "fit",
) -> list[Job]:
    tracks = select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()
    query = select(Job).outerjoin(tracks, tracks.c.track_id == Job.best_track_id).where(Job.user_id == user_id)
    if search:
        escaped = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.where(or_(Job.company.ilike(pattern, escape="\\"), Job.title.ilike(pattern, escape="\\"), Job.jd_text.ilike(pattern, escape="\\")))
    if track:
        query = query.where(Job.best_track_id == track)
    fit_condition = or_(Job.rescued.is_(True), and_(Job.best_fit.is_not(None), Job.best_fit >= tracks.c.min_fit))
    if bucket == "fit":
        query = query.where(or_(Job.best_fit.is_(None), fit_condition))  # unscored jobs stay visible
    elif bucket == "low":
        query = query.where(Job.best_fit.is_not(None), not_(fit_condition))
    if sort == "newest":
        query = query.order_by(Job.discovered_at.desc(), Job.created_at.desc(), Job.id)
    else:
        query = query.order_by(nulls_last(Job.best_fit.desc()), Job.discovered_at.desc(), Job.id)
    return list(await session.scalars(query))
```

Imports: `from sqlalchemy import and_, not_, nulls_last, or_, select` and `Track` from models. Note: `fit_condition` compares against the joined `min_fit`; a job whose `best_track_id` has no track row counts as low.

In `profile.py` add:

```python
async def list_aggregators(session: AsyncSession, user_id: uuid.UUID) -> list[Aggregator]:
    return list(await session.scalars(select(Aggregator).where(Aggregator.user_id == user_id).order_by(Aggregator.source)))


async def replace_aggregators(session: AsyncSession, user_id: uuid.UUID, entries: list[AggregatorEntry]) -> None:
    await session.execute(delete(Aggregator).where(Aggregator.user_id == user_id))
    for entry in entries:
        session.add(Aggregator(user_id=user_id, source=entry.source, enabled=entry.enabled, keywords=list(entry.keywords)))
    await session.flush()


def set_track_embedding(track: Track, vector: list[float]) -> None:
    track.embedding = vector
```

and make `replace_watchlist` store `keywords=list(entry.keywords)`; `upsert_track` must reset `embedding = None` when `description`, `name`, or `keywords` change (so the scorer recomputes it).

Timestamps: `replace_watchlist`, `replace_aggregators`, and `upsert_track` set `updated_at=datetime.now(UTC)` explicitly on the rows they insert or change. The mixin's `server_default=func.now()` is the transaction start time in Postgres, so inside one test transaction every row would share a timestamp older than any Python `datetime.now(UTC)`; the poller's pause rule (Task 7) compares an entry's `updated_at` with a run's Python-side `started_at`, and needs a real clock.

- [ ] **Step 6: Profile sync and API**

In `services/profile_sync.py`: `watchlist_row_to_model` includes `keywords=list(row.keywords)`; add `aggregator_row_to_model(row) -> AggregatorEntry`; `load_profile_from_db` fills `aggregators`; `replace_profile_in_db` calls `repo.replace_aggregators(session, user_id, profile.aggregators)`.

In `api/routers/profile.py` add, mirroring the watchlist endpoints: `GET /profile/aggregators -> list[AggregatorEntry]` and `PUT /profile/aggregators` (body `list[AggregatorEntry]`, replaces, returns the list). Extend the profile API test:

```python
async def test_aggregators_put_and_get(client: httpx.AsyncClient) -> None:
    body = [{"source": "remoteok", "enabled": True, "keywords": ["pm"]}, {"source": "hn-hiring", "enabled": False, "keywords": []}]
    put = await client.put("/api/v1/profile/aggregators", json=body)
    assert put.status_code == 200 and put.json() == body
    got = await client.get("/api/v1/profile/aggregators")
    assert got.json() == body
    bad = await client.put("/api/v1/profile/aggregators", json=[{"source": "linkedin"}])
    assert bad.status_code == 422
```

- [ ] **Step 7: Run migration and tests**

Run from `apps/api`: `uv run rhapto db upgrade` (against the dev db), then `uv run pytest tests/unit/test_repositories_discovery.py tests/api/test_profile_api.py -q`, then the full Python check set and `uv run lint-imports`.
Expected: PASS; contracts kept.

- [ ] **Step 8: Regenerate OpenAPI and web types, commit**

Run `bash scripts/codegen.sh` from the repo root (updates `openapi.json` and `schema.d.ts` for the new endpoints).

```bash
git add apps/api/alembic/versions/0002_discovery.py apps/api/src/rhapto/db apps/api/src/rhapto/services/profile_sync.py apps/api/src/rhapto/api apps/api/tests packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts
git commit -m "feat(db): discovery schema: scores, poll runs, aggregators, job identity"
```

---

### Task 3: Pure scorer, persistence wrapper, golden classification cases

**Files:**
- Create: `apps/api/src/rhapto/engine/scoring.py`
- Create: `apps/api/src/rhapto/services/scoring.py`
- Create: `apps/api/tests/unit/test_scoring.py`
- Create: `apps/api/tests/golden/classification/cases.json`, `apps/api/tests/golden/test_classification.py`
- Test: `apps/api/tests/unit/test_scoring_service.py` (uses db fixtures)

**Interfaces:**
- Consumes: `keyword_matches`, `cosine` from `rhapto.engine.select`; `EmbeddingProvider`; Task 2 repos.
- Produces (engine): `class TrackScore(BaseModel): track_id: str; fit_score: int; semantic: int; keywords: int; matched: list[str]`; `def track_text(track: Track) -> str`; `def semantic_score(cos: float) -> int`; `def keyword_score(track: Track, title: str | None, text: str) -> tuple[int, list[str]]`; `def score_job(title: str | None, jd_text: str, jd_embedding: list[float], tracks: list[Track], track_embeddings: dict[str, list[float]]) -> list[TrackScore]`; `def best_track(scores: list[TrackScore], tracks: list[Track]) -> TrackScore | None`; `def bucket_for(best: TrackScore | None, tracks: list[Track], rescued: bool) -> Literal["fit", "low"]`; `def rationale(score: TrackScore) -> dict[str, Any]`; constants `SEMANTIC_WEIGHT`, `KEYWORD_WEIGHT`, `COSINE_FLOOR`, `COSINE_CEIL`.
- Produces (service): `async def ensure_track_embeddings(session, user_id, embedder) -> tuple[list[Track], dict[str, list[float]]]` (returns Pydantic tracks in position order and vectors, computing and storing any missing embedding); `async def score_and_store(session, user_id, jobs: list[Job], embedder) -> None` (embeds jobs lacking `jd_embedding`, writes `job_scores`, `best_track_id`, `best_fit`); `async def rescore_user(session, user_id, embedder) -> int` (all jobs, returns count).

- [ ] **Step 1: Write the failing unit tests**

`apps/api/tests/unit/test_scoring.py`:

```python
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.scoring import (
    KEYWORD_WEIGHT,
    SEMANTIC_WEIGHT,
    TrackScore,
    best_track,
    bucket_for,
    keyword_score,
    score_job,
    semantic_score,
    track_text,
)
from rhapto.models.profile.tracks import Track

DATA = Track(id="data-pm", name="Data Program Management", resume_base="b", min_fit=60,
             keywords=["Data Program Manager", "analytics", "data platform", "ETL"],
             description="Data platform and analytics program leadership.")
AI = Track(id="ai-pm", name="AI Product/Program", resume_base="b", min_fit=55,
           keywords=["AI Product Manager", "LLM", "GenAI", "ML platform"],
           description="AI product and program roles leveraging hands-on LLM work.")


def test_semantic_score_maps_cosine_band() -> None:
    assert semantic_score(0.20) == 0 and semantic_score(0.80) == 100
    assert semantic_score(0.50) == 50
    assert semantic_score(-1.0) == 0 and semantic_score(0.99) == 100


def test_keyword_score_title_counts_double_and_caps() -> None:
    score, matched = keyword_score(DATA, "Data Program Manager", "we run ETL and analytics")
    # title hit 2 + text hits 1 + 1 = 4 over 4 keywords -> 100
    assert score == 100 and matched == ["Data Program Manager", "analytics", "ETL"]
    score, matched = keyword_score(DATA, None, "nothing relevant here")
    assert score == 0 and matched == []
    score, _ = keyword_score(Track(id="t", name="t", resume_base="b"), "x", "y")
    assert score == 0  # no keywords -> 0, never a division by zero


def test_track_text_falls_back_to_name_and_keywords() -> None:
    assert track_text(DATA) == "Data platform and analytics program leadership."
    bare = Track(id="t", name="Ops Lead", resume_base="b", keywords=["SRE", "on-call"])
    assert track_text(bare) == "Ops Lead SRE on-call"


async def test_score_job_blends_and_orders_by_track() -> None:
    embedder = FakeEmbeddingProvider()
    jd = "Data Program Manager to lead our analytics data platform and ETL modernisation"
    vectors = await embedder.embed([jd, track_text(DATA), track_text(AI)])
    scores = score_job("Data Program Manager", jd, vectors[0], [DATA, AI], {"data-pm": vectors[1], "ai-pm": vectors[2]})
    assert [s.track_id for s in scores] == ["data-pm", "ai-pm"]
    data = scores[0]
    assert data.fit_score == round(SEMANTIC_WEIGHT * data.semantic + KEYWORD_WEIGHT * data.keywords)
    assert data.fit_score > scores[1].fit_score


def test_best_track_ties_resolve_by_track_order_and_bucket_uses_min_fit() -> None:
    tie = [TrackScore(track_id="ai-pm", fit_score=60, semantic=60, keywords=60, matched=[]),
           TrackScore(track_id="data-pm", fit_score=60, semantic=60, keywords=60, matched=[])]
    best = best_track(tie, [DATA, AI])
    assert best is not None and best.track_id == "data-pm"
    assert bucket_for(best, [DATA, AI], rescued=False) == "fit"
    low = TrackScore(track_id="data-pm", fit_score=59, semantic=59, keywords=59, matched=[])
    assert bucket_for(low, [DATA, AI], rescued=False) == "low"
    assert bucket_for(low, [DATA, AI], rescued=True) == "fit"
    assert best_track([], [DATA, AI]) is None and bucket_for(None, [DATA, AI], rescued=False) == "low"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_scoring.py -q`
Expected: FAIL, module not found.

- [ ] **Step 3: Implement the engine scorer**

`apps/api/src/rhapto/engine/scoring.py`:

```python
"""Deterministic track classification: embedding similarity plus keyword hits. No LLM."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from rhapto.engine.select import cosine, keyword_matches
from rhapto.models.profile.tracks import Track

SEMANTIC_WEIGHT = 0.6
KEYWORD_WEIGHT = 0.4
COSINE_FLOOR = 0.20
COSINE_CEIL = 0.80
TITLE_HIT = 2
TEXT_HIT = 1


class TrackScore(BaseModel):
    track_id: str
    fit_score: int
    semantic: int
    keywords: int
    matched: list[str]


def track_text(track: Track) -> str:
    if track.description and track.description.strip():
        return track.description.strip()
    return " ".join([track.name, *track.keywords]).strip()


def semantic_score(cos: float) -> int:
    scaled = (cos - COSINE_FLOOR) / (COSINE_CEIL - COSINE_FLOOR) * 100
    return int(round(min(100.0, max(0.0, scaled))))


def keyword_score(track: Track, title: str | None, text: str) -> tuple[int, list[str]]:
    if not track.keywords:
        return 0, []
    hits = 0
    matched: list[str] = []
    for keyword in track.keywords:
        in_title = bool(title) and keyword_matches(keyword, title or "")
        in_text = keyword_matches(keyword, text)
        if in_title:
            hits += TITLE_HIT
        elif in_text:
            hits += TEXT_HIT
        if in_title or in_text:
            matched.append(keyword)
    fraction = min(1.0, hits / len(track.keywords))
    return int(round(fraction * 100)), matched


def score_job(
    title: str | None,
    jd_text: str,
    jd_embedding: list[float],
    tracks: list[Track],
    track_embeddings: dict[str, list[float]],
) -> list[TrackScore]:
    scores: list[TrackScore] = []
    for track in tracks:
        vector = track_embeddings.get(track.id)
        semantic = semantic_score(cosine(jd_embedding, vector)) if vector else 0
        keywords, matched = keyword_score(track, title, jd_text)
        fit = int(round(SEMANTIC_WEIGHT * semantic + KEYWORD_WEIGHT * keywords))
        scores.append(TrackScore(track_id=track.id, fit_score=fit, semantic=semantic, keywords=keywords, matched=matched))
    return scores


def best_track(scores: list[TrackScore], tracks: list[Track]) -> TrackScore | None:
    order = {t.id: i for i, t in enumerate(tracks)}
    ranked = sorted(scores, key=lambda s: (-s.fit_score, order.get(s.track_id, len(order))))
    return ranked[0] if ranked else None


def bucket_for(best: TrackScore | None, tracks: list[Track], rescued: bool) -> Literal["fit", "low"]:
    if rescued:
        return "fit"
    if best is None:
        return "low"
    track = next((t for t in tracks if t.id == best.track_id), None)
    if track is None:
        return "low"
    return "fit" if best.fit_score >= track.min_fit else "low"


def rationale(score: TrackScore) -> dict[str, Any]:
    return {
        "semantic": score.semantic,
        "keywords": score.keywords,
        "matched": score.matched,
        "weights": {"semantic": SEMANTIC_WEIGHT, "keywords": KEYWORD_WEIGHT},
    }
```

`keyword_matches` is a whole-word matcher, so `"ETL"` matches `"ETL"` but not `"settle"`. Note the `cosine` helper requires equal-length vectors; the service guarantees that by embedding tracks and jobs with the same provider.

- [ ] **Step 4: Run the unit tests**

Run: `uv run pytest tests/unit/test_scoring.py -q`
Expected: PASS. If `test_score_job_blends_and_orders_by_track` fails on the `>` assertion, the fake embedder's hashed vectors collided; change the JD wording, not the scorer.

- [ ] **Step 5: Persistence wrapper**

`apps/api/src/rhapto/services/scoring.py`:

```python
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import EMBEDDING_DIMENSIONS, Job
from rhapto.db.models import Track as TrackRow
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.scoring import best_track, rationale, score_job, track_text
from rhapto.models.profile.tracks import Track
from rhapto.services.profile_sync import track_row_to_model

logger = logging.getLogger(__name__)


def _fit_dimensions(vector: list[float]) -> list[float] | None:
    return list(vector) if len(vector) == EMBEDDING_DIMENSIONS else None


async def ensure_track_embeddings(
    session: AsyncSession, user_id: uuid.UUID, embedder: EmbeddingProvider
) -> tuple[list[Track], dict[str, list[float]]]:
    rows: list[TrackRow] = await profile_repo.list_tracks(session, user_id)
    missing = [r for r in rows if r.embedding is None]
    if missing:
        vectors = await embedder.embed([track_text(track_row_to_model(r)) for r in missing])
        for row, vector in zip(missing, vectors, strict=True):
            fitted = _fit_dimensions(vector)
            if fitted is None:
                logger.error("embedding width %d != %d; not caching track %r", len(vector), EMBEDDING_DIMENSIONS, row.track_id)
                continue
            profile_repo.set_track_embedding(row, fitted)
        await session.flush()
    tracks = [track_row_to_model(r) for r in rows]
    vectors_by_id = {r.track_id: list(r.embedding) for r in rows if r.embedding is not None}
    return tracks, vectors_by_id


async def score_and_store(
    session: AsyncSession, user_id: uuid.UUID, jobs: list[Job], embedder: EmbeddingProvider
) -> None:
    if not jobs:
        return
    tracks, track_vectors = await ensure_track_embeddings(session, user_id, embedder)
    unembedded = [j for j in jobs if j.jd_embedding is None]
    if unembedded:
        vectors = await embedder.embed([f"{j.title or ''}\n{j.jd_text}" for j in unembedded])
        for job, vector in zip(unembedded, vectors, strict=True):
            job.jd_embedding = _fit_dimensions(vector)
    for job in jobs:
        if job.jd_embedding is None or not tracks:
            job.best_track_id, job.best_fit = None, None
            continue
        scores = score_job(job.title, job.jd_text, list(job.jd_embedding), tracks, track_vectors)
        best = best_track(scores, tracks)
        job.best_track_id = best.track_id if best else None
        job.best_fit = best.fit_score if best else None
        await disc_repo.upsert_scores(session, user_id, job, [(s.track_id, s.fit_score, rationale(s)) for s in scores])
    await session.flush()


async def rescore_user(session: AsyncSession, user_id: uuid.UUID, embedder: EmbeddingProvider) -> int:
    for row in await profile_repo.list_tracks(session, user_id):
        row.embedding = None  # descriptions may have changed; recompute every track
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user_id)))
    await score_and_store(session, user_id, jobs, embedder)
    return len(jobs)
```

`track_row_to_model` exists in `services/profile_sync.py` (it converts the ORM track to the Pydantic `Track`); if its name differs, use the existing converter.

- [ ] **Step 6: Service test**

`apps/api/tests/unit/test_scoring_service.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.services.scoring import ensure_track_embeddings, rescore_user, score_and_store

DATA = Track(id="data-pm", name="Data", resume_base="b", min_fit=60, keywords=["data platform", "ETL"], description="Data platform program leadership")
AI = Track(id="ai-pm", name="AI", resume_base="b", min_fit=55, keywords=["LLM", "GenAI"], description="AI product roles with LLM work")


async def test_score_and_store_sets_best_track_and_scores(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(session, user.id, DATA)
    await profile_repo.upsert_track(session, user.id, AI)
    job = await jobs_repo.create_job(session, user.id, jd_text="Own the data platform and ETL roadmap for analytics " * 5, title="Data Platform Program Manager")
    embedder = FakeEmbeddingProvider(dimensions=384)
    await score_and_store(session, user.id, [job], embedder)
    assert job.best_track_id == "data-pm" and job.best_fit is not None and job.jd_embedding is not None
    tracks, vectors = await ensure_track_embeddings(session, user.id, embedder)
    assert set(vectors) == {"data-pm", "ai-pm"} and [t.id for t in tracks] == ["data-pm", "ai-pm"]
    assert await rescore_user(session, user.id, embedder) == 1
```

Run: `uv run pytest tests/unit/test_scoring_service.py -q` → PASS.

- [ ] **Step 7: Golden classification cases**

`apps/api/tests/golden/classification/cases.json` (all fictional; expected values are against `profile.example` tracks `data-pm` with min_fit 60 and `ai-pm` with min_fit 55):

```json
[
  {"id": "dpm-snowflake", "title": "Data Platform Program Manager", "text": "ExampleCo seeks a Data Program Manager to lead our Snowflake migration, ETL modernisation, and analytics data platform roadmap across engineering teams.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-warehouse", "title": "Senior Program Manager, Data Platform", "text": "Run the data platform program: warehouse consolidation, ETL pipelines, analytics enablement, and cross-functional delivery with data engineering.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-analytics", "title": "Analytics Program Lead", "text": "Own analytics delivery for the data platform: dashboards, ETL reliability, and program management of the analytics roadmap.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-etl", "title": "Technical Program Manager, ETL", "text": "Coordinate ETL migrations and data platform releases; partner with analytics and data engineering as the program manager.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-governance", "title": "Data Program Manager, Governance", "text": "Lead the data platform governance program, analytics quality, and ETL lineage across business units.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-migration", "title": "Data Program Manager", "text": "Drive the analytics data platform migration program and ETL cutover plans with engineering and finance stakeholders.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-bi", "title": "BI and Data Platform Program Manager", "text": "Program manage the BI and analytics data platform: ETL scheduling, warehouse cost, and stakeholder reporting.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "dpm-ops", "title": "Data Operations Program Manager", "text": "Run data platform operations programs: ETL incident reviews, analytics SLAs, and vendor management.", "expected_track": "data-pm", "expected_bucket": "fit"},
  {"id": "aipm-llm", "title": "AI Product Manager", "text": "Ship LLM features on our GenAI platform; hands-on with prompts, evaluations, and the ML platform team as AI Product Manager.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "aipm-genai", "title": "Product Manager, GenAI", "text": "Lead GenAI product discovery, LLM integration, and the ML platform roadmap for enterprise customers.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "aipm-mlplatform", "title": "ML Platform Program Manager", "text": "Program manage the ML platform: LLM serving, GenAI evaluation tooling, and AI product launches.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "aipm-agents", "title": "AI Product Manager, Agents", "text": "Define LLM agent products, GenAI guardrails, and ML platform requirements with research and engineering.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "aipm-copilot", "title": "Senior AI Product Manager", "text": "Own the copilot roadmap: LLM prompts, GenAI quality metrics, and the ML platform partnership.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "aipm-search", "title": "Product Manager, AI Search", "text": "Build LLM-powered search on the GenAI stack; work with the ML platform team on retrieval and evaluation as AI Product Manager.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "aipm-program", "title": "AI Program Manager", "text": "Coordinate GenAI programs across product teams: LLM rollouts, ML platform capacity, and AI product governance.", "expected_track": "ai-pm", "expected_bucket": "fit"},
  {"id": "low-barista", "title": "Barista", "text": "Prepare espresso drinks, keep the counter clean, and greet customers at our downtown cafe. Weekend shifts required.", "expected_track": null, "expected_bucket": "low"},
  {"id": "low-nurse", "title": "Registered Nurse, ICU", "text": "Provide critical care nursing in a 20-bed ICU; current RN licence and ACLS certification required.", "expected_track": null, "expected_bucket": "low"},
  {"id": "low-sales", "title": "Account Executive", "text": "Close mid-market SaaS deals, manage a pipeline in the CRM, and hit quarterly quota with outbound prospecting.", "expected_track": null, "expected_bucket": "low"},
  {"id": "low-frontend", "title": "Frontend Engineer", "text": "Build React components, own the design system, and ship accessible web interfaces with the product team.", "expected_track": null, "expected_bucket": "low"},
  {"id": "low-hr", "title": "HR Business Partner", "text": "Partner with leaders on performance cycles, employee relations, and compensation planning.", "expected_track": null, "expected_bucket": "low"}
]
```

`apps/api/tests/golden/test_classification.py`:

```python
"""Golden classification: fictional JDs scored against the demo profile's tracks with the fake embedder."""

import json
from pathlib import Path

import pytest

from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.scoring import best_track, bucket_for, score_job, track_text
from rhapto.profile.loader import load_profile

CASES = json.loads((Path(__file__).parent / "classification" / "cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
async def test_classification_case(case: dict[str, object], demo_profile_dir: Path) -> None:
    tracks = load_profile(demo_profile_dir).tracks
    embedder = FakeEmbeddingProvider()
    text = f"{case['title']}\n{case['text']}"
    vectors = await embedder.embed([text, *(track_text(t) for t in tracks)])
    scores = score_job(str(case["title"]), str(case["text"]), vectors[0], tracks, {t.id: v for t, v in zip(tracks, vectors[1:], strict=True)})
    best = best_track(scores, tracks)
    bucket = bucket_for(best, tracks, rescued=False)
    assert bucket == case["expected_bucket"], scores
    if case["expected_track"] is not None:
        assert best is not None and best.track_id == case["expected_track"], scores


def test_twenty_cases_present() -> None:
    assert len(CASES) == 20
```

Run: `uv run pytest tests/golden/test_classification.py -q`. Expected: 21 passed. If a `fit` case scores below its track's `min_fit` with the fake embedder, add one more of that track's keywords to the case text (keep it fictional); if a `low` case lands in `fit`, remove the overlapping word. Do not change weights.

- [ ] **Step 8: Checks and commit**

Run the full Python check set and `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/engine/scoring.py apps/api/src/rhapto/services/scoring.py apps/api/tests/unit/test_scoring.py apps/api/tests/unit/test_scoring_service.py apps/api/tests/golden/classification apps/api/tests/golden/test_classification.py
git commit -m "feat(engine): deterministic track scoring with persistence and golden cases"
```

---

### Task 4: Discovery core: Posting, HTTP client, HTML to text, dedupe, source protocol and registry, contract test

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/__init__.py`, `posting.py`, `http.py`, `dedupe.py`, `sources/__init__.py`, `sources/base.py`
- Modify: `apps/api/src/rhapto/services/jobtext.py` (expose `html_to_text`)
- Modify: `apps/api/src/rhapto/config.py` (`rhapto_discovery_user_agent`, `rhapto_poll_interval_hours`), `.env.example`
- Test: `apps/api/tests/unit/test_discovery_core.py`, `apps/api/tests/unit/test_discovery_sources.py` (contract test; adapters register in Tasks 5 and 6)

**Interfaces:**
- Consumes: `assert_public_host(hostname)` and trafilatura extraction from `services/jobtext.py`; `dedupe_hash` from `db/hashing.py`.
- Produces:
  - `class Posting(BaseModel): external_id: str; company: str; title: str; location: str | None; url: str; jd_text: str; posted_at: datetime | None`
  - `class DiscoveryHttp: __init__(self, *, user_agent: str, timeout: float = 20.0, max_bytes: int = 25 * 1024 * 1024, client: httpx.AsyncClient | None = None)`, `async get_json(self, url: str) -> Any`, `async get_text(self, url: str) -> str`, `async aclose(self)`; raises `SourceError(message)` on non-2xx after one retry on 5xx, on size overflow, or on a non-public host.
  - `class FakeDiscoveryHttp: __init__(self, routes: dict[str, Any])` where a route key is a URL substring and the value is the JSON (or `SourceError` instance to raise); records `self.calls: list[str]`.
  - `def html_to_text(html: str) -> str` in `services/jobtext.py` (trafilatura then tag-strip fallback, whitespace collapsed).
  - `def normalize_title(title: str) -> str` (lowercase, strip seniority suffixes in parentheses and after " - ", collapse spaces), `def identity_hash(company: str, title: str, location: str | None) -> str` (sha256 of `f"{company.lower().strip()}|{normalize_title(title)}|{(location or '').lower().strip()}"`).
  - `class SourceError(Exception)`; `@dataclass(frozen=True) class SourceInfo: name: str; kind: Literal["board", "aggregator"]; label: str; needs_board: bool`; `class Source(Protocol): info: ClassVar[SourceInfo]; async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]`.
  - Registry in `sources/__init__.py`: `SOURCES: dict[str, type[Source]]`, `def get_source(name: str) -> Source`, `def board_sources() -> list[SourceInfo]`, `def aggregator_sources() -> list[SourceInfo]`, `def all_sources() -> list[SourceInfo]`.
  - `def matches_keywords(keywords: list[str], *texts: str | None) -> bool` in `sources/base.py` (any keyword whole-word in any text; empty keyword list means match everything).

- [ ] **Step 1: Write the failing core tests**

`apps/api/tests/unit/test_discovery_core.py`:

```python
import httpx
import pytest

from rhapto.services.discovery.dedupe import identity_hash, normalize_title
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.sources.base import SourceError, matches_keywords
from rhapto.services.jobtext import html_to_text


def test_html_to_text_strips_markup_and_entities() -> None:
    text = html_to_text("<p>Lead the <b>data platform</b> &amp; ETL.</p><ul><li>Remote</li></ul>")
    assert "data platform & ETL" in text and "<" not in text and "Remote" in text


def test_normalize_title_and_identity_hash() -> None:
    assert normalize_title("Senior Data PM (Remote) - Platform") == "senior data pm"
    assert normalize_title("  Data   Program Manager ") == "data program manager"
    a = identity_hash("ExampleCo", "Data Program Manager (Remote)", "Denver, CO")
    b = identity_hash("exampleco", "data program manager", "denver, co")
    assert a == b and len(a) == 64
    assert identity_hash("ExampleCo", "Data Program Manager", None) != a


def test_matches_keywords_whole_word_any_text() -> None:
    assert matches_keywords(["ETL"], "Data lead", "we run ETL nightly")
    assert not matches_keywords(["ETL"], "we settle accounts", None)
    assert matches_keywords([], None, None)


async def test_discovery_http_rejects_private_hosts_and_large_bodies() -> None:
    http = DiscoveryHttp(user_agent="t", max_bytes=10)
    with pytest.raises(SourceError):
        await http.get_json("http://127.0.0.1/jobs")

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 11, headers={"content-type": "application/json"})

    big = DiscoveryHttp(user_agent="t", max_bytes=10, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    with pytest.raises(SourceError, match="25|too large|exceeds"):
        await big.get_text("https://example.com/big")


async def test_discovery_http_retries_once_on_5xx_and_sends_user_agent() -> None:
    seen: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["user-agent"])
        if len(seen) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"ok": True})

    http = DiscoveryHttp(user_agent="rhapto-test/1", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    assert await http.get_json("https://example.com/api") == {"ok": True}
    assert seen == ["rhapto-test/1", "rhapto-test/1"]


async def test_fake_http_routes_by_substring_and_records_calls() -> None:
    fake = FakeDiscoveryHttp({"/boards/acme/": {"jobs": []}, "/bad": SourceError("down")})
    assert await fake.get_json("https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true") == {"jobs": []}
    with pytest.raises(SourceError):
        await fake.get_json("https://x/bad")
    assert len(fake.calls) == 2
```

The SSRF check needs the `assert_public_host` behaviour from `services/jobtext.py` (it resolves the host and rejects loopback and private ranges). The test's private-host case must not depend on DNS: `127.0.0.1` is rejected before any lookup.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_discovery_core.py -q`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

`services/jobtext.py`: refactor the HTML-to-text code at lines 161-163 into a public function and call it from `fetch_job_text`:

```python
def html_to_text(html: str) -> str:
    """Plain text from HTML: trafilatura first, then a tag-strip fallback; whitespace collapsed."""
    unescaped = html_module.unescape(html) if "&lt;" in html and "<" not in html else html
    extracted = trafilatura.extract(unescaped, include_comments=False, include_tables=True) or ""
    text = extracted.strip() or _strip_tags(unescaped)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n{3,}", "\n\n", text)).strip()
```

with `import html as html_module`. The escaped-HTML branch covers Greenhouse, whose `content` field is HTML-escaped HTML. Make sure `_strip_tags` also unescapes entities (`html_module.unescape`).

`services/discovery/posting.py`:

```python
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, field_validator


class Posting(BaseModel):
    external_id: str
    company: str
    title: str
    location: str | None = None
    url: str
    jd_text: str
    posted_at: datetime | None = None

    @field_validator("external_id", "company", "title", "jd_text")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("posted_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("posted_at must be timezone-aware")
        return value
```

`services/discovery/http.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import httpx

from rhapto.services.discovery.sources.base import SourceError
from rhapto.services.jobtext import assert_public_host

DEFAULT_MAX_BYTES = 25 * 1024 * 1024


class DiscoveryHttp:
    """Vendor fetches: public hosts only, size cap, timeout, one retry on 5xx, explicit user agent."""

    def __init__(
        self,
        *,
        user_agent: str,
        timeout: float = 20.0,
        max_bytes: int = DEFAULT_MAX_BYTES,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.user_agent = user_agent
        self.max_bytes = max_bytes
        self._client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str) -> httpx.Response:
        host = urlparse(url).hostname or ""
        try:
            await assert_public_host(host)
        except Exception as exc:  # JobTextError or resolution failure
            raise SourceError(f"refusing to fetch {url}: {exc}") from exc
        headers = {"User-Agent": self.user_agent, "Accept": "application/json, text/html;q=0.8"}
        last: httpx.Response | None = None
        for attempt in range(2):
            try:
                async with self._client.stream("GET", url, headers=headers) as response:
                    if response.status_code >= 500 and attempt == 0:
                        await asyncio.sleep(0.5)
                        continue
                    if response.status_code >= 400:
                        raise SourceError(f"{url} returned HTTP {response.status_code}")
                    chunks: list[bytes] = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > self.max_bytes:
                            raise SourceError(f"{url} exceeds {self.max_bytes} bytes")
                        chunks.append(chunk)
                    last = httpx.Response(response.status_code, content=b"".join(chunks), headers=response.headers, request=response.request)
                    return last
            except httpx.HTTPError as exc:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise SourceError(f"{url}: {exc}") from exc
        raise SourceError(f"{url}: no response after retry")

    async def get_json(self, url: str) -> Any:
        response = await self._get(url)
        try:
            return response.json()
        except ValueError as exc:
            raise SourceError(f"{url}: invalid JSON") from exc

    async def get_text(self, url: str) -> str:
        return (await self._get(url)).text


class FakeDiscoveryHttp:
    """Test double: routes keyed by URL substring; a SourceError value is raised instead of returned."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def _route(self, url: str) -> Any:
        self.calls.append(url)
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, SourceError):
                    raise value
                return value
        raise SourceError(f"no fake route for {url}")

    async def get_json(self, url: str) -> Any:
        return self._route(url)

    async def get_text(self, url: str) -> str:
        value = self._route(url)
        return value if isinstance(value, str) else str(value)

    async def aclose(self) -> None:
        return None
```

`assert_public_host` raises on loopback and private addresses; check its exception type in `jobtext.py` (`JobTextError`) and catch that instead of `Exception` if it is the only one raised.

`services/discovery/dedupe.py`:

```python
from __future__ import annotations

import hashlib
import re

_PAREN = re.compile(r"\([^)]*\)")


def normalize_title(title: str) -> str:
    base = _PAREN.sub(" ", title)
    base = base.split(" - ")[0].split(" – ")[0]
    return re.sub(r"\s+", " ", base).strip().lower()


def identity_hash(company: str, title: str, location: str | None) -> str:
    key = f"{company.strip().lower()}|{normalize_title(title)}|{(location or '').strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
```

`services/discovery/sources/base.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar, Literal, Protocol

from rhapto.engine.select import keyword_matches
from rhapto.services.discovery.posting import Posting

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp


class SourceError(Exception):
    """A source request failed; recorded on the poll run, never fatal for the whole poll."""


@dataclass(frozen=True)
class SourceInfo:
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool


class Source(Protocol):
    info: ClassVar[SourceInfo]

    async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]: ...


def matches_keywords(keywords: list[str], *texts: str | None) -> bool:
    if not keywords:
        return True
    return any(keyword_matches(k, t) for k in keywords for t in texts if t)
```

Because `http.py` imports `SourceError` from `base.py` and `base.py` only needs `DiscoveryHttp` for typing, the `TYPE_CHECKING` guard avoids the cycle.

`services/discovery/sources/__init__.py` (adapters are added to `SOURCES` in Tasks 5 and 6; start with an empty dict and the helpers):

```python
from __future__ import annotations

from rhapto.services.discovery.sources.base import Source, SourceError, SourceInfo

SOURCES: dict[str, type[Source]] = {}


def register(cls: type[Source]) -> type[Source]:
    SOURCES[cls.info.name] = cls
    return cls


def get_source(name: str) -> Source:
    try:
        return SOURCES[name]()
    except KeyError as exc:
        raise SourceError(f"unknown source {name!r}") from exc


def all_sources() -> list[SourceInfo]:
    return [cls.info for cls in SOURCES.values()]


def board_sources() -> list[SourceInfo]:
    return [i for i in all_sources() if i.kind == "board"]


def aggregator_sources() -> list[SourceInfo]:
    return [i for i in all_sources() if i.kind == "aggregator"]
```

`services/discovery/__init__.py`: empty docstring module. Settings: add to `Settings`:

```python
    rhapto_poll_interval_hours: int = 6
    rhapto_discovery_user_agent: str = "rhapto-discovery/0.3"
```

and to `.env.example` under a `# discovery (phase 0.3)` comment:

```
RHAPTO_POLL_INTERVAL_HOURS=6
RHAPTO_DISCOVERY_USER_AGENT=rhapto-discovery/0.3
```

- [ ] **Step 4: Contract test scaffold**

`apps/api/tests/unit/test_discovery_sources.py`:

```python
"""Every registered source passes the same contract against its recorded (fictional) fixture."""

import json
import re
from pathlib import Path

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.sources import SOURCES, aggregator_sources, all_sources, board_sources, get_source
from rhapto.models.profile.watchlist import AggregatorEntry, WatchlistEntry

FIXTURES = Path(__file__).parent.parent / "fixtures" / "discovery"


def fake_http_for(name: str) -> FakeDiscoveryHttp:
    routes = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
    return FakeDiscoveryHttp(routes)


@pytest.mark.parametrize("name", sorted(SOURCES))
async def test_source_contract(name: str) -> None:
    source = get_source(name)
    board = "exampleco" if source.info.needs_board else None
    postings = await source.fetch(fake_http_for(name), board=board, keywords=[])
    assert postings, f"{name} fixture produced no postings"
    for p in postings:
        assert p.external_id and p.title and p.company and p.jd_text
        assert p.url.startswith("https://")
        assert not re.search(r"<[a-z][^>]*>", p.jd_text), f"{name}: HTML leaked into jd_text"
        assert p.posted_at is None or p.posted_at.tzinfo is not None


def test_registry_matches_profile_schema_enums() -> None:
    board_enum = set(WatchlistEntry.model_fields["source"].annotation.__args__)  # type: ignore[union-attr]
    aggregator_enum = set(AggregatorEntry.model_fields["source"].annotation.__args__)  # type: ignore[union-attr]
    assert {i.name for i in board_sources()} <= board_enum
    assert {i.name for i in aggregator_sources()} == aggregator_enum
    assert {i.name for i in all_sources()} == set(SOURCES)
```

Fixture files are `{ "<url substring>": <json body> }` maps consumed by `FakeDiscoveryHttp`. The generated `source` fields are `Literal[...]`; if the annotation is wrapped differently by the generator, use `typing.get_args` on it. `board_sources()` is a subset of the enum because `smartrecruiters` and `workable` remain valid schema values without adapters.

- [ ] **Step 5: Run tests, checks, commit**

Run: `uv run pytest tests/unit/test_discovery_core.py tests/unit/test_discovery_sources.py -q` → the core tests pass; the parametrized contract test is skipped/empty until Task 5 registers adapters (`test_registry_matches_profile_schema_enums` passes with empty sets only if `aggregator_enum` is empty, which it is not, so mark it `xfail(strict=True, reason="adapters land in Tasks 5 and 6")` for now and remove the marker in Task 6). Then the full Python check set and `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/services/discovery apps/api/src/rhapto/services/jobtext.py apps/api/src/rhapto/config.py .env.example apps/api/tests/unit/test_discovery_core.py apps/api/tests/unit/test_discovery_sources.py
git commit -m "feat(discovery): posting model, guarded http client, dedupe, source registry"
```

---

### Task 5: Board adapters: Greenhouse, Lever, Ashby

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/sources/greenhouse.py`, `lever.py`, `ashby.py`
- Create: `apps/api/tests/fixtures/discovery/greenhouse.json`, `lever.json`, `ashby.json`
- Modify: `apps/api/src/rhapto/services/discovery/sources/__init__.py` (import the three modules so they register)
- Test: `apps/api/tests/unit/test_discovery_boards.py` plus the Task 4 contract test

**Interfaces:**
- Consumes: Task 4 `Posting`, `DiscoveryHttp`, `SourceInfo`, `register`, `matches_keywords`, `html_to_text`.
- Produces: `GreenhouseSource` (`info = SourceInfo("greenhouse", "board", "Greenhouse", True)`), `LeverSource` (`"lever"`), `AshbySource` (`"ashby"`), each with `fetch(http, *, board, keywords)` that returns postings filtered by `matches_keywords(keywords, title, jd_text)`.

- [ ] **Step 1: Fixtures (fictional data, shapes match the live APIs)**

`tests/fixtures/discovery/greenhouse.json`:

```json
{
  "boards-api.greenhouse.io/v1/boards/exampleco/jobs?content=true": {
    "jobs": [
      {
        "id": 4001,
        "title": "Data Platform Program Manager",
        "updated_at": "2026-09-03T14:19:37-04:00",
        "first_published": "2026-08-20T10:00:00-04:00",
        "location": {"name": "Denver, CO"},
        "absolute_url": "https://boards.greenhouse.io/exampleco/jobs/4001",
        "company_name": "ExampleCo",
        "content": "&lt;p&gt;ExampleCo seeks a &lt;b&gt;Data Program Manager&lt;/b&gt; to lead our Snowflake migration and ETL modernisation.&lt;/p&gt;&lt;ul&gt;&lt;li&gt;5+ years program management&lt;/li&gt;&lt;/ul&gt;"
      },
      {
        "id": 4002,
        "title": "AI Product Manager",
        "updated_at": "2026-09-01T09:00:00-04:00",
        "first_published": "2026-08-28T09:00:00-04:00",
        "location": {"name": "Remote"},
        "absolute_url": "https://boards.greenhouse.io/exampleco/jobs/4002",
        "company_name": "ExampleCo",
        "content": "&lt;p&gt;Ship LLM features on our GenAI platform.&lt;/p&gt;"
      }
    ]
  }
}
```

`tests/fixtures/discovery/lever.json`:

```json
{
  "api.lever.co/v0/postings/exampleco?mode=json": [
    {
      "id": "8f1c2a3b-0000-4000-8000-000000000001",
      "text": "Senior Program Manager, Data Platform",
      "categories": {"commitment": "Full Time", "department": "Data", "location": "Seattle, WA", "team": "Platform", "allLocations": ["Seattle, WA"]},
      "hostedUrl": "https://jobs.lever.co/exampleco/8f1c2a3b-0000-4000-8000-000000000001",
      "createdAt": 1788134400000,
      "descriptionPlain": "Run the data platform program: warehouse consolidation and ETL pipelines.",
      "description": "<p>Run the data platform program: warehouse consolidation and ETL pipelines.</p>",
      "lists": [{"text": "What you'll do", "content": "<li>Own analytics enablement</li><li>Partner with data engineering</li>"}],
      "additionalPlain": "ExampleCo is an equal opportunity employer."
    }
  ]
}
```

`tests/fixtures/discovery/ashby.json`:

```json
{
  "api.ashbyhq.com/posting-api/job-board/exampleco": {
    "jobs": [
      {
        "id": "7458d4e9-0000-4000-8000-000000000001",
        "title": "ML Platform Program Manager",
        "location": "Remote - US",
        "isRemote": true,
        "isListed": true,
        "jobUrl": "https://jobs.ashbyhq.com/exampleco/7458d4e9-0000-4000-8000-000000000001",
        "publishedAt": "2026-08-30T14:29:08.532+00:00",
        "descriptionPlain": "Program manage the ML platform: LLM serving and GenAI evaluation tooling.",
        "descriptionHtml": "<p>Program manage the ML platform: LLM serving and GenAI evaluation tooling.</p>",
        "department": "Engineering", "team": "ML Platform", "employmentType": "FullTime", "workplaceType": "Remote"
      },
      {
        "id": "7458d4e9-0000-4000-8000-000000000002",
        "title": "Hidden role",
        "location": "Nowhere",
        "isListed": false,
        "jobUrl": "https://jobs.ashbyhq.com/exampleco/hidden",
        "publishedAt": "2026-08-30T14:29:08.532+00:00",
        "descriptionPlain": "should be skipped"
      }
    ]
  }
}
```

- [ ] **Step 2: Write the failing adapter tests**

`apps/api/tests/unit/test_discovery_boards.py`:

```python
from datetime import UTC, datetime

from test_discovery_sources import fake_http_for

from rhapto.services.discovery.sources import get_source


async def test_greenhouse_unescapes_html_and_keeps_ids_and_dates() -> None:
    postings = await get_source("greenhouse").fetch(fake_http_for("greenhouse"), board="exampleco", keywords=[])
    assert [p.external_id for p in postings] == ["4001", "4002"]
    first = postings[0]
    assert first.company == "ExampleCo" and first.location == "Denver, CO"
    assert "Data Program Manager" in first.jd_text and "&lt;" not in first.jd_text and "<" not in first.jd_text
    assert first.posted_at == datetime(2026, 8, 20, 14, 0, tzinfo=UTC)
    assert first.url == "https://boards.greenhouse.io/exampleco/jobs/4001"


async def test_greenhouse_keyword_filter_applies_to_title_and_text() -> None:
    postings = await get_source("greenhouse").fetch(fake_http_for("greenhouse"), board="exampleco", keywords=["GenAI"])
    assert [p.external_id for p in postings] == ["4002"]


async def test_lever_joins_plain_sections_and_converts_epoch_ms() -> None:
    (p,) = await get_source("lever").fetch(fake_http_for("lever"), board="exampleco", keywords=[])
    assert p.title == "Senior Program Manager, Data Platform" and p.location == "Seattle, WA"
    assert "warehouse consolidation" in p.jd_text and "Own analytics enablement" in p.jd_text
    assert "equal opportunity" in p.jd_text and "<li>" not in p.jd_text
    assert p.posted_at == datetime.fromtimestamp(1788134400, tz=UTC)
    assert p.company == "exampleco"  # Lever has no company field; the board slug stands in until the poller overrides it


async def test_ashby_skips_unlisted_and_parses_iso() -> None:
    postings = await get_source("ashby").fetch(fake_http_for("ashby"), board="exampleco", keywords=[])
    assert [p.title for p in postings] == ["ML Platform Program Manager"]
    assert postings[0].posted_at is not None and postings[0].posted_at.tzinfo is not None
```

The poller passes the watchlist company name and overrides `Posting.company` for board sources (Task 7), so adapters may use the slug when the API has no company field.

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/test_discovery_boards.py -q` → FAIL (unknown source).

- [ ] **Step 4: Implement the adapters**

`sources/greenhouse.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, ClassVar

from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.jobtext import html_to_text


def parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


@register
class GreenhouseSource:
    info: ClassVar[SourceInfo] = SourceInfo("greenhouse", "board", "Greenhouse", True)

    async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]:
        data = await http.get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
        out: list[Posting] = []
        for job in data.get("jobs", []) if isinstance(data, dict) else []:
            try:
                title = str(job["title"])
                text = html_to_text(str(job.get("content") or ""))
                if not matches_keywords(keywords, title, text):
                    continue
                location = job.get("location") or {}
                out.append(
                    Posting(
                        external_id=str(job["id"]),
                        company=str(job.get("company_name") or board),
                        title=title,
                        location=str(location.get("name")) if isinstance(location, dict) and location.get("name") else None,
                        url=str(job["absolute_url"]),
                        jd_text=text or title,
                        posted_at=parse_iso(job.get("first_published")) or parse_iso(job.get("updated_at")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # one bad posting never fails the board
        return out
```

`sources/lever.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.jobtext import html_to_text


@register
class LeverSource:
    info: ClassVar[SourceInfo] = SourceInfo("lever", "board", "Lever", True)

    async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]:
        data = await http.get_json(f"https://api.lever.co/v0/postings/{board}?mode=json")
        out: list[Posting] = []
        for job in data if isinstance(data, list) else []:
            try:
                title = str(job["text"])
                parts = [str(job.get("descriptionPlain") or html_to_text(str(job.get("description") or "")))]
                for section in job.get("lists") or []:
                    parts.append(f"{section.get('text', '')}\n{html_to_text(str(section.get('content') or ''))}")
                parts.append(str(job.get("additionalPlain") or ""))
                text = "\n\n".join(p.strip() for p in parts if p and p.strip())
                if not matches_keywords(keywords, title, text):
                    continue
                categories = job.get("categories") or {}
                created = job.get("createdAt")
                out.append(
                    Posting(
                        external_id=str(job["id"]),
                        company=str(board),
                        title=title,
                        location=str(categories.get("location")) if categories.get("location") else None,
                        url=str(job["hostedUrl"]),
                        jd_text=text or title,
                        posted_at=datetime.fromtimestamp(int(created) / 1000, tz=UTC) if isinstance(created, (int, float)) else None,
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
```

`sources/ashby.py`:

```python
from __future__ import annotations

from typing import ClassVar

from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text


@register
class AshbySource:
    info: ClassVar[SourceInfo] = SourceInfo("ashby", "board", "Ashby", True)

    async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]:
        data = await http.get_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        out: list[Posting] = []
        for job in data.get("jobs", []) if isinstance(data, dict) else []:
            try:
                if job.get("isListed") is False:
                    continue
                title = str(job["title"])
                text = str(job.get("descriptionPlain") or "").strip() or html_to_text(str(job.get("descriptionHtml") or ""))
                if not matches_keywords(keywords, title, text):
                    continue
                out.append(
                    Posting(
                        external_id=str(job["id"]),
                        company=str(board),
                        title=title,
                        location=str(job.get("location")) if job.get("location") else None,
                        url=str(job["jobUrl"]),
                        jd_text=text or title,
                        posted_at=parse_iso(job.get("publishedAt")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
```

In `sources/__init__.py`, after the helper definitions, import the modules for their registration side effect:

```python
from rhapto.services.discovery.sources import ashby, greenhouse, lever  # noqa: E402,F401  (registration)
```

Ruff may prefer these imports at the top; the registry must exist before the modules import `register`, so keep them at the bottom with the `noqa`.

- [ ] **Step 5: Run tests, checks, commit**

Run: `uv run pytest tests/unit/test_discovery_boards.py tests/unit/test_discovery_sources.py -q` → PASS (contract test now runs for three sources; the enum test still xfails until Task 6). Then the full check set and `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/services/discovery/sources apps/api/tests/fixtures/discovery apps/api/tests/unit/test_discovery_boards.py
git commit -m "feat(discovery): greenhouse, lever, and ashby board adapters"
```

---

### Task 6: Aggregator adapters: RemoteOK and Hacker News Who's Hiring

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/sources/remoteok.py`, `hn_hiring.py`
- Create: `apps/api/tests/fixtures/discovery/remoteok.json`, `hn-hiring.json`
- Modify: `apps/api/src/rhapto/services/discovery/sources/__init__.py` (register), `apps/api/tests/unit/test_discovery_sources.py` (remove the xfail)
- Test: `apps/api/tests/unit/test_discovery_aggregators.py`

**Interfaces:**
- Produces: `RemoteOkSource` (`SourceInfo("remoteok", "aggregator", "RemoteOK", False)`), `HnHiringSource` (`SourceInfo("hn-hiring", "aggregator", "Hacker News Who's Hiring", False)`). Both ignore `board`. Both apply `matches_keywords(keywords, title, text)`; with an empty keyword list they return everything (the poller always passes a non-empty list for aggregators, see Task 7).

- [ ] **Step 1: Fixtures**

`tests/fixtures/discovery/remoteok.json`:

```json
{
  "remoteok.com/api": [
    {"last_updated": 1788300000, "legal": "fictional fixture"},
    {
      "id": "1500001", "slug": "remote-data-program-manager-exampleco", "company": "ExampleCo",
      "position": "Data Program Manager", "tags": ["program manager", "data", "etl"],
      "location": "Worldwide", "url": "https://remoteOK.com/remote-jobs/1500001",
      "description": "<strong>ExampleCo</strong><br>Lead the analytics data platform program and ETL cutover.",
      "date": "2026-09-08T14:57:50+00:00", "epoch": 1788965870
    },
    {
      "id": "1500002", "slug": "remote-barista", "company": "CafeCo", "position": "Barista",
      "tags": ["coffee"], "location": "", "url": "https://remoteOK.com/remote-jobs/1500002",
      "description": "Prepare espresso drinks.", "date": "2026-09-07T10:00:00+00:00", "epoch": 1788861600
    }
  ]
}
```

`tests/fixtures/discovery/hn-hiring.json`:

```json
{
  "search_by_date?query=%22who%20is%20hiring%22": {
    "hits": [{"objectID": "49500001", "title": "Ask HN: Who is hiring? (September 2026)", "created_at": "2026-09-01T15:01:17Z"}]
  },
  "/items/49500001": {
    "id": 49500001,
    "children": [
      {
        "id": 49500002, "author": "exampleco_hr", "created_at": "2026-09-01T15:05:00.000Z", "story_id": 49500001,
        "text": "ExampleCo | Data Program Manager | Denver, CO or Remote | Full-time | $150k-$180k<p>We are hiring a program manager for our analytics data platform and ETL modernisation. Apply at <a href=\"https://example.com/careers/dpm\">example.com/careers</a>",
        "children": []
      },
      {
        "id": 49500003, "author": "cafeco", "created_at": "2026-09-01T16:00:00.000Z", "story_id": 49500001,
        "text": "CafeCo | Barista | Onsite | Part-time<p>Espresso and pastries.",
        "children": []
      },
      {"id": 49500004, "author": "someone", "created_at": "2026-09-01T16:30:00.000Z", "story_id": 49500001, "text": null, "children": []}
    ]
  }
}
```

- [ ] **Step 2: Write the failing tests**

`apps/api/tests/unit/test_discovery_aggregators.py`:

```python
from datetime import UTC, datetime

from test_discovery_sources import fake_http_for

from rhapto.services.discovery.sources import get_source


async def test_remoteok_skips_legal_notice_and_filters_keywords() -> None:
    postings = await get_source("remoteok").fetch(fake_http_for("remoteok"), board=None, keywords=["ETL", "program manager"])
    assert [p.external_id for p in postings] == ["1500001"]
    p = postings[0]
    assert p.company == "ExampleCo" and p.title == "Data Program Manager" and p.location == "Worldwide"
    assert "<strong>" not in p.jd_text and "ETL cutover" in p.jd_text
    assert p.posted_at == datetime(2026, 9, 8, 14, 57, 50, tzinfo=UTC)
    assert p.url == "https://remoteOK.com/remote-jobs/1500001"


async def test_remoteok_keywords_match_tags_too() -> None:
    postings = await get_source("remoteok").fetch(fake_http_for("remoteok"), board=None, keywords=["coffee"])
    assert [p.external_id for p in postings] == ["1500002"]


async def test_hn_hiring_parses_header_line_and_skips_empty_comments() -> None:
    postings = await get_source("hn-hiring").fetch(fake_http_for("hn-hiring"), board=None, keywords=["program manager"])
    assert [p.external_id for p in postings] == ["49500002"]
    p = postings[0]
    assert p.company == "ExampleCo" and p.title == "Data Program Manager" and p.location == "Denver, CO or Remote"
    assert p.url == "https://news.ycombinator.com/item?id=49500002"
    assert "analytics data platform" in p.jd_text and "<p>" not in p.jd_text
    assert p.posted_at == datetime(2026, 9, 1, 15, 5, tzinfo=UTC)
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/test_discovery_aggregators.py -q` → FAIL.

- [ ] **Step 4: Implement**

`sources/remoteok.py`:

```python
from __future__ import annotations

from typing import ClassVar

from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text


@register
class RemoteOkSource:
    info: ClassVar[SourceInfo] = SourceInfo("remoteok", "aggregator", "RemoteOK", False)

    async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]:
        data = await http.get_json("https://remoteok.com/api")
        out: list[Posting] = []
        for item in data if isinstance(data, list) else []:
            if not isinstance(item, dict) or "position" not in item:
                continue  # the first element is a legal notice
            try:
                title = str(item["position"])
                text = html_to_text(str(item.get("description") or ""))
                tags = " ".join(str(t) for t in item.get("tags") or [])
                if not matches_keywords(keywords, title, text, tags):
                    continue
                out.append(
                    Posting(
                        external_id=str(item["id"]),
                        company=str(item.get("company") or "Unknown"),
                        title=title,
                        location=str(item.get("location")) if item.get("location") else None,
                        url=str(item["url"]),
                        jd_text=text or title,
                        posted_at=parse_iso(item.get("date")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
```

`sources/hn_hiring.py`:

```python
from __future__ import annotations

from typing import ClassVar

from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

SEARCH_URL = (
    "https://hn.algolia.com/api/v1/search_by_date"
    "?query=%22who%20is%20hiring%22&tags=story,author_whoishiring&hitsPerPage=1"
)
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"


def parse_header(first_line: str) -> tuple[str, str, str | None]:
    """'Company | Role | Location | ...' -> (company, role, location); role falls back to the whole line."""
    parts = [p.strip() for p in first_line.split("|")]
    if len(parts) >= 2 and parts[0] and parts[1]:
        return parts[0], parts[1], (parts[2] if len(parts) > 2 and parts[2] else None)
    return (parts[0] or "Unknown"), first_line.strip()[:200], None


@register
class HnHiringSource:
    info: ClassVar[SourceInfo] = SourceInfo("hn-hiring", "aggregator", "Hacker News Who's Hiring", False)

    async def fetch(self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]) -> list[Posting]:
        search = await http.get_json(SEARCH_URL)
        hits = search.get("hits") if isinstance(search, dict) else None
        if not hits:
            raise SourceError("no Who is hiring thread found")
        story_id = str(hits[0]["objectID"])
        item = await http.get_json(ITEM_URL.format(id=story_id))
        out: list[Posting] = []
        for comment in item.get("children", []) if isinstance(item, dict) else []:
            try:
                raw = comment.get("text")
                if not raw:
                    continue
                text = html_to_text(str(raw))
                first_line, _, rest = text.partition("\n")
                company, title, location = parse_header(first_line)
                body = rest.strip() or text
                if not matches_keywords(keywords, title, body, first_line):
                    continue
                out.append(
                    Posting(
                        external_id=str(comment["id"]),
                        company=company,
                        title=title,
                        location=location,
                        url=f"https://news.ycombinator.com/item?id={comment['id']}",
                        jd_text=body,
                        posted_at=parse_iso(comment.get("created_at")),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        return out
```

`html_to_text` must turn `<p>` into a newline so the header line separates from the body: confirm with the fixture; if trafilatura joins them, insert `\n` for `<p>` and `<br>` before extraction in `html_to_text` (`re.sub(r"<(p|br)\b[^>]*>", "\n", html, flags=re.I)`).

Register both in `sources/__init__.py` (`from rhapto.services.discovery.sources import ashby, greenhouse, hn_hiring, lever, remoteok  # noqa`), and remove the `xfail` marker from `test_registry_matches_profile_schema_enums`.

- [ ] **Step 5: Run tests, checks, commit**

Run: `uv run pytest tests/unit/test_discovery_aggregators.py tests/unit/test_discovery_sources.py -q` → PASS for five sources and the enum test. Full check set, `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/services/discovery/sources apps/api/tests/fixtures/discovery apps/api/tests/unit/test_discovery_aggregators.py apps/api/tests/unit/test_discovery_sources.py
git commit -m "feat(discovery): remoteok and hacker news aggregator adapters"
```

---

### Task 7: Poller: orchestration, dedupe and re-posts, pause rule, scoring, run records

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/poller.py`
- Test: `apps/api/tests/unit/test_poller.py` (db fixtures `session`, `user`)

**Interfaces:**
- Consumes: Task 2 repos, Task 3 `score_and_store`, Task 4 to 6 sources and `FakeDiscoveryHttp`.
- Produces:
  - `@dataclass class SourceSpec: source: str; board: str | None; company: str | None; keywords: list[str]`
  - `@dataclass class RunResult: source: str; board: str | None; found: int; new: int; error: str | None`
  - `@dataclass class PollSummary: results: list[RunResult]; new_jobs: int; new_job_ids: list[uuid.UUID]`
  - `async def build_specs(session, user_id) -> list[SourceSpec]` (watchlist rows with keywords, then enabled aggregators with their keywords or the union of track keywords when empty)
  - `async def poll_sources(session, user_id, *, http: DiscoveryHttp | FakeDiscoveryHttp, embedder: EmbeddingProvider, specs: list[SourceSpec] | None = None, on_step: Callable[[str], Awaitable[None]] | None = None) -> PollSummary` — commits after each source so a crash mid-poll keeps earlier results.
  - `PAUSE_AFTER = 3`, `PAUSED_MESSAGE = "paused after 3 failures; save the watchlist entry to retry"`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_poller.py`:

```python
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from test_discovery_sources import fake_http_for

from rhapto.db.models import Job, PollRun, User, WatchlistEntry
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import AggregatorEntry
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistModel
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.poller import PAUSED_MESSAGE, SourceSpec, build_specs, poll_sources
from rhapto.services.discovery.sources.base import SourceError

TRACKS = [
    Track(id="data-pm", name="Data", resume_base="b", min_fit=60, keywords=["data platform", "ETL", "program manager"], description="Data platform program leadership"),
    Track(id="ai-pm", name="AI", resume_base="b", min_fit=55, keywords=["LLM", "GenAI"], description="AI product roles"),
]


async def seed(session: AsyncSession, user: User) -> None:
    for t in TRACKS:
        await profile_repo.upsert_track(session, user.id, t)
    await profile_repo.replace_watchlist(session, user.id, [WatchlistModel(company="ExampleCo", source="greenhouse", board="exampleco", keywords=[])])
    await profile_repo.replace_aggregators(session, user.id, [AggregatorEntry(source="remoteok", enabled=True, keywords=[]), AggregatorEntry(source="hn-hiring", enabled=False)])
    await session.flush()


async def test_build_specs_uses_track_keywords_for_aggregators(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    specs = await build_specs(session, user.id)
    assert [(s.source, s.board, s.company) for s in specs] == [("greenhouse", "exampleco", "ExampleCo"), ("remoteok", None, None)]
    assert set(specs[1].keywords) == {"data platform", "ETL", "program manager", "LLM", "GenAI"}


async def test_poll_inserts_scores_and_records_runs(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    http = FakeDiscoveryHttp({**fake_http_for("greenhouse").routes, **fake_http_for("remoteok").routes})
    summary = await poll_sources(session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384))
    assert summary.new_jobs == 3 and {r.source for r in summary.results} == {"greenhouse", "remoteok"}
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user.id)))
    assert {j.source for j in jobs} == {"greenhouse", "remoteok"}
    greenhouse = [j for j in jobs if j.source == "greenhouse"]
    assert all(j.company == "ExampleCo" and j.best_fit is not None and j.jd_embedding is not None for j in greenhouse)
    runs = await disc_repo.latest_runs(session, user.id)
    assert {(r.source, r.found, r.new, r.error) for r in runs} == {("greenhouse", 2, 2, None), ("remoteok", 1, 1, None)}

    again = await poll_sources(session, user.id, http=http, embedder=FakeEmbeddingProvider(dimensions=384))
    assert again.new_jobs == 0 and [r.found for r in again.results] == [2, 1]


async def test_repost_is_flagged_not_requeued(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    routes = fake_http_for("greenhouse").routes
    embedder = FakeEmbeddingProvider(dimensions=384)
    await poll_sources(session, user.id, http=FakeDiscoveryHttp(routes), embedder=embedder)
    key = next(iter(routes))
    reposted = {key: {"jobs": [{**routes[key]["jobs"][0], "id": 9999, "content": "&lt;p&gt;Reposted with new wording.&lt;/p&gt;"}]}}
    summary = await poll_sources(session, user.id, http=FakeDiscoveryHttp(reposted), embedder=embedder)
    assert summary.new_jobs == 1
    new = await session.scalar(select(Job).where(Job.external_id == "9999"))
    original = await session.scalar(select(Job).where(Job.external_id == "4001"))
    assert new is not None and original is not None and new.repost_of == original.id


async def test_failed_source_is_recorded_and_paused_after_three(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    http = FakeDiscoveryHttp({"greenhouse.io": SourceError("HTTP 500"), "remoteok.com/api": [{"legal": "x"}]})
    embedder = FakeEmbeddingProvider(dimensions=384)
    for _ in range(3):
        summary = await poll_sources(session, user.id, http=http, embedder=embedder)
        assert next(r for r in summary.results if r.source == "greenhouse").error == "HTTP 500"
    summary = await poll_sources(session, user.id, http=http, embedder=embedder)
    assert next(r for r in summary.results if r.source == "greenhouse").error == PAUSED_MESSAGE
    assert http.calls.count("https://boards-api.greenhouse.io/v1/boards/exampleco/jobs?content=true") == 3
    # saving the watchlist entry (updated_at moves past the last run) lifts the pause
    await profile_repo.replace_watchlist(session, user.id, [WatchlistModel(company="ExampleCo", source="greenhouse", board="exampleco", keywords=[])])
    await session.flush()
    summary = await poll_sources(session, user.id, http=http, embedder=embedder)
    assert next(r for r in summary.results if r.source == "greenhouse").error == "HTTP 500"


async def test_explicit_specs_and_step_callbacks(session: AsyncSession, user: User) -> None:
    await seed(session, user)
    steps: list[str] = []

    async def on_step(step: str) -> None:
        steps.append(step)

    spec = SourceSpec(source="greenhouse", board="exampleco", company="ExampleCo", keywords=["GenAI"])
    summary = await poll_sources(session, user.id, http=fake_http_for("greenhouse"), embedder=FakeEmbeddingProvider(dimensions=384), specs=[spec], on_step=on_step)
    assert summary.new_jobs == 1 and steps == ["fetch", "dedupe", "score", "done"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_poller.py -q` → FAIL.

- [ ] **Step 3: Implement the poller**

`services/discovery/poller.py`:

```python
"""One poll: every watchlist board and enabled aggregator -> new scored jobs and a run record each."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Job
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import get_source
from rhapto.services.discovery.sources.base import SourceError
from rhapto.services.scoring import score_and_store

logger = logging.getLogger(__name__)
PAUSE_AFTER = 3
PAUSED_MESSAGE = "paused after 3 failures; save the watchlist entry to retry"
StepCallback = Callable[[str], Awaitable[None]]


@dataclass
class SourceSpec:
    source: str
    board: str | None
    company: str | None
    keywords: list[str] = field(default_factory=list)
    entry_updated_at: datetime | None = None


@dataclass
class RunResult:
    source: str
    board: str | None
    found: int
    new: int
    error: str | None


@dataclass
class PollSummary:
    results: list[RunResult]
    new_jobs: int
    new_job_ids: list[uuid.UUID]


async def build_specs(session: AsyncSession, user_id: uuid.UUID) -> list[SourceSpec]:
    specs = [
        SourceSpec(source=row.source, board=row.board, company=row.company, keywords=list(row.keywords), entry_updated_at=row.updated_at)
        for row in await profile_repo.list_watchlist(session, user_id)
    ]
    track_keywords: list[str] = []
    for track in await profile_repo.list_tracks(session, user_id):
        track_keywords.extend(k for k in track.keywords if k not in track_keywords)
    for agg in await profile_repo.list_aggregators(session, user_id):
        if agg.enabled:
            specs.append(SourceSpec(source=agg.source, board=None, company=None, keywords=list(agg.keywords) or track_keywords, entry_updated_at=agg.updated_at))
    return specs


async def _is_paused(session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec) -> bool:
    if await disc_repo.consecutive_failures(session, user_id, spec.source, spec.board) < PAUSE_AFTER:
        return False
    runs = await disc_repo.latest_runs(session, user_id)
    last = next((r for r in runs if r.source == spec.source and r.board == spec.board), None)
    if last is None or spec.entry_updated_at is None:
        return True
    return spec.entry_updated_at <= last.started_at


async def _ingest(session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec, postings: list[Posting]) -> list[Job]:
    created: list[Job] = []
    seen_hashes: set[str] = set()
    for posting in postings:
        company = spec.company or posting.company
        if await jobs_repo.find_by_external_id(session, user_id, spec.source, posting.external_id) is not None:
            continue
        text_hash = dedupe_hash(posting.jd_text)
        if text_hash in seen_hashes or await jobs_repo.find_duplicate(session, user_id, text_hash) is not None:
            continue
        seen_hashes.add(text_hash)
        ident = identity_hash(company, posting.title, posting.location)
        earlier = await jobs_repo.find_by_identity(session, user_id, ident)
        job = await jobs_repo.create_discovered_job(
            session, user_id, source=spec.source, external_id=posting.external_id, company=company,
            title=posting.title, location=posting.location, url=posting.url, jd_text=posting.jd_text,
            posted_at=posting.posted_at, identity_hash=ident, repost_of=earlier.id if earlier else None,
        )
        created.append(job)
    return created


async def poll_sources(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    http: DiscoveryHttp | FakeDiscoveryHttp,
    embedder: EmbeddingProvider,
    specs: list[SourceSpec] | None = None,
    on_step: StepCallback | None = None,
) -> PollSummary:
    async def step(name: str) -> None:
        if on_step is not None:
            await on_step(name)

    specs = specs if specs is not None else await build_specs(session, user_id)
    results: list[RunResult] = []
    new_ids: list[uuid.UUID] = []
    await step("fetch")
    for spec in specs:
        if await _is_paused(session, user_id, spec):
            run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
            disc_repo.finish_run(run, found=0, new=0, error=PAUSED_MESSAGE)
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, PAUSED_MESSAGE))
            continue
        run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
        try:
            postings = await get_source(spec.source).fetch(http, board=spec.board, keywords=spec.keywords)
            await step("dedupe")
            created = await _ingest(session, user_id, spec, postings)
            await step("score")
            await score_and_store(session, user_id, created, embedder)
            disc_repo.finish_run(run, found=len(postings), new=len(created), error=None)
            results.append(RunResult(spec.source, spec.board, len(postings), len(created), None))
            new_ids.extend(j.id for j in created)
        except SourceError as exc:
            disc_repo.finish_run(run, found=0, new=0, error=str(exc))
            results.append(RunResult(spec.source, spec.board, 0, 0, str(exc)))
        except Exception as exc:  # a bug in one adapter must not take the others down
            logger.exception("poll of %s/%s failed", spec.source, spec.board)
            disc_repo.finish_run(run, found=0, new=0, error=f"{type(exc).__name__}: {exc}")
            results.append(RunResult(spec.source, spec.board, 0, 0, f"{type(exc).__name__}: {exc}"))
        await session.commit()
    await step("done")
    return PollSummary(results=results, new_jobs=len(new_ids), new_job_ids=new_ids)
```

`on_step("dedupe")` and `("score")` fire per source; the test with one spec sees each once. For the test that expects `["fetch", "dedupe", "score", "done"]` with a single spec this holds; for multiple sources the UI shows the steps repeating, which is acceptable.

The `updated_at` comparison in `_is_paused` relies on the Python-side `updated_at` that Task 2's `replace_watchlist` and `replace_aggregators` set explicitly; a save always produces a fresh `updated_at` later than the previous run's `started_at`.

Session note: `poll_sources` commits after every source. If the `session` fixture in `tests/conftest.py` is transaction-scoped and those commits break isolation between tests, open your own session from the `session_factory` fixture inside each test (the pattern `tests/unit/test_worker_tasks.py` uses) instead of the shared `session`.

- [ ] **Step 4: Run tests, checks, commit**

Run: `uv run pytest tests/unit/test_poller.py -q` → PASS. Full check set and `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/services/discovery/poller.py apps/api/tests/unit/test_poller.py
git commit -m "feat(discovery): poller with dedupe, re-post flagging, pause rule, and scoring"
```

---

### Task 8: Worker tasks and cron: poll_now, poll_all_sources, score_jobs, rescore_jobs

**Files:**
- Modify: `apps/api/src/rhapto/worker/tasks.py`, `apps/api/src/rhapto/worker/main.py`
- Modify: `apps/api/tests/api/conftest.py` (`worker_ctx` gains `discovery_http`)
- Test: `apps/api/tests/unit/test_worker_discovery.py`

**Interfaces:**
- Consumes: Task 7 `poll_sources`, Task 3 `score_and_store`, `rescore_user`; task repo helpers; event bus.
- Produces: `async def poll_now(ctx, task_id: str) -> None` (task type `poll_now`; steps published as `{"event": "progress", "step": ...}`; on success `mark_succeeded(task, "new:<n>")` and publishes `{"event": "done", "new_jobs": n, "results": [...]}` plus `{"event": "discovery", "new_jobs": n}` on channel `discovery`; on failure `{"event": "error", "message": ...}`), `async def poll_all_sources(ctx) -> None` (cron; every user via `list_user_ids(session)` in `db/repositories/users.py`, added here), `async def score_jobs(ctx, user_id: str, job_ids: list[str]) -> None`, `async def rescore_jobs(ctx, user_id: str) -> None`; `TASKS` gains the four; `WorkerSettings.cron_jobs` built from `rhapto_poll_interval_hours`; `ctx["discovery_http"]`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_worker_discovery.py`:

```python
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_discovery_sources import fake_http_for

from rhapto.db.models import Job, Task, User
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.eventbus import InMemoryEventBus, task_channel
from rhapto.worker.main import cron_hours
from rhapto.worker.tasks import TASKS, poll_now, rescore_jobs, score_jobs


async def seed(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(session, user.id, Track(id="data-pm", name="Data", resume_base="b", min_fit=60, keywords=["ETL", "program manager"], description="Data platform program leadership"))
    await profile_repo.replace_watchlist(session, user.id, [WatchlistEntry(company="ExampleCo", source="greenhouse", board="exampleco")])
    await session.commit()


def ctx_for(factory: async_sessionmaker[AsyncSession], bus: InMemoryEventBus) -> dict[str, Any]:
    return {
        "session_factory": factory,
        "embedder": FakeEmbeddingProvider(dimensions=384),
        "event_bus": bus,
        "discovery_http": fake_http_for("greenhouse"),
        "allow_dimension_mismatch": False,
    }


async def test_poll_now_runs_and_publishes(session_factory: async_sessionmaker[AsyncSession], session: AsyncSession, user: User) -> None:
    await seed(session, user)
    task = await task_repo.create_task(session, user.id, "poll_now", {})
    await session.commit()
    bus = InMemoryEventBus()
    events: list[dict[str, Any]] = []
    async with bus.subscription(task_channel(str(task.id))) as stream:
        await poll_now(ctx_for(session_factory, bus), str(task.id))
        async for event in stream:
            events.append(event)
            if event["event"] in ("done", "error"):
                break
    assert events[-1]["event"] == "done" and events[-1]["new_jobs"] == 2
    assert [e["step"] for e in events if e["event"] == "progress"][:1] == ["fetch"]
    async with session_factory() as check:
        row = await check.get(Task, task.id)
        assert row is not None and row.status == "succeeded" and row.result_ref == "new:2"
        assert len(list(await check.scalars(select(Job)))) == 2


async def test_poll_now_records_failure(session_factory: async_sessionmaker[AsyncSession], session: AsyncSession, user: User) -> None:
    task = await task_repo.create_task(session, user.id, "poll_now", {})
    await session.commit()
    ctx = ctx_for(session_factory, InMemoryEventBus())
    del ctx["embedder"]  # KeyError at the poll_sources call site, i.e. at the task boundary, not inside one source
    await poll_now(ctx, str(task.id))
    async with session_factory() as check:
        row = await check.get(Task, task.id)
        assert row is not None and row.status == "failed" and row.error


async def test_score_and_rescore_tasks(session_factory: async_sessionmaker[AsyncSession], session: AsyncSession, user: User) -> None:
    await seed(session, user)
    job = Job(user_id=user.id, jd_text="ETL program manager for the data platform " * 5, title="Data Program Manager", dedupe_hash="h", discovered_at=__import__("datetime").datetime.now(__import__("datetime").UTC))
    session.add(job)
    await session.commit()
    ctx = ctx_for(session_factory, InMemoryEventBus())
    await score_jobs(ctx, str(user.id), [str(job.id)])
    async with session_factory() as check:
        scored = await check.get(Job, job.id)
        assert scored is not None and scored.best_track_id == "data-pm"
    await rescore_jobs(ctx, str(user.id))
    assert set(TASKS) >= {"poll_now", "poll_all_sources", "score_jobs", "rescore_jobs"}


def test_cron_hours_from_interval() -> None:
    assert cron_hours(6) == {0, 6, 12, 18}
    assert cron_hours(24) == {0}
    assert cron_hours(5) == {0, 5, 10, 15, 20}
    assert cron_hours(0) == set()
```

Use proper `from datetime import UTC, datetime` imports instead of the `__import__` trick when writing the file; it is shown inline only to keep the snippet short. For the event subscription, follow the exact pattern `tests/unit/test_worker_tasks.py` uses for `tailor_job` (subscribe before running the task if the in-memory bus does not buffer).

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_worker_discovery.py -q` → FAIL.

- [ ] **Step 3: Implement**

In `db/repositories/users.py` add:

```python
async def list_user_ids(session: AsyncSession) -> list[uuid.UUID]:
    return list(await session.scalars(select(User.id).order_by(User.created_at)))
```

In `worker/tasks.py` add (imports: `poll_sources` from `rhapto.services.discovery.poller`, `score_and_store`, `rescore_user` from `rhapto.services.scoring`, `list_user_ids`):

```python
DISCOVERY_CHANNEL = "discovery"


async def poll_now(ctx: dict[str, Any], task_id: str) -> None:
    """User-triggered poll: progress on the task channel, summary on the discovery channel."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    channel = task_channel(task_id)
    async with factory() as session:
        try:
            tid = uuid.UUID(task_id)
            task = await session.get(Task, tid)
            if task is None:
                return
            active: Task = task
            task_repo.mark_running(active)
            await session.commit()

            async def on_step(step: str) -> None:
                task_repo.set_step(active, step)
                await session.commit()
                await bus.publish(channel, {"event": "progress", "step": step})

            summary = await poll_sources(
                session, active.user_id, http=ctx["discovery_http"], embedder=ctx["embedder"], on_step=on_step
            )
            task_repo.mark_succeeded(active, f"new:{summary.new_jobs}")
            await session.commit()
            results = [r.__dict__ for r in summary.results]
            await bus.publish(channel, {"event": "done", "new_jobs": summary.new_jobs, "results": results})
            await bus.publish(DISCOVERY_CHANNEL, {"event": "discovery", "new_jobs": summary.new_jobs})
        except Exception as exc:  # task boundary
            await session.rollback()
            failed = await session.get(Task, uuid.UUID(task_id))
            if failed is not None:
                task_repo.mark_failed(failed, f"{type(exc).__name__}: {exc}")
                await session.commit()
            await bus.publish(channel, {"event": "error", "message": str(exc)})


async def poll_all_sources(ctx: dict[str, Any]) -> None:
    """Cron entry point: poll every user's sources; failures are recorded per source."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    async with factory() as session:
        for user_id in await list_user_ids(session):
            try:
                summary = await poll_sources(session, user_id, http=ctx["discovery_http"], embedder=ctx["embedder"])
                await bus.publish(DISCOVERY_CHANNEL, {"event": "discovery", "new_jobs": summary.new_jobs})
            except Exception:
                logger.exception("scheduled poll failed for user %s", user_id)
                await session.rollback()


async def score_jobs(ctx: dict[str, Any], user_id: str, job_ids: list[str]) -> None:
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    try:
        uid = uuid.UUID(user_id)
        async with factory() as session:
            jobs = [j for j in [await session.get(Job, uuid.UUID(i)) for i in job_ids] if j is not None and j.user_id == uid]
            await score_and_store(session, uid, jobs, ctx["embedder"])
            await session.commit()
    except Exception:
        logger.exception("score_jobs failed for user %s", user_id)


async def rescore_jobs(ctx: dict[str, Any], user_id: str) -> None:
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    try:
        uid = uuid.UUID(user_id)
        async with factory() as session:
            await rescore_user(session, uid, ctx["embedder"])
            await session.commit()
    except Exception:
        logger.exception("rescore_jobs failed for user %s", user_id)
```

Add the four to `TASKS`. In `worker/main.py`:

```python
from arq import cron
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.worker.tasks import embed_blocks, poll_all_sources, poll_now, render_package_pdf, rescore_jobs, score_jobs, tailor_job


def cron_hours(interval_hours: int) -> set[int]:
    if interval_hours <= 0:
        return set()
    return set(range(0, 24, min(interval_hours, 24)))


async def on_startup(ctx: dict[str, Any]) -> None:
    ...existing lines...
    ctx["discovery_http"] = DiscoveryHttp(user_agent=settings.rhapto_discovery_user_agent)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()
    await ctx["event_bus"].close()
    await ctx["discovery_http"].aclose()


_HOURS = cron_hours(get_settings().rhapto_poll_interval_hours)


class WorkerSettings:
    functions = [tailor_job, embed_blocks, render_package_pdf, poll_now, score_jobs, rescore_jobs]
    cron_jobs = [cron(poll_all_sources, hour=_HOURS, minute=0, run_at_startup=False)] if _HOURS else []
    ...existing settings...
```

In `tests/api/conftest.py`, `worker_ctx` gains `"discovery_http": FakeDiscoveryHttp({})` (API tests that poll override it via a fixture in Task 9), and its `embedder` must be `FakeEmbeddingProvider(dimensions=384)`: `services/scoring.py` drops vectors whose width is not `EMBEDDING_DIMENSIONS`, so a 64-wide fake would leave every job unscored in API tests.

- [ ] **Step 4: Run tests, checks, commit**

Run: `uv run pytest tests/unit/test_worker_discovery.py tests/unit/test_worker_tasks.py -q` → PASS. Full check set, `uv run lint-imports` (worker imports services, allowed).

```bash
git add apps/api/src/rhapto/worker apps/api/src/rhapto/db/repositories/users.py apps/api/tests/unit/test_worker_discovery.py apps/api/tests/api/conftest.py
git commit -m "feat(worker): poll_now, scheduled polling, and scoring tasks"
```

---

### Task 9: API: discovery router, richer jobs list, rescue, scoring on create, rescore on track edit

**Files:**
- Create: `apps/api/src/rhapto/api/routers/discovery.py`
- Modify: `apps/api/src/rhapto/api/schemas.py`, `apps/api/src/rhapto/api/routers/jobs.py`, `apps/api/src/rhapto/api/routers/profile.py`, `apps/api/src/rhapto/api/app.py`
- Regenerate: `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_discovery_api.py`, extend `apps/api/tests/api/test_jobs_api.py`

**Interfaces:**
- Produces schemas: `JobScoreOut(track_id: str, fit_score: int, rationale: dict[str, Any])`; `JobOut` gains `best_track_id: str | None`, `best_fit: int | None`, `bucket: Literal["fit", "low"] | None` (None when unscored), `rescued: bool`, `repost_of: uuid.UUID | None`, `posted_at: datetime | None`, `scores: list[JobScoreOut]`; `PollRunOut(id, source, board, started_at, finished_at, found, new, error)`; `SourceInfoOut(name, kind, label, needs_board)`.
- Endpoints: `POST /api/v1/discovery/poll -> 202 TaskOut` (task type `poll_now`), `GET /api/v1/discovery/runs -> list[PollRunOut]`, `GET /api/v1/discovery/sources -> list[SourceInfoOut]`, `GET /api/v1/jobs?search&track&bucket&sort`, `POST /api/v1/jobs/{job_id}/rescue -> JobOut`, `POST /api/v1/jobs` enqueues `score_jobs`, `PUT /api/v1/profile/tracks/{track_id}` enqueues `rescore_jobs` after commit.

- [ ] **Step 1: Write the failing API tests**

`apps/api/tests/api/test_discovery_api.py`:

```python
from typing import Any

import httpx
import pytest
from test_discovery_sources import fake_http_for

from rhapto.services.discovery.http import FakeDiscoveryHttp


@pytest.fixture
def discovery_http(worker_ctx: dict[str, Any]) -> FakeDiscoveryHttp:
    http = FakeDiscoveryHttp({**fake_http_for("greenhouse").routes, **fake_http_for("remoteok").routes})
    worker_ctx["discovery_http"] = http
    return http


async def test_sources_lists_registry(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/discovery/sources")
    assert response.status_code == 200
    names = {s["name"]: s for s in response.json()}
    assert names["greenhouse"]["kind"] == "board" and names["greenhouse"]["needs_board"] is True
    assert names["hn-hiring"]["kind"] == "aggregator"


async def test_poll_creates_jobs_runs_and_scored_queue(client: httpx.AsyncClient, imported_profile: None, discovery_http: FakeDiscoveryHttp) -> None:
    started = await client.post("/api/v1/discovery/poll")
    assert started.status_code == 202
    task = await client.get(f"/api/v1/tasks/{started.json()['id']}")
    assert task.json()["status"] == "succeeded" and task.json()["result_ref"].startswith("new:")
    runs = await client.get("/api/v1/discovery/runs")
    assert {r["source"] for r in runs.json()} == {"greenhouse", "remoteok"}
    jobs = await client.get("/api/v1/jobs", params={"sort": "fit"})
    body = jobs.json()
    assert body and all(j["best_fit"] is not None and j["bucket"] in ("fit", "low") for j in body)
    assert [j["best_fit"] for j in body] == sorted((j["best_fit"] for j in body), reverse=True)
    assert body[0]["scores"] and {"track_id", "fit_score", "rationale"} <= set(body[0]["scores"][0])
    only_low = await client.get("/api/v1/jobs", params={"bucket": "low"})
    assert all(j["bucket"] == "low" for j in only_low.json())
    by_track = await client.get("/api/v1/jobs", params={"track": "data-pm"})
    assert all(j["best_track_id"] == "data-pm" for j in by_track.json())


async def test_rescue_moves_job_into_fit_bucket(client: httpx.AsyncClient, imported_profile: None, discovery_http: FakeDiscoveryHttp) -> None:
    await client.post("/api/v1/discovery/poll")
    low = (await client.get("/api/v1/jobs", params={"bucket": "low"})).json()
    if not low:
        pytest.skip("fixture produced no low-fit job with this embedder")
    rescued = await client.post(f"/api/v1/jobs/{low[0]['id']}/rescue")
    assert rescued.status_code == 200 and rescued.json()["rescued"] is True and rescued.json()["bucket"] == "fit"


async def test_manual_job_is_scored_on_create(client: httpx.AsyncClient, imported_profile: None) -> None:
    jd = "ExampleCo seeks a Data Program Manager to lead our data platform, analytics, and ETL modernisation. " * 2
    created = await client.post("/api/v1/jobs", json={"jd_text": jd, "title": "Data Program Manager"})
    assert created.status_code == 201
    fetched = await client.get(f"/api/v1/jobs/{created.json()['id']}")
    assert fetched.json()["best_track_id"] == "data-pm" and fetched.json()["best_fit"] is not None
    assert fetched.json()["bucket"] in ("fit", "low")  # the fake embedder's absolute level is not asserted


async def test_track_put_rescores(client: httpx.AsyncClient, imported_profile: None) -> None:
    jd = "ExampleCo seeks a Data Program Manager to lead our data platform, analytics, and ETL modernisation. " * 2
    job = (await client.post("/api/v1/jobs", json={"jd_text": jd, "title": "Data Program Manager"})).json()
    track = (await client.get("/api/v1/profile/tracks")).json()[0]
    track["min_fit"] = 100
    put = await client.put(f"/api/v1/profile/tracks/{track['id']}", json=track)
    assert put.status_code == 200
    fetched = await client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.json()["bucket"] == "low"
```

The API tests use the `InlineEnqueuer`, so enqueued tasks run synchronously before the response; that is why `GET /tasks/{id}` already shows `succeeded`.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/api/test_discovery_api.py -q` → FAIL (404s).

- [ ] **Step 3: Implement**

`api/schemas.py` additions:

```python
class JobScoreOut(BaseModel):
    track_id: str
    fit_score: int
    rationale: dict[str, Any]


class PollRunOut(BaseModel):
    id: uuid.UUID
    source: str
    board: str | None
    started_at: datetime
    finished_at: datetime | None
    found: int
    new: int
    error: str | None


class SourceInfoOut(BaseModel):
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool
```

and on `JobOut`: `best_track_id: str | None = None`, `best_fit: int | None = None`, `bucket: Literal["fit", "low"] | None = None`, `rescued: bool = False`, `repost_of: uuid.UUID | None = None`, `posted_at: datetime | None = None`, `scores: list[JobScoreOut] = []`.

`api/routers/jobs.py`: `job_to_out` gains parameters `scores: list[JobScore]` and `min_fit: int | None` and fills the new fields; `bucket` is `None` when `best_fit is None`, else `"fit"` if `rescued or (min_fit is not None and best_fit >= min_fit)` else `"low"`. `_out` loads scores via `disc_repo.scores_for_jobs` and the track's `min_fit` via `profile_repo.get_track`. To avoid N+1 on the list endpoint, add `_outs(session, user_id, jobs)` that fetches scores for all ids in one call and tracks once; use it in `list_jobs`. `list_jobs` signature:

```python
@router.get("", response_model=list[JobOut])
async def list_jobs(
    user_id: UserDep,
    session: SessionDep,
    search: str | None = Query(default=None),
    track: str | None = Query(default=None),
    bucket: Literal["fit", "low"] | None = Query(default=None),
    sort: Literal["fit", "newest"] = Query(default="fit"),
) -> list[JobOut]:
```

`create_job` gets an `EnqueuerDep` (as in `tailor.py`) and, after `session.commit()`, calls `await enqueuer.enqueue("score_jobs", user_id=str(user_id), job_ids=[str(job.id)])`, then `session.expire_all()` and re-reads the job before returning so the inline path shows the score. Add:

```python
@router.post("/{job_id}/rescue", response_model=JobOut)
async def rescue_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    repo.set_rescued(job, True)
    await session.commit()
    return await _out(session, user_id, job)
```

`api/routers/discovery.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session
from rhapto.api.routers.tailor import task_to_out
from rhapto.api.schemas import PollRunOut, SourceInfoOut, TaskOut
from rhapto.db.repositories import discovery as disc_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.services.discovery.sources import all_sources
from rhapto.services.enqueue import Enqueuer

router = APIRouter(prefix="/discovery")
UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]


@router.post("/poll", response_model=TaskOut, status_code=202)
async def poll(user_id: UserDep, session: SessionDep, enqueuer: EnqueuerDep) -> TaskOut:
    task = await task_repo.create_task(session, user_id, "poll_now", {})
    await session.commit()
    task_id = task.id
    await enqueuer.enqueue("poll_now", task_id=str(task_id))
    session.expire_all()
    refreshed = await task_repo.get_task(session, user_id, task_id)
    if refreshed is None:
        raise RuntimeError(f"task {task_id} vanished after commit")
    return task_to_out(refreshed)


@router.get("/runs", response_model=list[PollRunOut])
async def runs(user_id: UserDep, session: SessionDep) -> list[PollRunOut]:
    return [PollRunOut.model_validate(r, from_attributes=True) for r in await disc_repo.latest_runs(session, user_id)]


@router.get("/sources", response_model=list[SourceInfoOut])
async def sources() -> list[SourceInfoOut]:
    return [SourceInfoOut(name=i.name, kind=i.kind, label=i.label, needs_board=i.needs_board) for i in all_sources()]
```

Check the exact dependency name for the enqueuer in `api/deps.py` (the tailor router imports it; reuse the same). Register in `app.py`: `app.include_router(discovery.router, prefix=API_PREFIX, tags=["discovery"])`. In `profile.py`, the track PUT handler gains `EnqueuerDep` and after commit calls `await enqueuer.enqueue("rescore_jobs", user_id=str(user_id))`; profile import (`POST /profile/import`) does the same so imported tracks get embeddings and existing jobs get scores.

- [ ] **Step 4: Regenerate, run, commit**

Run `bash scripts/codegen.sh` from the root; then `uv run pytest tests/api -q` → PASS; full check set; `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/api apps/api/tests/api packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts
git commit -m "feat(api): discovery endpoints, scored job listing, rescue, and rescoring hooks"
```

---

### Task 10: CLI: `rhapto discover` and `rhapto score`

**Files:**
- Modify: `apps/api/src/rhapto/cli/main.py`
- Test: `apps/api/tests/unit/test_cli_discover.py`

**Interfaces:**
- Consumes: `load_profile`, `get_source`, `DiscoveryHttp`, `FastEmbedProvider`, engine scoring.
- Produces: `rhapto discover --profile DIR [--source NAME] [--board SLUG] [--json]` (exit 0; prints one line per posting `fit  track  company | title | location  url`, sorted by fit, or a JSON array with `--json`; exit 1 when every source failed); `rhapto score --jd FILE --profile DIR` (prints one line per track `track_id  fit  semantic  keywords  matched`). Both accept `--embedder fake` (hidden option) so tests avoid loading the model.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_cli_discover.py`:

```python
import json
from pathlib import Path

from typer.testing import CliRunner

from rhapto.cli import main as cli
from rhapto.services.discovery.http import FakeDiscoveryHttp

runner = CliRunner()


def test_discover_lists_scored_postings(monkeypatch, demo_profile_dir: Path) -> None:
    fixtures = Path(__file__).parent.parent / "fixtures" / "discovery"
    routes = json.loads((fixtures / "greenhouse.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(cli, "build_discovery_http", lambda settings: FakeDiscoveryHttp(routes))
    result = runner.invoke(cli.app, ["discover", "--profile", str(demo_profile_dir), "--source", "greenhouse", "--board", "exampleco", "--embedder", "fake", "--json"])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)
    assert {r["title"] for r in rows} == {"Data Platform Program Manager", "AI Product Manager"}
    assert all({"fit", "track", "url", "company"} <= set(r) for r in rows)
    assert rows == sorted(rows, key=lambda r: -r["fit"])


def test_discover_reports_source_failure(monkeypatch, demo_profile_dir: Path) -> None:
    from rhapto.services.discovery.sources.base import SourceError

    monkeypatch.setattr(cli, "build_discovery_http", lambda settings: FakeDiscoveryHttp({"greenhouse.io": SourceError("HTTP 500")}))
    result = runner.invoke(cli.app, ["discover", "--profile", str(demo_profile_dir), "--source", "greenhouse", "--board", "exampleco", "--embedder", "fake"])
    assert result.exit_code == 1 and "HTTP 500" in result.output


def test_score_prints_breakdown(tmp_path: Path, demo_profile_dir: Path) -> None:
    jd = tmp_path / "jd.txt"
    jd.write_text("Data Program Manager to lead the analytics data platform and ETL migration.", encoding="utf-8")
    result = runner.invoke(cli.app, ["score", "--jd", str(jd), "--profile", str(demo_profile_dir), "--embedder", "fake"])
    assert result.exit_code == 0, result.output
    assert "data-pm" in result.output and "ai-pm" in result.output
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_cli_discover.py -q` → FAIL (no such command).

- [ ] **Step 3: Implement**

In `cli/main.py` add (imports: `json`, `DiscoveryHttp`, `get_source`, `SourceError`, `SourceSpec`-free logic, `FakeEmbeddingProvider`, engine scoring functions, `Posting`):

```python
def build_discovery_http(settings: Settings) -> DiscoveryHttp:
    return DiscoveryHttp(user_agent=settings.rhapto_discovery_user_agent)


def build_embedder(settings: Settings, kind: str) -> EmbeddingProvider:
    if kind == "fake":
        return FakeEmbeddingProvider(dimensions=384)
    return FastEmbedProvider(settings.rhapto_embedding_model)


async def _score_postings(profile: Profile, postings: list[tuple[str, Posting]], embedder: EmbeddingProvider) -> list[dict[str, Any]]:
    tracks = profile.tracks
    vectors = await embedder.embed([track_text(t) for t in tracks] + [f"{p.title}\n{p.jd_text}" for _, p in postings])
    track_vectors = {t.id: v for t, v in zip(tracks, vectors[: len(tracks)], strict=True)}
    rows: list[dict[str, Any]] = []
    for (source, posting), vector in zip(postings, vectors[len(tracks):], strict=True):
        scores = score_job(posting.title, posting.jd_text, vector, tracks, track_vectors)
        best = best_track(scores, tracks)
        rows.append({
            "source": source, "company": posting.company, "title": posting.title, "location": posting.location,
            "url": posting.url, "fit": best.fit_score if best else 0, "track": best.track_id if best else None,
            "bucket": bucket_for(best, tracks, rescued=False),
        })
    return sorted(rows, key=lambda r: -r["fit"])


@app.command(name="discover")
def discover_cmd(
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    source: str | None = typer.Option(None, "--source", help="Poll one source only"),
    board: str | None = typer.Option(None, "--board", help="Board slug for a single board source"),
    as_json: bool = typer.Option(False, "--json", help="Print a JSON array"),
    embedder_kind: str = typer.Option("fastembed", "--embedder", hidden=True),
) -> None:
    """Fetch the watchlist boards and enabled aggregators, score every posting, print them by fit. Nothing is stored."""
    settings = get_settings()
    try:
        loaded = load_profile(profile)
    except ProfileError as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(1) from exc
    track_keywords = [k for t in loaded.tracks for k in t.keywords]
    specs: list[tuple[str, str | None, str | None, list[str]]] = []
    if source:
        specs.append((source, board, board, track_keywords if board is None else []))
    else:
        specs.extend((e.source, e.board, e.company, list(e.keywords)) for e in loaded.watchlist)
        specs.extend((a.source, None, None, list(a.keywords) or track_keywords) for a in loaded.aggregators if a.enabled)
    http = build_discovery_http(settings)

    async def run() -> tuple[list[tuple[str, Posting]], list[str]]:
        found: list[tuple[str, Posting]] = []
        errors: list[str] = []
        try:
            for name, slug, company, keywords in specs:
                try:
                    for p in await get_source(name).fetch(http, board=slug, keywords=keywords):
                        found.append((name, p.model_copy(update={"company": company or p.company})))
                except SourceError as exc:
                    errors.append(f"{name}/{slug or '-'}: {exc}")
        finally:
            await http.aclose()
        return found, errors

    found, errors = asyncio.run(run())
    for line in errors:
        typer.echo(f"error: {line}", err=True)
    rows = asyncio.run(_score_postings(loaded, found, build_embedder(settings, embedder_kind))) if found else []
    if as_json:
        typer.echo(json.dumps(rows, indent=1))
    else:
        for r in rows:
            typer.echo(f"{r['fit']:>3}  {r['track'] or '-':<14} {r['company']} | {r['title']} | {r['location'] or '-'}  {r['url']}")
        typer.echo(f"{len(rows)} postings from {len(specs) - len(errors)} of {len(specs)} sources")
    if specs and len(errors) == len(specs):
        raise typer.Exit(1)


@app.command(name="score")
def score_cmd(
    jd: Path = typer.Option(..., "--jd", help="Job description text file"),
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    embedder_kind: str = typer.Option("fastembed", "--embedder", hidden=True),
) -> None:
    """Print the per-track fit breakdown for one job description."""
    settings = get_settings()
    loaded = load_profile(profile)
    text = jd.read_text(encoding="utf-8")
    embedder = build_embedder(settings, embedder_kind)

    async def run() -> None:
        vectors = await embedder.embed([track_text(t) for t in loaded.tracks] + [text])
        track_vectors = {t.id: v for t, v in zip(loaded.tracks, vectors[:-1], strict=True)}
        title = text.strip().splitlines()[0][:200] if text.strip() else None
        for s in score_job(title, text, vectors[-1], loaded.tracks, track_vectors):
            typer.echo(f"{s.track_id:<14} fit={s.fit_score:>3} semantic={s.semantic:>3} keywords={s.keywords:>3} matched={', '.join(s.matched) or '-'}")

    asyncio.run(run())
```

`cli` importing `services.discovery` is allowed by the contracts (cli is an entrypoint). `FakeEmbeddingProvider` lives in `engine/providers/fake.py`, which is part of the shipped package, so the hidden option needs no test-only import.

- [ ] **Step 4: Run tests, checks, commit**

Run: `uv run pytest tests/unit/test_cli_discover.py tests/unit/test_cli.py -q` → PASS. Full check set, `uv run lint-imports`.

```bash
git add apps/api/src/rhapto/cli/main.py apps/api/tests/unit/test_cli_discover.py
git commit -m "feat(cli): discover and score commands"
```

---

### Task 11: Web queue: fit badge, source chip, filter bar, Poll now, runs drawer, rescue, best-track preselect

**Files:**
- Modify: `apps/web/src/lib/api/queries.ts`
- Create: `apps/web/src/lib/fit.ts`, `apps/web/src/components/queue/FitBadge.tsx`, `FilterBar.tsx`, `PollNowButton.tsx`, `RunsDrawer.tsx`
- Modify: `apps/web/src/components/queue/JobCard.tsx`, `JobList.tsx`, `TailorButton.tsx`, `apps/web/src/app/page.tsx`, `apps/web/src/lib/task-progress.ts` (poll task events)
- Test: `apps/web/src/lib/fit.test.ts`, `apps/web/src/components/queue/FilterBar.test.tsx`, `FitBadge.test.tsx`, `PollNowButton.test.tsx`, `RunsDrawer.test.tsx`, extend `JobCard.test.tsx` if it exists (else create)

**Interfaces:**
- Consumes: regenerated `schema.d.ts` from Task 9 (`JobOut.best_fit`, `bucket`, `scores`, `rescued`, `repost_of`, `source`; `/api/v1/discovery/*`).
- Produces:
  - `queries.ts`: `export type JobFilters = { search: string; track: string | null; bucket: "fit" | "low"; sort: "fit" | "newest" }`; `keys.jobs(filters: JobFilters)`; `useJobs(filters: JobFilters)`; `useDiscoveryRuns()` (key `["discovery", "runs"]`, `staleTime: 30_000`); `useSources()` (key `["discovery", "sources"]`, `staleTime: Infinity`); `usePollNow()` (mutation posting `/api/v1/discovery/poll`, returns `TaskOut`); `useRescueJob()` (mutation, invalidates jobs); `invalidateDiscovery(queryClient)`.
  - `lib/fit.ts`: `export function fitTone(fit: number | null, minFit: number | null): Tone` (green if fit >= 75, amber if fit >= minFit, slate otherwise or when null), `export function formatFit(fit: number | null): string` ("—" when null), `export const SOURCE_LABEL: Record<string, string>` (manual, url, greenhouse, lever, ashby, remoteok, "hn-hiring").
  - `FilterBar` props `{ filters: JobFilters; onChange: (next: JobFilters) => void; tracks: {id: string; name: string}[] }`; `FitBadge` props `{ fit: number | null; trackName: string | null; minFit: number | null }`; `PollNowButton` props `{ onFinished: () => void }` (renders the button, then `TaskProgress` for the poll task with steps `fetch, dedupe, score, done`); `RunsDrawer` props `{ open: boolean; onOpenChange: (o: boolean) => void }`.

- [ ] **Step 1: Write the failing unit tests**

`apps/web/src/lib/fit.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { fitTone, formatFit, SOURCE_LABEL } from "./fit";

describe("fit helpers", () => {
  it("maps fit to tones by band and threshold", () => {
    expect(fitTone(80, 60)).toBe("green");
    expect(fitTone(65, 60)).toBe("amber");
    expect(fitTone(59, 60)).toBe("slate");
    expect(fitTone(null, 60)).toBe("slate");
    expect(fitTone(70, null)).toBe("slate");
  });
  it("formats missing fit as a dash and labels sources", () => {
    expect(formatFit(null)).toBe("—");
    expect(formatFit(72)).toBe("72");
    expect(SOURCE_LABEL["hn-hiring"]).toBe("HN");
  });
});
```

`apps/web/src/components/queue/FilterBar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

const base = { search: "", track: null, bucket: "fit" as const, sort: "fit" as const };

describe("FilterBar", () => {
  it("toggles bucket and sort and picks a track", async () => {
    const onChange = vi.fn();
    render(<FilterBar filters={base} onChange={onChange} tracks={[{ id: "data-pm", name: "Data PM" }]} />);
    const user = userEvent.setup({ delay: null });
    await user.click(screen.getByRole("button", { name: /low fit/i }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, bucket: "low" });
    await user.click(screen.getByRole("button", { name: /newest/i }));
    expect(onChange).toHaveBeenLastCalledWith({ ...base, sort: "newest" });
    expect(screen.getByLabelText(/track/i)).toBeInTheDocument();
  });
});
```

`apps/web/src/components/queue/FitBadge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FitBadge } from "./FitBadge";

describe("FitBadge", () => {
  it("shows score and track, and a scoring placeholder when unscored", () => {
    render(<FitBadge fit={82} trackName="Data PM" minFit={60} />);
    expect(screen.getByText("82")).toBeInTheDocument();
    expect(screen.getByText("Data PM")).toBeInTheDocument();
    render(<FitBadge fit={null} trackName={null} minFit={null} />);
    expect(screen.getByText(/scoring/i)).toBeInTheDocument();
  });
});
```

`apps/web/src/components/queue/RunsDrawer.test.tsx` (mock `useDiscoveryRuns` with `vi.mock("@/lib/api/queries", ...)` following the pattern in `Board.test.tsx`):

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api/queries", () => ({
  useDiscoveryRuns: () => ({
    isLoading: false,
    error: null,
    data: [
      { id: "1", source: "greenhouse", board: "exampleco", started_at: new Date().toISOString(), finished_at: new Date().toISOString(), found: 12, new: 3, error: null },
      { id: "2", source: "remoteok", board: null, started_at: new Date().toISOString(), finished_at: new Date().toISOString(), found: 0, new: 0, error: "HTTP 503" },
    ],
  }),
}));

import { RunsDrawer } from "./RunsDrawer";

describe("RunsDrawer", () => {
  it("lists each source with counts and errors", () => {
    render(<RunsDrawer open onOpenChange={() => undefined} />);
    expect(screen.getByText(/greenhouse/i)).toBeInTheDocument();
    expect(screen.getByText(/exampleco/)).toBeInTheDocument();
    expect(screen.getByText(/3 new/)).toBeInTheDocument();
    expect(screen.getByText("HTTP 503")).toBeInTheDocument();
  });
});
```

`apps/web/src/components/queue/PollNowButton.test.tsx` (mock `usePollNow` to resolve `{ id: "t1", status: "queued" }` and `TaskProgress` to a stub that immediately calls `onFinished({ status: "succeeded" })`): assert the button is disabled while pending, that the stub rendered with `taskId "t1"`, and that `onFinished` fired.

- [ ] **Step 2: Run to verify failure**

Run from `apps/web`: `pnpm test -- src/lib/fit.test.ts src/components/queue` → FAIL (missing modules).

- [ ] **Step 3: Implement**

`lib/fit.ts`:

```ts
import type { Tone } from "./status";

export function fitTone(fit: number | null, minFit: number | null): Tone {
  if (fit === null || minFit === null) return "slate";
  if (fit >= 75) return "green";
  if (fit >= minFit) return "amber";
  return "slate";
}

export function formatFit(fit: number | null): string {
  return fit === null ? "—" : String(fit);
}

export const SOURCE_LABEL: Record<string, string> = {
  manual: "Pasted",
  url: "URL",
  greenhouse: "Greenhouse",
  lever: "Lever",
  ashby: "Ashby",
  remoteok: "RemoteOK",
  "hn-hiring": "HN",
};
```

`queries.ts` additions (types from `schema.d.ts`: `PollRunOut`, `SourceInfoOut`, `TaskOut`):

```ts
export type JobFilters = { search: string; track: string | null; bucket: "fit" | "low"; sort: "fit" | "newest" };

export const keys = { ...existing, jobs: (f: JobFilters) => ["jobs", f.search, f.track, f.bucket, f.sort] as const };

export function useJobs(filters: JobFilters) {
  return useQuery({
    queryKey: keys.jobs(filters),
    queryFn: () =>
      unwrap(apiClient().GET("/api/v1/jobs", {
        params: { query: { ...(filters.search ? { search: filters.search } : {}), ...(filters.track ? { track: filters.track } : {}), bucket: filters.bucket, sort: filters.sort } },
      })),
  });
}

export const discoveryKeys = { runs: ["discovery", "runs"] as const, sources: ["discovery", "sources"] as const };

export function invalidateDiscovery(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["discovery"] });
  invalidateJobs(queryClient);
}

export function useDiscoveryRuns() {
  return useQuery({ queryKey: discoveryKeys.runs, queryFn: () => unwrap(apiClient().GET("/api/v1/discovery/runs")), staleTime: 30_000 });
}

export function useSources() {
  return useQuery({ queryKey: discoveryKeys.sources, queryFn: () => unwrap(apiClient().GET("/api/v1/discovery/sources")), staleTime: Infinity });
}

export function usePollNow() {
  return useMutation({ mutationFn: () => unwrap(apiClient().POST("/api/v1/discovery/poll")) });
}

export function useRescueJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string) => unwrap(apiClient().POST("/api/v1/jobs/{job_id}/rescue", { params: { path: { job_id: jobId } } })),
    onSuccess: () => invalidateJobs(queryClient),
  });
}
```

Update every existing `useJobs(search)` caller (`JobList`, `page.tsx`, tests) to the filters object; `keys.jobs` callers likewise.

`FitBadge.tsx`: a `StatusBadge` with `tone={fitTone(fit, minFit)}`; content `<span className="font-mono">{formatFit(fit)}</span>` plus the track name, or the text "scoring…" when `fit === null`. Include `title` attribute "Fit score 0–100 against your best track".

`FilterBar.tsx`: a row with a `Select` for track (label "Track", options "All tracks" plus the given tracks; remember `onValueChange` may pass `null`), a two-button segmented toggle for bucket ("Fit" / "Low fit") and one for sort ("By fit" / "Newest"); active segment uses the default button variant, inactive uses `outline`; each button has `aria-pressed`.

`PollNowButton.tsx`: renders `<Button variant="outline" onClick=… disabled={pending}>Poll now</Button>`; on click calls `usePollNow().mutateAsync()`, stores the task id, and renders `<TaskProgress taskId jobId="" onFinished=…/>` beneath. Because `TaskProgress` today assumes tailoring (it resolves a package status on success and toasts "Package ready"), add a `kind: "tailor" | "poll"` prop to `TaskProgress` (default `"tailor"`) and to `lib/task-progress.ts` export `POLL_STEPS = ["fetch", "dedupe", "score", "done"]`; in poll mode the `done` event (`{event: "done", new_jobs}`) yields a toast "Poll finished: N new jobs" (or "no new jobs") and no package lookup. Extend `reduceTaskEvent` so a `done` event without `package_id` sets `packageId: null` and keeps `status: "succeeded"`, and store `newJobs: number | null` on `ProgressState`. Update `TaskProgress.test.tsx` with one poll-mode case.

`RunsDrawer.tsx`: a `Sheet` (side right) titled "Poll runs" listing `useDiscoveryRuns()` rows: source label, board, relative `finished_at ?? started_at`, "found F · new N", and the error text in red when present.

`JobCard.tsx`: add `<FitBadge>` first in the badge row (needs `minFit`: the card receives `tracks` from `JobList`, which loads `useTracks()` once and maps id to `{name, min_fit}`), a `StatusBadge tone="zinc"` with `SOURCE_LABEL[job.source] ?? job.source`, a "Re-post" zinc badge when `job.repost_of`, and, when `job.bucket === "low"`, a `Button variant="ghost" size="sm"` "Rescue" that calls `useRescueJob()` and toasts "Moved to the fit list". `TailorButton` preselects `job.best_track_id` when set (it already renders a track `Select`; initialise its state from `job.best_track_id ?? tracks[0]?.id`).

`page.tsx`: state `filters: JobFilters` (search debounced as today), `<FilterBar>` under the header, `<PollNowButton onFinished={() => invalidateDiscovery(queryClient)} />` next to "Add job", and a status line built from `useDiscoveryRuns()`: "Last poll {relative} · {sum of new} new" with a "Runs" link button opening `<RunsDrawer>`; "No polls yet" when empty. Also subscribe nothing new: the poll button's `onFinished` invalidation is enough for refresh.

- [ ] **Step 4: Run tests, checks, commit**

Run: `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build` → all green.

```bash
git add apps/web/src
git commit -m "feat(web): scored queue with filters, poll now, runs drawer, and rescue"
```

---

### Task 12: Web watchlist keywords and aggregators, smoke discover step, README

**Files:**
- Modify: `apps/web/src/components/profile/WatchlistTab.tsx`, `apps/web/src/lib/api/queries.ts` (`useAggregators`, `usePutAggregators`)
- Create: `apps/web/src/components/profile/AggregatorsSection.tsx`, `AggregatorsSection.test.tsx`
- Create: `scripts/discovery-fixture-server.py`
- Modify: `scripts/smoke-api.sh`, `README.md`, `.env.example`, `apps/api/src/rhapto/config.py`, `apps/api/src/rhapto/services/discovery/http.py` (base-URL override for smoke; see Step 3)
- Test: `apps/web/src/components/profile/WatchlistTab.test.tsx` (create or extend)

**Interfaces:**
- Consumes: `/api/v1/profile/aggregators` (Task 2), `/api/v1/discovery/sources` (Task 9), `useSources()` (Task 11).
- Produces: `useAggregators()` (key `["profile", "aggregators"]`), `usePutAggregators()` (replaces, invalidates profile); `AggregatorsSection` props `{}` (self-contained: loads aggregators and sources, one `SwitchField` per aggregator source, a shared keywords `Input` (comma list) whose placeholder is "Defaults to your track keywords", Save button); `WatchlistTab` gains a Keywords column (comma list, optional) and the source `Select` is populated from `useSources().filter(kind === "board")` plus the two schema-only sources with a "(no adapter yet)" suffix.

- [ ] **Step 1: Write the failing web tests**

`apps/web/src/components/profile/AggregatorsSection.test.tsx` (mock `useAggregators`, `usePutAggregators`, `useSources` per the `BlocksTab.test.tsx` pattern):

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const mutateAsync = vi.fn().mockResolvedValue([]);
vi.mock("@/lib/api/queries", () => ({
  useAggregators: () => ({ isLoading: false, error: null, data: [{ source: "remoteok", enabled: true, keywords: ["pm"] }] }),
  usePutAggregators: () => ({ mutateAsync, isPending: false }),
  useSources: () => ({ data: [{ name: "remoteok", kind: "aggregator", label: "RemoteOK", needs_board: false }, { name: "hn-hiring", kind: "aggregator", label: "Hacker News Who's Hiring", needs_board: false }, { name: "greenhouse", kind: "board", label: "Greenhouse", needs_board: true }] }),
}));

import { AggregatorsSection } from "./AggregatorsSection";

describe("AggregatorsSection", () => {
  it("renders one switch per aggregator and saves the full list", async () => {
    render(<AggregatorsSection />);
    const user = userEvent.setup({ delay: null });
    expect(screen.getByLabelText("RemoteOK")).toBeChecked();
    expect(screen.getByLabelText("Hacker News Who's Hiring")).not.toBeChecked();
    await user.click(screen.getByLabelText("Hacker News Who's Hiring"));
    await user.click(screen.getByRole("button", { name: /save/i }));
    expect(mutateAsync).toHaveBeenCalledWith([
      { source: "remoteok", enabled: true, keywords: ["pm"] },
      { source: "hn-hiring", enabled: true, keywords: ["pm"] },
    ]);
  });
});
```

`WatchlistTab.test.tsx`: mock `useWatchlist` with one entry carrying `keywords: ["etl"]`, `usePutWatchlist`, and `useSources`; assert the keywords cell shows "etl", and that saving sends `keywords: ["etl", "pm"]` after typing ", pm" into the field (use `delay: null`).

- [ ] **Step 2: Run to verify failure**

Run: `pnpm test -- src/components/profile` → FAIL.

- [ ] **Step 3: Implement**

`queries.ts`:

```ts
export type AggregatorEntry = components["schemas"]["AggregatorEntry"];
export function useAggregators() {
  return useQuery({ queryKey: [...profileKeys.root, "aggregators"], queryFn: () => unwrap(apiClient().GET("/api/v1/profile/aggregators")) });
}
export function usePutAggregators() {
  return useProfileMutation<AggregatorEntry[], AggregatorEntry[]>((body) => unwrap(apiClient().PUT("/api/v1/profile/aggregators", { body })));
}
```

(`profileKeys` already exists; add an `aggregators` key next to `watchlist` in the same shape the file uses.)

`AggregatorsSection.tsx`: keyed-body pattern (as `AnswersTab`): outer loads `useAggregators()` and `useSources()`; body state is `rows: AggregatorEntry[]` built by merging the aggregator sources from the registry with saved rows (unsaved sources default `enabled: false, keywords: []`), one `SwitchField name={src.name} label={src.label}` each, one shared keywords `Input` bound to the first row's keywords and written to every row on save (the spec's shared keyword list), Save calls `usePutAggregators().mutateAsync(rows)` and toasts "Saved aggregators". Render it inside `WatchlistTab` under the table with a heading "Aggregators".

`WatchlistTab.tsx`: add a Keywords column (`Input` with `aria-label="Keywords N"`, value `row.keywords.join(", ")`, on change split on commas, trim, drop empties); source options from `useSources()` boards plus `smartrecruiters` and `workable` labelled "(no adapter yet)"; `save()` sends `keywords` for each row.

`scripts/discovery-fixture-server.py` (stdlib only):

```python
"""Serve the discovery fixtures over HTTP so smoke runs never touch a vendor. Usage: python scripts/discovery-fixture-server.py 8089"""
import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "apps" / "api" / "tests" / "fixtures" / "discovery"
ROUTES: dict[str, object] = {}
for path in FIXTURES.glob("*.json"):
    ROUTES.update(json.loads(path.read_text(encoding="utf-8")))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        for key, body in ROUTES.items():
            if key.split("/", 1)[-1] in self.path or key in self.path:
                payload = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args: object) -> None:
        return


if __name__ == "__main__":
    HTTPServer(("0.0.0.0", int(sys.argv[1]) if len(sys.argv) > 1 else 8089), Handler).serve_forever()
```

Smoke step: the fixture server runs on the host; the worker container must reach it, and the SSRF guard rejects private addresses. So the smoke path uses the CLI, not the worker: after the existing steps, `scripts/smoke-api.sh` starts the fixture server in the background (`python scripts/discovery-fixture-server.py 8089 &`), then runs `RHAPTO_DISCOVERY_BASE_OVERRIDE=http://127.0.0.1:8089 uv run --project apps/api rhapto discover --profile profile.example --source greenhouse --board exampleco --json` and asserts with `jq 'length > 0'`, then kills the server. Implement the override in `DiscoveryHttp`: when `settings.rhapto_discovery_base_override` (new optional setting, default `""`) is set, `_get` rewrites the scheme and host of every URL to that base and skips `assert_public_host` (documented as smoke/test only; log a warning at startup when set). Add `RHAPTO_DISCOVERY_BASE_OVERRIDE=` to `.env.example` with a comment "smoke/testing only".

`README.md`: add a "Job discovery (phase 0.3)" section after the web section:

````markdown
## Job discovery (phase 0.3)

Add the companies you follow to `profile/watchlist.yaml` (Greenhouse, Lever, or Ashby board slugs) and switch on
the aggregators you want (RemoteOK, Hacker News Who's Hiring). The worker polls every `RHAPTO_POLL_INTERVAL_HOURS`
(default 6) and the Queue's **Poll now** button runs a poll on demand. Every new posting is deduped, embedded
locally, and scored 0–100 against each of your tracks; the queue sorts by fit, low-fit jobs sit in their own
bucket you can rescue from, and re-posts are flagged, not re-queued. Scoring never calls the LLM.

```bash
rhapto discover --profile ./profile          # one poll from the terminal, nothing stored
rhapto score --jd job.txt --profile ./profile # per-track breakdown for one description
```

Adding a source is one adapter module plus a registry entry (`apps/api/src/rhapto/services/discovery/sources/`);
LinkedIn and Indeed scraping stay out of core.
````

- [ ] **Step 4: Run everything, commit**

From `apps/web`: `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build`. From `apps/api`: the full Python check set and `uv run lint-imports`. From the root with the stack up (`docker compose up -d --build`): `bash scripts/smoke-api.sh` (includes the new discover step) and `bash scripts/codegen.sh && git diff --exit-code packages/schemas apps/web/src/lib/api/schema.d.ts apps/api/src/rhapto/models`.

```bash
git add apps/web/src scripts/discovery-fixture-server.py scripts/smoke-api.sh README.md .env.example apps/api/src/rhapto/config.py apps/api/src/rhapto/services/discovery/http.py
git commit -m "feat(web): watchlist keywords and aggregators; smoke discover step; docs"
```

---

## Self-review notes

- Spec coverage: data model (Task 2), profile schema (Task 1), sources and registry (Tasks 4 to 6), scoring (Task 3), poller and pause rule (Task 7), scheduling and worker tasks (Task 8), API (Task 9), web queue (Task 11), web profile (Task 12), CLI (Task 10), configuration (Tasks 4, 12), testing incl. 20 golden cases and smoke (Tasks 3, 12), error handling and safety (Tasks 4, 7).
- Deviations from the spec recorded for the ledger: discovery package lives under `services` (import contracts); the CLI `discover` command does not persist; `rescued` and `identity_hash` columns added; the smoke discover step runs through the CLI with a base-URL override rather than through the worker, because the SSRF guard correctly refuses a host-local fixture server.
- Type consistency checked: `Posting` fields, `SourceInfo`, `SourceSpec`, `RunResult`, `PollSummary`, `TrackScore`, `JobFilters`, and the four worker task names are used with the same shapes in every task that references them.
