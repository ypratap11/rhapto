# Shared Job Pool Implementation Plan (Phase 1)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store each job posting once, shared by every user, with everything derived from it — fit, hiding, search attribution — kept per user.

**Architecture:** `jobs` loses `user_id` and its six per-user columns and gains `owner_user_id` (NULL = pool, set = a private manual paste). A new sparse `user_jobs` table carries per-user state; a row exists only when a user has state for that job. `job_scores` is unchanged — it already keys on `(user_id, job_id, track_id)`. The jobs list becomes `jobs LEFT JOIN user_jobs LEFT JOIN searches`.

**Tech Stack:** Python 3.12, SQLAlchemy 2 async, Alembic, Postgres 16 + pgvector, pytest.

**Spec:** `docs/superpowers/specs/2026-09-24-shared-job-pool-and-accounts-design.md`

## Global Constraints

- Alembic head is `0009`; this plan adds exactly one migration, `0010`.
- Single-user behaviour must not change. The API contract (`JobOut` fields, filters, sorts) is identical before and after.
- `source = 'manual'` rows are private: `owner_user_id` is set and they never appear for another user.
- `unlisted_at` and `miss_count` are global — a dead posting is dead for everyone.
- Scoring still writes `job_scores`; only the denormalised "best" moves.
- Run `uv run pytest tests/unit tests/db tests/api -q`, `uv run ruff check src tests`, `uv run ruff format --check src tests`, `uv run mypy src` before every commit.
- The engine (`src/rhapto/engine/**`) must not import from db/services/api — import-linter enforces this. No task here touches the engine.
- Never invent data in the migration: a column with no per-user equivalent is dropped, not guessed.

---

### Task 1: `UserJob` model and migration 0010

**Files:**
- Modify: `apps/api/src/rhapto/db/models.py` (the `Job` class; add `UserJob`)
- Create: `apps/api/alembic/versions/0010_shared_job_pool.py`
- Test: `apps/api/tests/db/test_migration_0010.py`

**Interfaces:**
- Produces: `UserJob` ORM model with columns `user_id`, `job_id`, `best_fit`, `best_track_id`, `search_id`, `hidden_at`, `rescued`, `first_seen_at`; composite primary key `(user_id, job_id)`. `Job.owner_user_id: uuid.UUID | None`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/db/test_migration_0010.py
from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, UserJob

pytestmark = pytest.mark.asyncio


async def test_user_jobs_holds_per_user_state_and_jobs_does_not(session: AsyncSession) -> None:
    """The split itself: the posting carries no user, the state carries no posting content."""
    job_cols = {c.name for c in Job.__table__.columns}
    assert "user_id" not in job_cols, "the posting is shared; ownership lives in owner_user_id"
    assert "owner_user_id" in job_cols
    for moved in ("best_fit", "best_track_id", "location_tier", "search_id", "hidden_at", "rescued"):
        assert moved not in job_cols, f"{moved} is per-user and belongs on user_jobs"

    state_cols = {c.name for c in UserJob.__table__.columns}
    assert {"user_id", "job_id", "best_fit", "best_track_id", "search_id", "hidden_at", "rescued"} <= state_cols
    assert "jd_text" not in state_cols, "per-user state must never copy posting content"
    assert [c.name for c in UserJob.__table__.primary_key.columns] == ["user_id", "job_id"]


async def test_a_pool_job_is_unique_on_source_and_external_id(
    session: AsyncSession, user_id: uuid.UUID
) -> None:
    """Two users discovering the same Lever posting must collapse to one row."""
    for _ in range(2):
        session.add(
            Job(
                source="lever",
                external_id="abc-123",
                jd_text="x" * 80,
                dedupe_hash="d",
                discovered_at=sa.func.now(),
                owner_user_id=None,
            )
        )
    with pytest.raises(sa.exc.IntegrityError):
        await session.flush()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/db/test_migration_0010.py -v`
Expected: FAIL with `ImportError: cannot import name 'UserJob'`

- [ ] **Step 3: Write the model changes**

In `db/models.py`, change `class Job(UserScopedMixin, TimestampMixin, Base)` to `class Job(TimestampMixin, Base)`, delete the `best_track_id`, `best_fit`, `location_tier`, `search_id`, `hidden_at` and `rescued` columns, and add:

```python
    # NULL means this posting is in the shared pool. Set means it is private to one user: a
    # hand-pasted JD (source="manual") may have come from a recruiter email or an unlisted page,
    # and must never become visible to anyone else.
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
```

Add after `Job`:

```python
class UserJob(UserScopedMixin, TimestampMixin, Base):
    """One user's state for one posting. Sparse: a row exists only once there is state to keep,
    so the common case -- a pool job nobody has touched -- costs nothing."""

    __tablename__ = "user_jobs"
    job_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True
    )
    best_track_id: Mapped[str | None] = mapped_column(String(100))
    best_fit: Mapped[int | None] = mapped_column(Integer)
    search_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("searches.id", ondelete="SET NULL")
    )
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rescued: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (PrimaryKeyConstraint("user_id", "job_id"),)
```

Import `PrimaryKeyConstraint` from `sqlalchemy` at the top of the file if it is not already imported.

- [ ] **Step 4: Write migration 0010**

```python
# apps/api/alembic/versions/0010_shared_job_pool.py
"""shared job pool: jobs lose user_id, per-user state moves to user_jobs

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_jobs",
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("best_track_id", sa.String(100)),
        sa.Column("best_fit", sa.Integer()),
        sa.Column("search_id", sa.Uuid(), sa.ForeignKey("searches.id", ondelete="SET NULL")),
        sa.Column("hidden_at", sa.DateTime(timezone=True)),
        sa.Column("rescued", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "job_id"),
    )
    op.create_index("ix_user_jobs_user_id", "user_jobs", ["user_id"])

    # Carry every existing job's per-user state across before the columns go.
    op.execute(
        """
        INSERT INTO user_jobs (user_id, job_id, best_track_id, best_fit, search_id,
                               hidden_at, rescued, first_seen_at, created_at, updated_at)
        SELECT user_id, id, best_track_id, best_fit, search_id,
               hidden_at, rescued, discovered_at, now(), now()
        FROM jobs
        """
    )

    op.add_column("jobs", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_jobs_owner_user", "jobs", "users", ["owner_user_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("ix_jobs_owner_user_id", "jobs", ["owner_user_id"])
    # A hand-pasted JD stays private to whoever pasted it; everything from a public board pools.
    op.execute("UPDATE jobs SET owner_user_id = user_id WHERE source = 'manual'")

    op.drop_index("uq_jobs_user_source_external", table_name="jobs")
    op.drop_index("ix_jobs_user_id", table_name="jobs")
    for column in ("user_id", "best_track_id", "best_fit", "location_tier", "search_id",
                   "hidden_at", "rescued"):
        op.drop_column("jobs", column)

    # Pool rows dedupe globally; an owned row dedupes within its owner.
    op.create_index(
        "uq_jobs_pool_source_external", "jobs", ["source", "external_id"], unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL AND owner_user_id IS NULL"),
    )
    op.create_index(
        "uq_jobs_owned_source_external", "jobs", ["owner_user_id", "source", "external_id"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL AND owner_user_id IS NOT NULL"),
    )


def downgrade() -> None:
    raise NotImplementedError("0010 is one-way: merging a shared pool back per user cannot be inferred")
```

- [ ] **Step 5: Run the migration and the test**

Run: `cd apps/api && uv run alembic upgrade head && uv run pytest tests/db/test_migration_0010.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/db/models.py apps/api/alembic/versions/0010_shared_job_pool.py apps/api/tests/db/test_migration_0010.py
git commit -m "feat(db): split jobs into a shared pool and per-user state"
```

---

### Task 2: `user_jobs` repository

**Files:**
- Create: `apps/api/src/rhapto/db/repositories/user_jobs.py`
- Test: `apps/api/tests/db/test_user_jobs_repo.py`

**Interfaces:**
- Consumes: `UserJob` from Task 1.
- Produces:
  - `async def get_state(session, user_id: uuid.UUID, job_id: uuid.UUID) -> UserJob | None`
  - `async def upsert_state(session, user_id: uuid.UUID, job_id: uuid.UUID, **fields) -> UserJob` — creates the row if absent, sets only the keyword fields given.
  - `async def set_best(session, user_id: uuid.UUID, job_id: uuid.UUID, track_id: str | None, fit: int | None) -> None`

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/db/test_user_jobs_repo.py
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.repositories import user_jobs as repo

pytestmark = pytest.mark.asyncio


async def test_upsert_creates_then_updates_without_clobbering_other_fields(
    session: AsyncSession, user_id: uuid.UUID, pool_job_id: uuid.UUID
) -> None:
    """Sparse state means upsert, not insert: the row may or may not exist yet, and a later write
    of one field must not erase a field written earlier."""
    await repo.upsert_state(session, user_id, pool_job_id, hidden_at=None, rescued=True)
    await repo.set_best(session, user_id, pool_job_id, "ai-builder", 72)
    row = await repo.get_state(session, user_id, pool_job_id)
    assert row is not None
    assert row.rescued is True, "set_best must not reset an unrelated field"
    assert (row.best_track_id, row.best_fit) == ("ai-builder", 72)


async def test_state_is_per_user(
    session: AsyncSession, user_id: uuid.UUID, other_user_id: uuid.UUID, pool_job_id: uuid.UUID
) -> None:
    await repo.set_best(session, user_id, pool_job_id, "ai-builder", 72)
    assert await repo.get_state(session, other_user_id, pool_job_id) is None
```

Add `pool_job_id` and `other_user_id` fixtures to `apps/api/tests/db/conftest.py`: `pool_job_id` inserts a `Job` with `owner_user_id=None`, `source="lever"`, `external_id="t2"`, `jd_text="x"*80`, `dedupe_hash="d2"`, `discovered_at=now`; `other_user_id` inserts a second `users` row with email `other@example.com`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/db/test_user_jobs_repo.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.db.repositories.user_jobs`

- [ ] **Step 3: Write the repository**

```python
# apps/api/src/rhapto/db/repositories/user_jobs.py
"""One user's state for one posting.

Sparse by design: no row until there is something to remember, so the common case -- a pool job
nobody has hidden, scored or found through a saved search -- costs nothing. Every write is an
upsert for that reason; a caller can never assume the row is already there.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import UserJob


async def get_state(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID
) -> UserJob | None:
    return await session.scalar(
        select(UserJob).where(UserJob.user_id == user_id, UserJob.job_id == job_id)
    )


async def upsert_state(
    session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, **fields: Any
) -> UserJob:
    """Set only the fields named. Anything not passed is left exactly as it was -- scoring must
    not erase a user's "not interested", and hiding must not erase their score."""
    row = await get_state(session, user_id, job_id)
    if row is None:
        row = UserJob(user_id=user_id, job_id=job_id)
        session.add(row)
    for key, value in fields.items():
        setattr(row, key, value)
    await session.flush()
    return row


async def set_best(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    track_id: str | None,
    fit: int | None,
) -> None:
    await upsert_state(session, user_id, job_id, best_track_id=track_id, best_fit=fit)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd apps/api && uv run pytest tests/db/test_user_jobs_repo.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/db/repositories/user_jobs.py apps/api/tests/db/
git commit -m "feat(db): sparse per-user job state repository"
```

---

### Task 3: Scoring writes per-user best

**Files:**
- Modify: `apps/api/src/rhapto/services/scoring.py` (`_score_chunk`, around lines 62-87)
- Test: `apps/api/tests/unit/test_scoring_writes_user_state.py`

**Interfaces:**
- Consumes: `set_best` from Task 2.
- Produces: no new names; `_score_chunk` stops writing `job.best_track_id` / `job.best_fit`.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/unit/test_scoring_writes_user_state.py
"""The scorer's output is per-user, so it must land on user_jobs and never on the shared posting.

Writing it back onto the job row is how one user's fit would become every user's fit -- silently,
and only visible once a second account existed.
"""
from __future__ import annotations

from rhapto.db.models import Job, UserJob


def test_the_job_row_has_nowhere_to_write_a_per_user_score() -> None:
    assert not hasattr(Job, "best_fit")
    assert not hasattr(Job, "best_track_id")
    assert hasattr(UserJob, "best_fit")
    assert hasattr(UserJob, "best_track_id")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_scoring_writes_user_state.py -v`
Expected: PASS already after Task 1 — the guard exists to stop a later task putting the columns back. If it fails, Task 1 is incomplete.

- [ ] **Step 3: Update `_score_chunk`**

Replace the two assignment lines and the `continue` branch in `_score_chunk`:

```python
    for job, tier in chunk:
        if job.jd_embedding is None or not tracks:
            await user_jobs_repo.set_best(session, user_id, job.id, None, None)
            continue
        scores = score_job(
            job.title, job.jd_text, list(job.jd_embedding), tracks, track_vectors, tier
        )
        best = best_track(scores, tracks)
        await user_jobs_repo.set_best(
            session,
            user_id,
            job.id,
            best.track_id if best else None,
            best.fit_score if best else None,
        )
        await disc_repo.upsert_scores(
            session, user_id, job, [(s.track_id, s.fit_score, rationale(s)) for s in scores]
        )
```

Add `from rhapto.db.repositories import user_jobs as user_jobs_repo` to the imports.

- [ ] **Step 4: Run the scoring tests**

Run: `cd apps/api && uv run pytest tests/unit -k scoring -v && uv run pytest tests/db -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/services/scoring.py apps/api/tests/unit/test_scoring_writes_user_state.py
git commit -m "feat(scoring): write the best track and fit to per-user state"
```

---

### Task 4: `list_jobs` reads from the join

**Files:**
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py` (`list_jobs`, from line 63)
- Test: `apps/api/tests/db/test_jobs_pool_visibility.py`

**Interfaces:**
- Consumes: `UserJob` (Task 1).
- Produces: `list_jobs` returns `list[tuple[Job, str | None, UserJob | None]]` — the posting, the saved-search name, and this user's state (`None` when they have none).

**This is the largest task.** Every filter that referenced a moved column now references `UserJob`, and the visibility rule is new.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/db/test_jobs_pool_visibility.py
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.repositories import jobs as repo

pytestmark = pytest.mark.asyncio


async def test_pool_jobs_are_visible_to_everyone_and_manual_ones_are_not(
    session: AsyncSession, user_id: uuid.UUID, other_user_id: uuid.UUID
) -> None:
    """The privacy boundary. A pasted JD may have come from a recruiter email; it must not become
    visible to a stranger just because they share the instance."""
    pool = await repo.create_discovered_job(
        session, user_id, source="lever", external_id="p1", company="Acme", title="TPM",
        location=None, url=None, jd_text="x" * 80, posted_at=None, identity_hash="h1",
        repost_of=None, search_id=None,
    )
    private = await repo.create_manual_job(
        session, user_id, jd_text="y" * 80, company="Secret", title="Private role",
    )
    await session.commit()

    mine = {j.id for j, _n, _s in await repo.list_jobs(session, user_id, posted_within="any")}
    theirs = {j.id for j, _n, _s in await repo.list_jobs(session, other_user_id, posted_within="any")}
    assert {pool.id, private.id} <= mine
    assert pool.id in theirs
    assert private.id not in theirs, "a manual paste is private to whoever pasted it"


async def test_hidden_is_per_user(
    session: AsyncSession, user_id: uuid.UUID, other_user_id: uuid.UUID
) -> None:
    from datetime import UTC, datetime

    from rhapto.db.repositories import user_jobs as state_repo

    job = await repo.create_discovered_job(
        session, user_id, source="lever", external_id="p2", company="Acme", title="TPM",
        location=None, url=None, jd_text="x" * 80, posted_at=None, identity_hash="h2",
        repost_of=None, search_id=None,
    )
    await state_repo.upsert_state(session, user_id, job.id, hidden_at=datetime.now(UTC))
    await session.commit()

    assert job.id not in {j.id for j, _n, _s in await repo.list_jobs(session, user_id, posted_within="any")}
    assert job.id in {j.id for j, _n, _s in await repo.list_jobs(session, other_user_id, posted_within="any")}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/db/test_jobs_pool_visibility.py -v`
Expected: FAIL — `list_jobs` still returns 2-tuples and has no visibility rule.

- [ ] **Step 3: Rewrite the query head**

Replace the `tracks` subquery and `select(...)` at the top of `list_jobs` with:

```python
    tracks = select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()
    state = (
        select(UserJob)
        .where(UserJob.user_id == user_id)
        .subquery()
    )
    query = (
        select(Job, SearchRow.name, UserJob)
        .outerjoin(UserJob, (UserJob.job_id == Job.id) & (UserJob.user_id == user_id))
        .outerjoin(tracks, tracks.c.track_id == UserJob.best_track_id)
        .outerjoin(SearchRow, SearchRow.id == UserJob.search_id)
        # The pool is everyone's; an owned row is only its owner's.
        .where(or_(Job.owner_user_id.is_(None), Job.owner_user_id == user_id))
    )
```

Then, throughout the body, replace `Job.best_fit` with `UserJob.best_fit`, `Job.best_track_id` with `UserJob.best_track_id`, `Job.hidden_at` with `UserJob.hidden_at`, `Job.rescued` with `UserJob.rescued` and `Job.search_id` with `UserJob.search_id`. The `hidden` filter becomes `UserJob.hidden_at.is_not(None)` / `UserJob.hidden_at.is_(None)` — and because the join is outer, "not hidden" must also accept a missing row: `or_(UserJob.hidden_at.is_(None), UserJob.user_id.is_(None))`.

Change the return to `return [(job, name, st) for job, name, st in (await session.execute(query)).all()]`.

Add `UserJob` and `or_` to the imports if absent.

- [ ] **Step 4: Add `create_manual_job`**

```python
async def create_manual_job(
    session: AsyncSession, user_id: uuid.UUID, *, jd_text: str, company: str | None,
    title: str | None,
) -> Job:
    """A hand-pasted JD. `owner_user_id` is what keeps it out of everyone else's pool."""
    job = Job(
        source="manual",
        owner_user_id=user_id,
        company=_clamp(company, 200),
        title=_clamp(title, 300),
        jd_text=jd_text,
        dedupe_hash=hashlib.sha256(jd_text.encode()).hexdigest(),
        discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job
```

- [ ] **Step 5: Run the tests**

Run: `cd apps/api && uv run pytest tests/db -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/db/repositories/jobs.py apps/api/tests/db/test_jobs_pool_visibility.py
git commit -m "feat(jobs): read per-user state from the join, keep manual pastes private"
```

---

### Task 5: Update every reader of `best_fit`

**Files:**
- Modify: `apps/api/src/rhapto/api/routers/jobs.py:97-98`
- Modify: `apps/api/src/rhapto/api/routers/packages.py:142-143`
- Modify: `apps/api/src/rhapto/db/repositories/dashboard.py`
- Modify: `apps/api/src/rhapto/services/discovery/live.py`
- Test: existing `apps/api/tests/api/test_jobs_api.py`, `test_jobs_filters_api.py`, `test_dashboard_api.py`

**Interfaces:**
- Consumes: the 3-tuple from Task 4.

- [ ] **Step 1: Run the suite to find every break**

Run: `cd apps/api && uv run pytest tests/api -q`
Expected: FAIL — unpacking errors where callers still expect `(job, name)`.

- [ ] **Step 2: Update each caller**

In `api/routers/jobs.py`, the `JobOut` builder takes the state and reads `best_fit`/`best_track_id` from it, falling back to `None`:

```python
def job_out(job: Job, search_name: str | None, state: UserJob | None, min_fit: int | None) -> JobOut:
    best_fit = state.best_fit if state else None
    best_track_id = state.best_track_id if state else None
```

Apply the same substitution in `packages.py`, `dashboard.py` and `discovery/live.py`: each reads the per-user row rather than the job row. `JobOut`'s public shape does not change.

- [ ] **Step 3: Run the suite**

Run: `cd apps/api && uv run pytest tests/api tests/db tests/unit -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/rhapto
git commit -m "refactor(api): read best fit from per-user state"
```

---

### Task 6: Pool-aware ingest

**Files:**
- Modify: `apps/api/src/rhapto/services/discovery/poller.py` (`_ingest`)
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py` (`find_by_external_id`, `reconcile_listing`)
- Test: `apps/api/tests/unit/test_poller_pool.py`

**Interfaces:**
- Consumes: Tasks 1-4.

- [ ] **Step 1: Write the failing test**

```python
# apps/api/tests/unit/test_poller_pool.py
"""A posting two users both follow is fetched once and stored once.

Before the pool this produced one row per user, so the JD text, the embedding and the cached LLM
extract were all duplicated -- and the extract is a paid call.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.repositories import jobs as repo

pytestmark = pytest.mark.asyncio


async def test_the_same_posting_ingests_once_for_two_users(
    session: AsyncSession, user_id: uuid.UUID, other_user_id: uuid.UUID
) -> None:
    first = await repo.upsert_pool_job(
        session, source="lever", external_id="shared-1", company="Acme", title="TPM",
        location=None, url=None, jd_text="x" * 80, posted_at=None, identity_hash="hs",
    )
    second = await repo.upsert_pool_job(
        session, source="lever", external_id="shared-1", company="Acme", title="TPM",
        location=None, url=None, jd_text="x" * 80, posted_at=None, identity_hash="hs",
    )
    assert first.id == second.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd apps/api && uv run pytest tests/unit/test_poller_pool.py -v`
Expected: FAIL — `upsert_pool_job` does not exist.

- [ ] **Step 3: Add `upsert_pool_job` and use it in the poller**

```python
async def upsert_pool_job(
    session: AsyncSession, *, source: str, external_id: str | None, company: str | None,
    title: str | None, location: str | None, url: str | None, jd_text: str,
    posted_at: datetime | None, identity_hash: str | None,
) -> Job:
    """Fetch-or-create the shared row for one posting. Keyed on (source, external_id) because that
    is what the board itself considers one posting; `owner_user_id` stays NULL."""
    existing = None
    if external_id is not None:
        existing = await session.scalar(
            select(Job).where(
                Job.source == source,
                Job.external_id == external_id,
                Job.owner_user_id.is_(None),
            )
        )
    if existing is not None:
        existing.miss_count = 0
        existing.unlisted_at = None
        return existing
    job = Job(
        source=source,
        external_id=_clamp(external_id, 200),
        company=_clamp(company, 200),
        title=_clamp(title, 300),
        location=_clamp(location, 200),
        url=url,
        jd_text=jd_text,
        posted_at=posted_at,
        identity_hash=identity_hash,
        dedupe_hash=hashlib.sha256(f"{source}:{external_id}:{jd_text}".encode()).hexdigest(),
        discovered_at=datetime.now(UTC),
        owner_user_id=None,
    )
    session.add(job)
    await session.flush()
    return job
```

In `poller._ingest`, call `upsert_pool_job` for the posting and then `user_jobs.upsert_state(session, user_id, job.id, search_id=..., first_seen_at=now)` for the user whose search or watchlist found it.

- [ ] **Step 4: Run the tests**

Run: `cd apps/api && uv run pytest tests/unit tests/db tests/api -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto apps/api/tests
git commit -m "feat(discovery): ingest each posting once into the shared pool"
```

---

## Self-Review

**Spec coverage.** §4.1 column split → Task 1. §4.2 tables → Tasks 1-2. §4.3 privacy boundary → Tasks 1, 4 (`create_manual_job`, visibility test). §4.4 `best_fit` rewrite → Tasks 3-5. §4.5 polling and scoring → Tasks 3, 6. §6 migration → Task 1. Not covered here, deliberately: §5 accounts and §8 abuse limits are Phases 2 and 3.

**Gap found and accepted:** the spec's §4.5 "new account triggers a backfill over the existing pool" has no task. It belongs with Phase 2, because until accounts exist there is no second user to backfill for. Noted in the Phase 2 plan's scope.

**Type consistency.** `list_jobs` returns `(Job, str | None, UserJob | None)` in Task 4 and every caller in Task 5 unpacks three values. `set_best(session, user_id, job_id, track_id, fit)` is defined in Task 2 and called with that signature in Task 3. `upsert_state(session, user_id, job_id, **fields)` is defined in Task 2 and called in Tasks 4 and 6.

**Risk the executor must respect:** Task 1's migration is one-way and drops columns holding live data. Take a `pg_dump` of the server before it runs there. Locally, the test database is disposable.
