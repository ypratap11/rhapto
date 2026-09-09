# Rhapto Stage 2: Backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the stage 1 engine behind a FastAPI backend with Postgres (pgvector), an arq worker on Redis, Server-Sent Events for tailoring progress, profile import/export, packages, and an application tracker, all runnable with Docker Compose.

**Architecture:** Same `rhapto` package, new layers: `db` (SQLAlchemy 2 async models, Alembic), `services` (profile sync between YAML, Postgres, and the engine's `Profile`; package file storage; job-text fetching; event bus and enqueuer abstractions with Redis/arq and in-memory/inline implementations), `worker` (arq tasks calling `engine.pipeline.tailor`), and `api` (FastAPI app factory, bearer-token auth, RFC 7807 errors, routers). Tests run against a real Postgres from `docker compose up -d db redis`, with worker tasks executed inline and providers faked, so no network or LLM is touched.

**Tech Stack:** FastAPI, uvicorn, SQLAlchemy 2 (asyncio) with asyncpg, Alembic, pgvector, arq, redis, sse-starlette, httpx, trafilatura, python-multipart, Docker Compose (pgvector/pgvector:pg16, redis:7).

**Spec:** `docs/superpowers/specs/2026-09-09-rhapto-architecture-design.md` sections 6 (database), 7 (API), 8 (worker), 10 (packaging), 11 (testing), and stage 2 of section 12. Stage 1 is on branch `stage-1-engine-cli` and is the base for this work.

## Global Constraints

- Everything from the stage 1 plan still applies: Python `>=3.12`, `uv`, ruff `E,F,I,UP,B`, `mypy --strict`, no personal data in tracked files, generated models never hand-edited, engine purity (import-linter contract).
- Layering (enforced by import-linter contracts in Task 12): `rhapto.engine` imports nothing from `profile`, `db`, `services`, `worker`, `api`, `cli`, `config`. `rhapto.db` imports only `rhapto.models`. `rhapto.profile` imports only `rhapto.models` and `rhapto.engine`. `rhapto.services` may import `db`, `engine`, `profile`, `models`, `config`. `rhapto.worker` and `rhapto.api` may import `services`, `db`, `engine`, `models`, `config`. `rhapto.cli` may import anything.
- Every table has `id` (UUID), `user_id` (FK to users, indexed, cascade delete), `created_at`, `updated_at`. Profile entities keep their profile-level string ids (`block_id`, `base_id`, `track_id`, `rule`) unique per user; cross references inside the profile use those string ids, matching the YAML files exactly.
- API prefix `/api/v1`; OpenAPI at `/api/v1/openapi.json`; auth via `Authorization: Bearer <RHAPTO_API_TOKEN>` on every route except `/api/v1/health`, `/api/v1/openapi.json`, and `/api/v1/docs` (no user data; the frontend client is generated from the schema); a single user identified by `RHAPTO_USER_EMAIL` is created at startup. Errors are RFC 7807 `application/problem+json`.
- No code path submits an application anywhere. The only outbound network calls are the LLM provider and the optional job-URL fetch requested by the user.
- Editing a package through `PATCH /packages/{id}` re-runs the guardrails with the package's stored selection and re-renders; it creates a new version and never bypasses validation.
- Worker tasks are plain async functions `(ctx, **kwargs)`; the API enqueues through an `Enqueuer` protocol; tests use `InlineEnqueuer` with fake providers. The API commits before enqueueing so an inline task sees the rows.
- Progress events flow through an `EventBus` protocol (Redis pub/sub in production, in-memory in tests) on channel `task:<task_id>`; the SSE endpoint subscribes first, then replays current task state, then streams.
- Package files live under `RHAPTO_PACKAGES_DIR/<package_id>/` (`resume.docx`, `resume.pdf`); the DB stores paths.
- Test database: `RHAPTO_TEST_DATABASE_URL` (default `postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test`); API tests skip with a clear message if Postgres is unreachable. Bring it up with `docker compose up -d db redis` from the repo root.
- Commit messages end with the two attribution lines given in the session.

## File Structure

```
rhapto-starter/
├── docker-compose.yml                       db, redis, api, worker
├── .env.example                             extended
└── apps/api/
    ├── pyproject.toml                       new deps
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py                           async env, URL from DATABASE_URL or settings
    │   ├── script.py.mako
    │   └── versions/0001_initial.py
    ├── Dockerfile                           api and worker targets added
    ├── .importlinter                        layering contracts added
    ├── src/rhapto/
    │   ├── config.py                        db/redis/token/user/paths settings
    │   ├── db/
    │   │   ├── __init__.py
    │   │   ├── base.py                      Base, mixins, uuid helper
    │   │   ├── models.py                    all tables
    │   │   ├── session.py                   engine and session factory
    │   │   └── repositories/
    │   │       ├── __init__.py
    │   │       ├── users.py                 get_or_create_user
    │   │       ├── profile.py               CRUD for the six profile tables
    │   │       ├── jobs.py
    │   │       ├── packages.py
    │   │       ├── applications.py
    │   │       └── tasks.py
    │   ├── services/
    │   │   ├── __init__.py
    │   │   ├── profile_sync.py              DB <-> engine Profile, YAML import/export
    │   │   ├── storage.py                   PackageStorage
    │   │   ├── jobtext.py                   fetch_job_text, dedupe_hash
    │   │   ├── eventbus.py                  EventBus, InMemoryEventBus, RedisEventBus
    │   │   └── enqueue.py                   Enqueuer, InlineEnqueuer, ArqEnqueuer
    │   ├── worker/
    │   │   ├── __init__.py
    │   │   ├── tasks.py                     tailor_job, embed_blocks, TASKS
    │   │   └── main.py                      WorkerSettings (arq)
    │   ├── api/
    │   │   ├── __init__.py
    │   │   ├── app.py                       create_app, module-level app
    │   │   ├── deps.py                      state, session, auth, enqueuer, bus, storage
    │   │   ├── errors.py                    RFC 7807 handlers
    │   │   ├── schemas.py                   request/response models
    │   │   └── routers/
    │   │       ├── __init__.py
    │   │       ├── meta.py                  health, me
    │   │       ├── profile.py
    │   │       ├── jobs.py
    │   │       ├── tailor.py                tailor, tasks, SSE
    │   │       ├── packages.py
    │   │       └── applications.py
    │   └── cli/main.py                      db upgrade, profile import/export
    └── tests/
        ├── api/
        │   ├── conftest.py                  Postgres fixtures, app client, fakes
        │   ├── test_meta.py
        │   ├── test_profile_api.py
        │   ├── test_jobs_api.py
        │   ├── test_tailor_api.py
        │   ├── test_packages_api.py
        │   └── test_applications_api.py
        ├── db/
        │   ├── test_models.py
        │   └── test_profile_sync.py
        └── unit/
            ├── test_eventbus.py
            ├── test_enqueue.py
            ├── test_storage.py
            ├── test_jobtext.py
            └── test_worker_tasks.py
```

---
### Task 1: Backend dependencies, settings, database models, Alembic, Compose services, test fixtures

**Files:**
- Modify: `apps/api/pyproject.toml`, `apps/api/src/rhapto/config.py`, `.env.example`
- Create: `docker-compose.yml` (repo root, db and redis only for now)
- Create: `apps/api/src/rhapto/db/__init__.py`, `base.py`, `models.py`, `session.py`, `repositories/__init__.py`, `repositories/users.py`
- Create: `apps/api/alembic.ini`, `apps/api/alembic/env.py`, `apps/api/alembic/script.py.mako`, `apps/api/alembic/versions/0001_initial.py`
- Create: `apps/api/tests/conftest.py`, `apps/api/tests/db/test_models.py`

**Interfaces:**
- Produces (`rhapto.config.Settings` new fields): `database_url: str`, `rhapto_test_database_url: str`, `redis_url: str`, `rhapto_api_token: str`, `rhapto_user_email: str`, `rhapto_packages_dir: Path`, `rhapto_web_origin: str`.
- Produces (`rhapto.db.base`): `Base`, `TimestampMixin`, `UserScopedMixin`, `new_uuid()`.
- Produces (`rhapto.db.models`): `User`, `ResumeBlock`, `ResumeBase`, `Track`, `Guardrail`, `Answers`, `WatchlistEntry`, `Job`, `Package`, `Application`, `Task`, plus `APPLICATION_STATUSES`, `TASK_STATUSES`, `PACKAGE_STATUSES`, `EMBEDDING_DIMENSIONS = 384`.
- Produces (`rhapto.db.session`): `make_engine(url) -> AsyncEngine`, `make_session_factory(engine) -> async_sessionmaker[AsyncSession]`.
- Produces (`rhapto.db.repositories.users`): `async get_or_create_user(session, email) -> User`.
- Produces (tests): fixtures `test_db_url` (session, skips if unreachable), `migrated_db` (session, runs Alembic to head), `engine`, `session_factory` (function-scoped, truncates all tables after each test), `session`, `user` (a `User` row for `test@example.com`). These are appended to the existing root `tests/conftest.py` (which already defines `repo_root` and `demo_profile_dir`) so both `tests/db` and `tests/api` see them.

- [ ] **Step 1: Dependencies and settings**

Add to `[project] dependencies` in `apps/api/pyproject.toml`:

```toml
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.29",
    "alembic>=1.13",
    "pgvector>=0.3",
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "arq>=0.26",
    "redis>=5.0",
    "sse-starlette>=2.1",
    "httpx>=0.27",
    "trafilatura>=1.12",
    "python-multipart>=0.0.9",
```

Add to the `dev` group: `"pytest-timeout>=2.3"`. Add mypy overrides for untyped packages:

```toml
[[tool.mypy.overrides]]
module = ["fastembed.*", "docx.*", "rapidfuzz.*", "pgvector.*", "trafilatura.*", "arq.*", "sse_starlette.*"]
ignore_missing_imports = true
```

(Replace the existing override block that lists the first three.) Add `timeout = 60` under `[tool.pytest.ini_options]`.

Add to `Settings` in `apps/api/src/rhapto/config.py` (keep the existing fields and `model_config` untouched):

```python
    database_url: str = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto"
    rhapto_test_database_url: str = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
    redis_url: str = "redis://localhost:6379/0"
    rhapto_api_token: str = ""
    rhapto_user_email: str = "user@example.com"
    rhapto_packages_dir: Path = Path("data/packages")
    rhapto_web_origin: str = "http://localhost:3000"
```

with `from pathlib import Path` at the top. Append to `.env.example`:

```
# backend (stage 2)
DATABASE_URL=postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto
REDIS_URL=redis://localhost:6379/0
RHAPTO_API_TOKEN=change-me
RHAPTO_USER_EMAIL=user@example.com
RHAPTO_PACKAGES_DIR=data/packages
RHAPTO_WEB_ORIGIN=http://localhost:3000
```

Add `data/` to `.gitignore`.

- [ ] **Step 2: Compose services for db and redis**

`docker-compose.yml` at the repo root:

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_USER: rhapto
      POSTGRES_PASSWORD: rhapto
      POSTGRES_DB: rhapto
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U rhapto -d rhapto"]
      interval: 5s
      timeout: 3s
      retries: 20

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 20

volumes:
  pgdata:
```

Run `docker compose up -d db redis` from the repo root and wait until `docker compose ps` shows both healthy.

- [ ] **Step 3: Database base, models, session**

`apps/api/src/rhapto/db/__init__.py`:

```python
"""SQLAlchemy models and repositories. Imports only rhapto.models."""
```

`apps/api/src/rhapto/db/base.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class UserScopedMixin:
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
```

`apps/api/src/rhapto/db/models.py`:

```python
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from rhapto.db.base import Base, TimestampMixin, UserScopedMixin, new_uuid

EMBEDDING_DIMENSIONS = 384
APPLICATION_STATUSES = ("discovered", "queued", "applied", "screen", "interview", "offer", "closed")
TASK_STATUSES = ("queued", "running", "succeeded", "failed")
PACKAGE_STATUSES = ("draft", "blocked")


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class ResumeBlock(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "resume_blocks"
    __table_args__ = (UniqueConstraint("user_id", "block_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    block_id: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    org: Mapped[str | None] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    period: Mapped[str | None] = mapped_column(String(50))
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    metric: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    attribution: Mapped[str | None] = mapped_column(String(200))
    concurrent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    exclude_when: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class ResumeBase(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "resume_bases"
    __table_args__ = (UniqueConstraint("user_id", "base_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    base_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    block_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    section_order: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    style_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Track(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "tracks"
    __table_args__ = (UniqueConstraint("user_id", "track_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    resume_base: Mapped[str] = mapped_column(String(100), nullable=False)
    min_fit: Mapped[int] = mapped_column(Integer, default=50, nullable=False)


class Guardrail(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "guardrails"
    __table_args__ = (UniqueConstraint("user_id", "rule"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    rule: Mapped[str] = mapped_column(String(100), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)


class Answers(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("user_id"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    answers_json: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)


class WatchlistEntry(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "watchlist"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    company: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    board: Mapped[str] = mapped_column(String(200), nullable=False)


class Job(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "jobs"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), default="manual", nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    title: Mapped[str | None] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(Text)
    jd_text: Mapped[str] = mapped_column(Text, nullable=False)
    jd_embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    extracted_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    dedupe_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Package(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "packages"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    track_id: Mapped[str] = mapped_column(String(100), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    resume_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    cover_note: Mapped[str] = mapped_column(Text, nullable=False)
    change_log: Mapped[str] = mapped_column(Text, nullable=False)
    answers_json: Mapped[dict[str, str]] = mapped_column(JSONB, default=dict, nullable=False)
    guardrail_report_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    jd_extract_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    selection_block_ids: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, nullable=False)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    docx_path: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    parent_package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"))


class Application(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "applications"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False)
    package_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("packages.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status_history_json: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list, nullable=False)


class Task(UserScopedMixin, TimestampMixin, Base):
    __tablename__ = "tasks"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued", nullable=False)
    progress_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    result_ref: Mapped[str | None] = mapped_column(String(100))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`apps/api/src/rhapto/db/session.py`:

```python
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


def make_engine(url: str) -> AsyncEngine:
    return create_async_engine(url, pool_pre_ping=True)


def make_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
```

`apps/api/src/rhapto/db/repositories/__init__.py`:

```python
"""Thin query helpers per table. Repositories take an AsyncSession and never commit."""
```

`apps/api/src/rhapto/db/repositories/users.py`:

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User


async def get_or_create_user(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        session.add(user)
        await session.flush()
    return user
```

- [ ] **Step 4: Alembic**

`apps/api/alembic.ini`:

```ini
[alembic]
script_location = %(here)s/alembic
prepend_sys_path = %(here)s/src
sqlalchemy.url = postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

`apps/api/alembic/env.py`:

```python
from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy import pool

import rhapto.db.models  # noqa: F401  (registers tables on Base.metadata)
from rhapto.db.base import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

url = os.environ.get("DATABASE_URL")
if url:
    config.set_main_option("sqlalchemy.url", url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}), prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

`apps/api/alembic/script.py.mako`: copy the default template that `uv run alembic init` generates (run `uv run alembic init /tmp/alembic-template` in a scratch location and copy `script.py.mako` from there; do not keep the scratch env.py).

Generate the initial migration against the running compose database:

```bash
cd apps/api && DATABASE_URL=postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto uv run alembic revision --autogenerate -m "initial" --rev-id 0001
```

Then edit `apps/api/alembic/versions/0001_initial.py`: add `import pgvector.sqlalchemy` near the imports if the generated code references `Vector` without importing it, and insert `op.execute("CREATE EXTENSION IF NOT EXISTS vector")` as the first statement of `upgrade()` (and `op.execute("DROP EXTENSION IF EXISTS vector")` as the last statement of `downgrade()`). Confirm every table from `models.py` appears. Apply and verify: `DATABASE_URL=... uv run alembic upgrade head` then `DATABASE_URL=... uv run alembic check` (expect "No new upgrade operations detected"). Exclude `alembic/` from ruff and mypy: add `"alembic"` to `[tool.ruff] extend-exclude` and `exclude = ["alembic"]` under `[tool.mypy]`.

- [ ] **Step 5: Test fixtures and model test**

`apps/api/tests/conftest.py`:

```python
from __future__ import annotations

import os
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rhapto.db.base import Base
from rhapto.db.models import User
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

DEFAULT_TEST_URL = "postgresql+asyncpg://rhapto:rhapto@localhost:5432/rhapto_test"
API_DIR = Path(__file__).resolve().parents[2]


def _dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://")


@pytest.fixture(scope="session")
def test_db_url() -> str:
    url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin = _dsn(url).rsplit("/", 1)[0] + "/postgres"
    dbname = url.rsplit("/", 1)[1]

    async def ensure() -> None:
        conn = await asyncpg.connect(admin)
        try:
            exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", dbname)
            if not exists:
                await conn.execute(f'CREATE DATABASE "{dbname}"')
        finally:
            await conn.close()

    import asyncio

    try:
        asyncio.run(ensure())
    except OSError as exc:
        pytest.skip(f"Postgres not reachable at {admin}: {exc}. Run `docker compose up -d db redis`.")
    return url


@pytest.fixture(scope="session")
def migrated_db(test_db_url: str) -> str:
    cfg = Config(str(API_DIR / "alembic.ini"))
    os.environ["DATABASE_URL"] = test_db_url
    command.upgrade(cfg, "head")
    return test_db_url


@pytest.fixture
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = make_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest.fixture
async def session_factory(engine: AsyncEngine) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    factory = make_session_factory(engine)
    yield factory
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
async def session(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with session_factory() as s:
        yield s


@pytest.fixture
async def user(session: AsyncSession) -> User:
    u = await get_or_create_user(session, "test@example.com")
    await session.commit()
    return u
```

`apps/api/tests/db/test_models.py`:

```python
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, ResumeBlock, User
from rhapto.db.repositories.users import get_or_create_user


async def test_get_or_create_user_is_idempotent(session: AsyncSession) -> None:
    a = await get_or_create_user(session, "x@example.com")
    b = await get_or_create_user(session, "x@example.com")
    assert a.id == b.id


async def test_block_round_trip_with_arrays_and_vector(session: AsyncSession, user: User) -> None:
    block = ResumeBlock(
        user_id=user.id, block_id="acme-migration", type="achievement", content="Owned it.",
        verified=True, tags=["migration", "cost"], exclude_when=["agency"], embedding=[0.1] * 384,
    )
    session.add(block)
    await session.commit()
    loaded = await session.scalar(select(ResumeBlock).where(ResumeBlock.block_id == "acme-migration"))
    assert loaded is not None and loaded.tags == ["migration", "cost"] and loaded.exclude_when == ["agency"]
    assert loaded.verified is True and len(list(loaded.embedding)) == 384
    assert loaded.created_at is not None


async def test_job_defaults(session: AsyncSession, user: User) -> None:
    job = Job(user_id=user.id, jd_text="text", dedupe_hash="abc", discovered_at=datetime.now(UTC))
    session.add(job)
    await session.commit()
    assert job.source == "manual" and job.company is None


async def test_truncate_between_tests(session: AsyncSession) -> None:
    assert (await session.scalar(select(User))) is None
```

- [ ] **Step 6: Run and commit**

From the repo root: `docker compose up -d db redis`. Then from `apps/api`: `uv sync`, `uv run pytest tests/db -v` (expect 4 passed), `uv run pytest -q` (all green), `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run lint-imports`.

```bash
git add docker-compose.yml .env.example .gitignore apps/api
git commit -m "feat(db): SQLAlchemy models, Alembic initial migration, compose db/redis, test fixtures"
```

---
### Task 2: Profile repositories, DB to engine Profile sync, YAML import/export, CLI `db upgrade` and `profile import/export`

**Files:**
- Create: `apps/api/src/rhapto/db/repositories/profile.py`
- Create: `apps/api/src/rhapto/services/__init__.py`, `apps/api/src/rhapto/services/profile_sync.py`
- Modify: `apps/api/src/rhapto/cli/main.py`
- Test: `apps/api/tests/db/test_profile_sync.py`, `apps/api/tests/unit/test_cli.py` (append)

**Interfaces:**
- Consumes: models from Task 1; `rhapto.engine.types.Profile`; `rhapto.profile.loader.load_profile`, `dump_profile`, `default_guardrails`, `synthesize_bases`; generated models (`Block`, `Visibility`, `ResumeBase` as `ResumeBaseModel`, `Track` as `TrackModel`, `GuardrailRule`, `WatchlistEntry` as `WatchlistEntryModel`).
- Produces (`rhapto.db.repositories.profile`): `list_blocks(session, user_id) -> list[ResumeBlock]`, `get_block(session, user_id, block_id) -> ResumeBlock | None`, `upsert_block(session, user_id, data: Block) -> ResumeBlock`, `delete_block(session, user_id, block_id) -> bool`; the same four for bases (`list_bases`, `get_base`, `upsert_base`, `delete_base`, keyed by `base_id`), tracks (`track_id`), guardrails (`rule`), watchlist (`list_watchlist`, `replace_watchlist(session, user_id, entries)`), and `get_answers(session, user_id) -> dict[str, str]`, `set_answers(session, user_id, answers)`; `delete_all_profile_rows(session, user_id)`.
- Produces (`rhapto.services.profile_sync`): `block_row_to_model(row) -> Block`, `base_row_to_model`, `track_row_to_model`, `guardrail_row_to_model`, `watchlist_row_to_model`; `async load_profile_from_db(session, user_id) -> Profile` (raises `ProfileError` when the user has no blocks or no tracks; synthesizes bases when none stored; default guardrails when none stored); `async replace_profile_in_db(session, user_id, profile: Profile) -> None`; `async import_profile_dir(session, user_id, path: Path) -> Profile`; `async export_profile_dir(session, user_id, path: Path) -> Profile`.
- Produces (CLI): `rhapto db upgrade`, `rhapto profile import <dir>`, `rhapto profile export <dir>`; `run_migrations(database_url: str) -> None` and `alembic_config() -> Config` helpers in `cli/main.py`.

- [ ] **Step 1: Write the failing sync tests**

`apps/api/tests/db/test_profile_sync.py`:

```python
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import profile as repo
from rhapto.engine.types import ProfileError
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.profile.loader import load_profile
from rhapto.services.profile_sync import (
    export_profile_dir,
    import_profile_dir,
    load_profile_from_db,
    replace_profile_in_db,
)


async def test_import_then_load_round_trips(session: AsyncSession, user: User, demo_profile_dir: Path) -> None:
    imported = await import_profile_dir(session, user.id, demo_profile_dir)
    await session.commit()
    loaded = await load_profile_from_db(session, user.id)
    assert loaded == imported
    assert {b.id for b in loaded.blocks} == {"acme-data-pm", "acme-migration", "side-llm-tool", "cred-pmp"}
    assert loaded.answers["name"] == "Maya Chen"
    assert [t.id for t in loaded.tracks] == ["data-pm", "ai-pm"]
    assert {b.id for b in loaded.bases} == {"data-pm", "ai-pm"}


async def test_export_writes_yaml_equal_to_db(session: AsyncSession, user: User, demo_profile_dir: Path, tmp_path: Path) -> None:
    await import_profile_dir(session, user.id, demo_profile_dir)
    await session.commit()
    exported = await export_profile_dir(session, user.id, tmp_path)
    assert load_profile(tmp_path) == exported


async def test_replace_is_destructive(session: AsyncSession, user: User, demo_profile_dir: Path) -> None:
    await import_profile_dir(session, user.id, demo_profile_dir)
    await session.commit()
    profile = await load_profile_from_db(session, user.id)
    smaller = profile.model_copy(update={"blocks": profile.blocks[:1], "bases": [], "tracks": profile.tracks[:1]})
    smaller = smaller.model_copy(update={"bases": [profile.bases[0].model_copy(update={"block_ids": [profile.blocks[0].id]})]})
    await replace_profile_in_db(session, user.id, smaller)
    await session.commit()
    assert len(await repo.list_blocks(session, user.id)) == 1


async def test_load_without_blocks_raises(session: AsyncSession, user: User) -> None:
    with pytest.raises(ProfileError, match="no blocks"):
        await load_profile_from_db(session, user.id)


async def test_upsert_block_updates_in_place(session: AsyncSession, user: User) -> None:
    await repo.upsert_block(session, user.id, Block(id="a", type="role", content="one"))
    await repo.upsert_block(session, user.id, Block(id="a", type="role", content="two", visibility=Visibility(exclude_when=["x"])))
    await session.commit()
    rows = await repo.list_blocks(session, user.id)
    assert len(rows) == 1 and rows[0].content == "two" and rows[0].exclude_when == ["x"]
    assert await repo.delete_block(session, user.id, "a") is True
    assert await repo.delete_block(session, user.id, "a") is False


async def test_profile_rows_are_user_scoped(session: AsyncSession, user: User) -> None:
    from rhapto.db.repositories.users import get_or_create_user

    other = await get_or_create_user(session, "other@example.com")
    await repo.upsert_block(session, user.id, Block(id="a", type="role", content="mine"))
    await repo.upsert_block(session, other.id, Block(id="a", type="role", content="theirs"))
    await session.commit()
    assert [b.content for b in await repo.list_blocks(session, user.id)] == ["mine"]
```

Append to `apps/api/tests/unit/test_cli.py`:

```python
def test_db_upgrade_and_profile_import_export_commands_exist() -> None:
    result = runner.invoke(cli.app, ["db", "--help"])
    assert result.exit_code == 0 and "upgrade" in result.output
    result = runner.invoke(cli.app, ["profile", "--help"])
    assert "import" in result.output and "export" in result.output
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/db/test_profile_sync.py tests/unit/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.services` and the CLI help test failing.

- [ ] **Step 3: Implement the profile repository**

`apps/api/src/rhapto/db/repositories/profile.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Answers, Guardrail, ResumeBase, ResumeBlock, Track, WatchlistEntry
from rhapto.models.profile.bases import ResumeBase as ResumeBaseModel
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track as TrackModel
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistEntryModel


async def list_blocks(session: AsyncSession, user_id: uuid.UUID) -> list[ResumeBlock]:
    rows = await session.scalars(select(ResumeBlock).where(ResumeBlock.user_id == user_id).order_by(ResumeBlock.created_at, ResumeBlock.block_id))
    return list(rows)


async def get_block(session: AsyncSession, user_id: uuid.UUID, block_id: str) -> ResumeBlock | None:
    return await session.scalar(select(ResumeBlock).where(ResumeBlock.user_id == user_id, ResumeBlock.block_id == block_id))


async def upsert_block(session: AsyncSession, user_id: uuid.UUID, data: Block) -> ResumeBlock:
    row = await get_block(session, user_id, data.id)
    if row is None:
        row = ResumeBlock(user_id=user_id, block_id=data.id, type=data.type, content=data.content)
        session.add(row)
    row.type = data.type
    row.org = data.org
    row.role = data.role
    row.period = data.period
    row.verified = data.verified
    row.metric = data.metric
    row.content = data.content
    row.tags = list(data.tags)
    row.attribution = data.attribution
    row.concurrent = data.concurrent
    row.exclude_when = list(data.visibility.exclude_when) if data.visibility else []
    await session.flush()
    return row


async def delete_block(session: AsyncSession, user_id: uuid.UUID, block_id: str) -> bool:
    result = await session.execute(delete(ResumeBlock).where(ResumeBlock.user_id == user_id, ResumeBlock.block_id == block_id))
    return bool(result.rowcount)


async def list_bases(session: AsyncSession, user_id: uuid.UUID) -> list[ResumeBase]:
    return list(await session.scalars(select(ResumeBase).where(ResumeBase.user_id == user_id).order_by(ResumeBase.created_at, ResumeBase.base_id)))


async def get_base(session: AsyncSession, user_id: uuid.UUID, base_id: str) -> ResumeBase | None:
    return await session.scalar(select(ResumeBase).where(ResumeBase.user_id == user_id, ResumeBase.base_id == base_id))


async def upsert_base(session: AsyncSession, user_id: uuid.UUID, data: ResumeBaseModel) -> ResumeBase:
    row = await get_base(session, user_id, data.id)
    if row is None:
        row = ResumeBase(user_id=user_id, base_id=data.id, name=data.name)
        session.add(row)
    row.name = data.name
    row.block_ids = list(data.block_ids)
    row.section_order = list(data.section_order)
    row.style_json = dict(data.style)
    await session.flush()
    return row


async def delete_base(session: AsyncSession, user_id: uuid.UUID, base_id: str) -> bool:
    result = await session.execute(delete(ResumeBase).where(ResumeBase.user_id == user_id, ResumeBase.base_id == base_id))
    return bool(result.rowcount)


async def list_tracks(session: AsyncSession, user_id: uuid.UUID) -> list[Track]:
    return list(await session.scalars(select(Track).where(Track.user_id == user_id).order_by(Track.created_at, Track.track_id)))


async def get_track(session: AsyncSession, user_id: uuid.UUID, track_id: str) -> Track | None:
    return await session.scalar(select(Track).where(Track.user_id == user_id, Track.track_id == track_id))


async def upsert_track(session: AsyncSession, user_id: uuid.UUID, data: TrackModel) -> Track:
    row = await get_track(session, user_id, data.id)
    if row is None:
        row = Track(user_id=user_id, track_id=data.id, name=data.name, resume_base=data.resume_base)
        session.add(row)
    row.name = data.name
    row.description = data.description
    row.keywords = list(data.keywords)
    row.resume_base = data.resume_base
    row.min_fit = data.min_fit
    await session.flush()
    return row


async def delete_track(session: AsyncSession, user_id: uuid.UUID, track_id: str) -> bool:
    result = await session.execute(delete(Track).where(Track.user_id == user_id, Track.track_id == track_id))
    return bool(result.rowcount)


async def list_guardrails(session: AsyncSession, user_id: uuid.UUID) -> list[Guardrail]:
    return list(await session.scalars(select(Guardrail).where(Guardrail.user_id == user_id).order_by(Guardrail.created_at, Guardrail.rule)))


async def get_guardrail(session: AsyncSession, user_id: uuid.UUID, rule: str) -> Guardrail | None:
    return await session.scalar(select(Guardrail).where(Guardrail.user_id == user_id, Guardrail.rule == rule))


async def upsert_guardrail(session: AsyncSession, user_id: uuid.UUID, data: GuardrailRule) -> Guardrail:
    row = await get_guardrail(session, user_id, data.rule)
    if row is None:
        row = Guardrail(user_id=user_id, rule=data.rule)
        session.add(row)
    row.active = data.active
    row.config_json = dict(data.config)
    await session.flush()
    return row


async def delete_guardrail(session: AsyncSession, user_id: uuid.UUID, rule: str) -> bool:
    result = await session.execute(delete(Guardrail).where(Guardrail.user_id == user_id, Guardrail.rule == rule))
    return bool(result.rowcount)


async def get_answers(session: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    return dict(row.answers_json) if row else {}


async def set_answers(session: AsyncSession, user_id: uuid.UUID, answers: dict[str, str]) -> None:
    row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    if row is None:
        row = Answers(user_id=user_id, answers_json={})
        session.add(row)
    row.answers_json = dict(answers)
    await session.flush()


async def list_watchlist(session: AsyncSession, user_id: uuid.UUID) -> list[WatchlistEntry]:
    return list(await session.scalars(select(WatchlistEntry).where(WatchlistEntry.user_id == user_id).order_by(WatchlistEntry.created_at)))


async def replace_watchlist(session: AsyncSession, user_id: uuid.UUID, entries: list[WatchlistEntryModel]) -> None:
    await session.execute(delete(WatchlistEntry).where(WatchlistEntry.user_id == user_id))
    for entry in entries:
        session.add(WatchlistEntry(user_id=user_id, company=entry.company, source=entry.source, board=entry.board))
    await session.flush()


async def delete_all_profile_rows(session: AsyncSession, user_id: uuid.UUID) -> None:
    for model in (ResumeBlock, ResumeBase, Track, Guardrail, Answers, WatchlistEntry):
        await session.execute(delete(model).where(model.user_id == user_id))
    await session.flush()
```

- [ ] **Step 4: Implement profile sync**

`apps/api/src/rhapto/services/__init__.py`:

```python
"""Application services: glue between db, engine, profile, and infrastructure."""
```

`apps/api/src/rhapto/services/profile_sync.py`:

```python
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db import models as db
from rhapto.db.repositories import profile as repo
from rhapto.engine.types import Profile, ProfileError
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block, Visibility
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.profile.loader import default_guardrails, dump_profile, load_profile, synthesize_bases


def block_row_to_model(row: db.ResumeBlock) -> Block:
    return Block(
        id=row.block_id, type=row.type, org=row.org, role=row.role, period=row.period, verified=row.verified,  # type: ignore[arg-type]
        metric=row.metric, content=row.content, tags=list(row.tags), attribution=row.attribution,
        concurrent=row.concurrent, visibility=Visibility(exclude_when=list(row.exclude_when)) if row.exclude_when else None,
    )


def base_row_to_model(row: db.ResumeBase) -> ResumeBase:
    return ResumeBase(id=row.base_id, name=row.name, block_ids=list(row.block_ids), section_order=list(row.section_order), style=dict(row.style_json))


def track_row_to_model(row: db.Track) -> Track:
    return Track(id=row.track_id, name=row.name, description=row.description, keywords=list(row.keywords), resume_base=row.resume_base, min_fit=row.min_fit)


def guardrail_row_to_model(row: db.Guardrail) -> GuardrailRule:
    return GuardrailRule(rule=row.rule, active=row.active, config=dict(row.config_json))


def watchlist_row_to_model(row: db.WatchlistEntry) -> WatchlistEntry:
    return WatchlistEntry(company=row.company, source=row.source, board=row.board)  # type: ignore[arg-type]


async def load_profile_from_db(session: AsyncSession, user_id: uuid.UUID) -> Profile:
    blocks = [block_row_to_model(r) for r in await repo.list_blocks(session, user_id)]
    if not blocks:
        raise ProfileError("profile has no blocks; import one with `rhapto profile import` or add blocks in the UI")
    tracks = [track_row_to_model(r) for r in await repo.list_tracks(session, user_id)]
    if not tracks:
        raise ProfileError("profile has no tracks")
    base_rows = await repo.list_bases(session, user_id)
    bases = [base_row_to_model(r) for r in base_rows] if base_rows else synthesize_bases(tracks, blocks)
    guardrail_rows = await repo.list_guardrails(session, user_id)
    guardrails = [guardrail_row_to_model(r) for r in guardrail_rows] if guardrail_rows else default_guardrails()
    return Profile(
        blocks=blocks, tracks=tracks, bases=bases, guardrails=guardrails,
        answers=await repo.get_answers(session, user_id),
        watchlist=[watchlist_row_to_model(r) for r in await repo.list_watchlist(session, user_id)],
    )


async def replace_profile_in_db(session: AsyncSession, user_id: uuid.UUID, profile: Profile) -> None:
    await repo.delete_all_profile_rows(session, user_id)
    for block in profile.blocks:
        await repo.upsert_block(session, user_id, block)
    for base in profile.bases:
        await repo.upsert_base(session, user_id, base)
    for track in profile.tracks:
        await repo.upsert_track(session, user_id, track)
    for rule in profile.guardrails:
        await repo.upsert_guardrail(session, user_id, rule)
    await repo.set_answers(session, user_id, profile.answers)
    await repo.replace_watchlist(session, user_id, profile.watchlist)


async def import_profile_dir(session: AsyncSession, user_id: uuid.UUID, path: Path) -> Profile:
    profile = load_profile(path)
    await replace_profile_in_db(session, user_id, profile)
    return profile


async def export_profile_dir(session: AsyncSession, user_id: uuid.UUID, path: Path) -> Profile:
    profile = await load_profile_from_db(session, user_id)
    dump_profile(profile, path)
    return profile
```

If mypy strict rejects the `# type: ignore[arg-type]` comments as unused, remove them; they cover the Literal fields (`type`, `source`) being assigned from `str` columns. If it instead reports an arg-type error there, keep them.

- [ ] **Step 5: CLI commands**

In `apps/api/src/rhapto/cli/main.py` add (imports at top: `import asyncio`, `from alembic import command`, `from alembic.config import Config`, `from rhapto.db.repositories.users import get_or_create_user`, `from rhapto.db.session import make_engine, make_session_factory`, `from rhapto.services.profile_sync import export_profile_dir, import_profile_dir`):

```python
db_app = typer.Typer(no_args_is_help=True, help="Database maintenance.")
app.add_typer(db_app, name="db")


def alembic_config() -> Config:
    """alembic.ini lives two directories above the package (apps/api) in a checkout and at /app in the image."""
    root = Path(__file__).resolve().parents[3]
    return Config(str(root / "alembic.ini"))


def run_migrations(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(alembic_config(), "head")


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply database migrations."""
    run_migrations(get_settings().database_url)
    typer.echo("database is up to date")


async def _with_user(database_url: str, email: str, fn):  # type: ignore[no-untyped-def]
    engine = make_engine(database_url)
    try:
        async with make_session_factory(engine)() as session:
            user = await get_or_create_user(session, email)
            result = await fn(session, user.id)
            await session.commit()
            return result
    finally:
        await engine.dispose()


@profile_app.command("import")
def profile_import(path: Path = typer.Argument(Path("./profile"), help="Profile directory to import (replaces the stored profile)")) -> None:
    """Import a YAML profile directory into the database, replacing what is stored."""
    settings = get_settings()
    try:
        profile = asyncio.run(_with_user(settings.database_url, settings.rhapto_user_email, lambda s, uid: import_profile_dir(s, uid, path)))
    except ProfileError as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"imported {len(profile.blocks)} blocks, {len(profile.tracks)} tracks for {settings.rhapto_user_email}")


@profile_app.command("export")
def profile_export(path: Path = typer.Argument(Path("./profile"), help="Directory to write YAML files into")) -> None:
    """Export the stored profile to a YAML directory."""
    settings = get_settings()
    try:
        profile = asyncio.run(_with_user(settings.database_url, settings.rhapto_user_email, lambda s, uid: export_profile_dir(s, uid, path)))
    except ProfileError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"exported {len(profile.blocks)} blocks to {path}")
```

`Path(__file__).resolve().parents[3]`: `cli/main.py` → parents[0] `cli`, [1] `rhapto`, [2] `src`, [3] `apps/api` (or `/app` in the image, where `src/` sits directly under `/app`). Add `import os` at the top.

- [ ] **Step 6: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/db tests/unit/test_cli.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: all pass. Smoke against the compose database: from `apps/api`, `uv run rhapto db upgrade`, then `uv run rhapto profile import ../../profile.example` (expect "imported 4 blocks, 2 tracks ..."), then `uv run rhapto profile export /tmp/rhapto-export` and `uv run rhapto profile validate /tmp/rhapto-export` (expect the `ok:` line with 5 guardrail rules).

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/rhapto/db apps/api/src/rhapto/services apps/api/src/rhapto/cli apps/api/tests
git commit -m "feat(profile): DB repositories, DB<->engine profile sync, CLI db upgrade and profile import/export"
```

---
### Task 3: Event bus and enqueuer abstractions (in-memory, Redis, arq, inline)

**Files:**
- Create: `apps/api/src/rhapto/services/eventbus.py`, `apps/api/src/rhapto/services/enqueue.py`
- Test: `apps/api/tests/unit/test_eventbus.py`, `apps/api/tests/unit/test_enqueue.py`

**Interfaces:**
- Produces (`rhapto.services.eventbus`): `Event = dict[str, Any]`; `EventBus` Protocol with `async publish(channel: str, event: Event) -> None` and `subscription(channel: str) -> AbstractAsyncContextManager[AsyncIterator[Event]]`; `InMemoryEventBus()` (also records `.published: list[tuple[str, Event]]`); `RedisEventBus(url: str)` with `async close()`; `task_channel(task_id: str) -> str` returning `f"task:{task_id}"`.
- Produces (`rhapto.services.enqueue`): `TaskFn = Callable[..., Awaitable[None]]`; `Enqueuer` Protocol with `async enqueue(task: str, **kwargs: Any) -> None`; `InlineEnqueuer(tasks: Mapping[str, TaskFn], ctx: dict[str, Any])` running the task immediately (records `.calls`); `ArqEnqueuer(redis_url: str)` with `async connect()`, `async close()`; `UnknownTaskError(KeyError)`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_eventbus.py`:

```python
import asyncio

from rhapto.services.eventbus import InMemoryEventBus, task_channel


def test_task_channel() -> None:
    assert task_channel("abc") == "task:abc"


async def test_subscriber_receives_events_published_after_subscribing() -> None:
    bus = InMemoryEventBus()
    received: list[dict[str, object]] = []

    async def consume() -> None:
        async with bus.subscription("task:1") as events:
            async for event in events:
                received.append(event)
                if event.get("event") == "done":
                    break

    consumer = asyncio.create_task(consume())
    await asyncio.sleep(0)
    await bus.publish("task:1", {"event": "progress", "step": "extract"})
    await bus.publish("task:2", {"event": "progress", "step": "ignored"})
    await bus.publish("task:1", {"event": "done"})
    await asyncio.wait_for(consumer, timeout=2)
    assert received == [{"event": "progress", "step": "extract"}, {"event": "done"}]
    assert bus.published[0] == ("task:1", {"event": "progress", "step": "extract"})


async def test_events_before_subscription_are_not_replayed() -> None:
    bus = InMemoryEventBus()
    await bus.publish("task:1", {"event": "progress", "step": "early"})
    async with bus.subscription("task:1") as events:
        await bus.publish("task:1", {"event": "done"})
        first = await asyncio.wait_for(events.__anext__(), timeout=1)
    assert first == {"event": "done"}


async def test_unsubscribe_on_exit() -> None:
    bus = InMemoryEventBus()
    async with bus.subscription("task:1"):
        assert bus.subscriber_count("task:1") == 1
    assert bus.subscriber_count("task:1") == 0
```

`apps/api/tests/unit/test_enqueue.py`:

```python
from typing import Any

import pytest

from rhapto.services.enqueue import InlineEnqueuer, UnknownTaskError


async def test_inline_enqueuer_runs_task_with_ctx() -> None:
    seen: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def hello(ctx: dict[str, Any], **kwargs: Any) -> None:
        seen.append((ctx, kwargs))

    enqueuer = InlineEnqueuer({"hello": hello}, ctx={"llm": "fake"})
    await enqueuer.enqueue("hello", task_id="t1")
    assert seen == [({"llm": "fake"}, {"task_id": "t1"})]
    assert enqueuer.calls == [("hello", {"task_id": "t1"})]


async def test_inline_enqueuer_unknown_task() -> None:
    enqueuer = InlineEnqueuer({}, ctx={})
    with pytest.raises(UnknownTaskError):
        await enqueuer.enqueue("nope")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_eventbus.py tests/unit/test_enqueue.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the event bus**

`apps/api/src/rhapto/services/eventbus.py`:

```python
from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any, Protocol

import redis.asyncio as aioredis

Event = dict[str, Any]


def task_channel(task_id: str) -> str:
    return f"task:{task_id}"


class EventBus(Protocol):
    async def publish(self, channel: str, event: Event) -> None: ...

    def subscription(self, channel: str) -> AbstractAsyncContextManager[AsyncIterator[Event]]: ...


class InMemoryEventBus:
    """Process-local pub/sub for tests and single-process runs. Subscribers only see events published after they subscribe."""

    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Event]]] = {}
        self.published: list[tuple[str, Event]] = []

    async def publish(self, channel: str, event: Event) -> None:
        self.published.append((channel, event))
        for queue in list(self._queues.get(channel, [])):
            queue.put_nowait(event)

    def subscriber_count(self, channel: str) -> int:
        return len(self._queues.get(channel, []))

    @asynccontextmanager
    async def subscription(self, channel: str) -> AsyncIterator[AsyncIterator[Event]]:
        queue: asyncio.Queue[Event] = asyncio.Queue()
        self._queues.setdefault(channel, []).append(queue)

        async def events() -> AsyncIterator[Event]:
            while True:
                yield await queue.get()

        try:
            yield events()
        finally:
            self._queues[channel].remove(queue)
            if not self._queues[channel]:
                del self._queues[channel]


class RedisEventBus:
    """Redis pub/sub; events are JSON objects."""

    def __init__(self, url: str) -> None:
        self._redis = aioredis.from_url(url, decode_responses=True)

    async def publish(self, channel: str, event: Event) -> None:
        await self._redis.publish(channel, json.dumps(event))

    @asynccontextmanager
    async def subscription(self, channel: str) -> AsyncIterator[AsyncIterator[Event]]:
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)

        async def events() -> AsyncIterator[Event]:
            while True:
                message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is None:
                    continue
                data = message["data"]
                yield json.loads(data) if isinstance(data, str) else data

        try:
            yield events()
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def close(self) -> None:
        await self._redis.aclose()
```

- [ ] **Step 4: Implement the enqueuer**

`apps/api/src/rhapto/services/enqueue.py`:

```python
from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any, Protocol

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

TaskFn = Callable[..., Awaitable[None]]


class UnknownTaskError(KeyError):
    """The task name is not registered."""


class Enqueuer(Protocol):
    async def enqueue(self, task: str, **kwargs: Any) -> None: ...


class InlineEnqueuer:
    """Runs the task immediately in-process. Used by tests and by single-process demos."""

    def __init__(self, tasks: Mapping[str, TaskFn], ctx: dict[str, Any]) -> None:
        self._tasks = dict(tasks)
        self.ctx = ctx
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def enqueue(self, task: str, **kwargs: Any) -> None:
        fn = self._tasks.get(task)
        if fn is None:
            raise UnknownTaskError(task)
        self.calls.append((task, dict(kwargs)))
        await fn(self.ctx, **kwargs)


class ArqEnqueuer:
    """Pushes jobs onto the arq queue in Redis."""

    def __init__(self, redis_url: str) -> None:
        self._settings = RedisSettings.from_dsn(redis_url)
        self._pool: ArqRedis | None = None

    async def connect(self) -> None:
        if self._pool is None:
            self._pool = await create_pool(self._settings)

    async def enqueue(self, task: str, **kwargs: Any) -> None:
        if self._pool is None:
            await self.connect()
        assert self._pool is not None
        await self._pool.enqueue_job(task, **kwargs)

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.aclose()
            self._pool = None
```

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_eventbus.py tests/unit/test_enqueue.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 6 passed, clean. If mypy complains about `redis.asyncio` types, add `"redis.*"` to the `ignore_missing_imports` override.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/services/eventbus.py apps/api/src/rhapto/services/enqueue.py apps/api/tests/unit/test_eventbus.py apps/api/tests/unit/test_enqueue.py
git commit -m "feat(services): event bus (in-memory, Redis) and enqueuer (inline, arq) abstractions"
```

---
### Task 4: Package storage and job-text services

**Files:**
- Create: `apps/api/src/rhapto/services/storage.py`, `apps/api/src/rhapto/services/jobtext.py`
- Test: `apps/api/tests/unit/test_storage.py`, `apps/api/tests/unit/test_jobtext.py`

**Interfaces:**
- Consumes: `rhapto.engine.render.pdf.convert_docx_to_pdf`, `soffice_available`, `PdfRenderError`.
- Produces (`rhapto.services.storage`): `PackageStorage(root: Path)` with `dir_for(package_id: str) -> Path`, `write_docx(package_id, data: bytes) -> Path`, `render_pdf(package_id, soffice_binary: str) -> Path | None` (returns None when LibreOffice is unavailable or fails), `path_for(package_id, name: Literal["resume.docx", "resume.pdf"]) -> Path | None` (None when missing), `read(package_id, name) -> bytes`, `build_zip(package_id, cover_note: str, package_json: str) -> bytes` (entries: `resume.docx` and `resume.pdf` when present, `cover-note.md`, `package.json`), `delete(package_id) -> None`.
- Produces (`rhapto.services.jobtext`): `JobTextError(Exception)`; `dedupe_hash(jd_text: str) -> str` (sha256 hex of lowercased, whitespace-collapsed first 4000 characters); `FetchText = Callable[[str], Awaitable[str]]`; `async fetch_job_text(url: str, *, client: httpx.AsyncClient | None = None) -> str` (GET with redirects and a 20 s timeout, `trafilatura.extract` on the HTML, fallback to a tag-stripped body, raises `JobTextError` on HTTP or extraction failure or when fewer than 200 characters of text result).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_storage.py`:

```python
import io
import zipfile
from pathlib import Path

import pytest

from rhapto.services import storage as storage_mod
from rhapto.services.storage import PackageStorage


def test_write_read_and_missing(tmp_path: Path) -> None:
    store = PackageStorage(tmp_path)
    path = store.write_docx("p1", b"PK-docx")
    assert path == tmp_path / "p1" / "resume.docx" and path.read_bytes() == b"PK-docx"
    assert store.read("p1", "resume.docx") == b"PK-docx"
    assert store.path_for("p1", "resume.pdf") is None
    assert store.path_for("p1", "resume.docx") == path


def test_render_pdf_skips_when_soffice_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    monkeypatch.setattr(storage_mod, "soffice_available", lambda binary: False)
    assert store.render_pdf("p1", "soffice") is None


def test_render_pdf_when_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    monkeypatch.setattr(storage_mod, "soffice_available", lambda binary: True)

    def fake_convert(docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(storage_mod, "convert_docx_to_pdf", fake_convert)
    assert store.render_pdf("p1", "soffice") == tmp_path / "p1" / "resume.pdf"


def test_render_pdf_swallows_render_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from rhapto.engine.render.pdf import PdfRenderError

    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    monkeypatch.setattr(storage_mod, "soffice_available", lambda binary: True)

    def boom(*args: object, **kwargs: object) -> Path:
        raise PdfRenderError("LibreOffice failed")

    monkeypatch.setattr(storage_mod, "convert_docx_to_pdf", boom)
    assert store.render_pdf("p1", "soffice") is None


def test_zip_contains_files(tmp_path: Path) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    data = store.build_zip("p1", "Dear team.", '{"version": 1}')
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert set(zf.namelist()) == {"resume.docx", "cover-note.md", "package.json"}
        assert zf.read("cover-note.md") == b"Dear team.\n"


def test_delete(tmp_path: Path) -> None:
    store = PackageStorage(tmp_path)
    store.write_docx("p1", b"PK")
    store.delete("p1")
    assert not (tmp_path / "p1").exists()
    store.delete("p1")  # idempotent
```

`apps/api/tests/unit/test_jobtext.py`:

```python
import httpx
import pytest

from rhapto.services.jobtext import JobTextError, dedupe_hash, fetch_job_text

HTML = "<html><body><nav>menu</nav><main><h1>Data Platform PM</h1>" + "<p>" + "We need Snowflake migration experience. " * 20 + "</p></main></body></html>"


def test_dedupe_hash_normalises_whitespace_and_case() -> None:
    assert dedupe_hash("Hello   World\n") == dedupe_hash("hello world")
    assert dedupe_hash("a") != dedupe_hash("b")
    assert len(dedupe_hash("x")) == 64


async def test_fetch_extracts_main_text() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        text = await fetch_job_text("https://example.com/job", client=client)
    assert "Snowflake migration" in text and "<p>" not in text


async def test_fetch_http_error_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="404"):
            await fetch_job_text("https://example.com/missing", client=client)


async def test_fetch_too_little_text_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body><p>tiny</p></body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JobTextError, match="too little"):
            await fetch_job_text("https://example.com/tiny", client=client)


def test_fetch_rejects_non_http_urls() -> None:
    import asyncio

    with pytest.raises(JobTextError, match="http"):
        asyncio.run(fetch_job_text("file:///etc/passwd"))
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_storage.py tests/unit/test_jobtext.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement storage**

`apps/api/src/rhapto/services/storage.py`:

```python
from __future__ import annotations

import io
import shutil
import zipfile
from pathlib import Path
from typing import Literal

from rhapto.engine.render.pdf import PdfRenderError, convert_docx_to_pdf, soffice_available

FileName = Literal["resume.docx", "resume.pdf"]


class PackageStorage:
    """Rendered package files under <root>/<package_id>/."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def dir_for(self, package_id: str) -> Path:
        return self.root / package_id

    def write_docx(self, package_id: str, data: bytes) -> Path:
        target = self.dir_for(package_id)
        target.mkdir(parents=True, exist_ok=True)
        path = target / "resume.docx"
        path.write_bytes(data)
        return path

    def render_pdf(self, package_id: str, soffice_binary: str) -> Path | None:
        docx = self.path_for(package_id, "resume.docx")
        if docx is None or not soffice_available(soffice_binary):
            return None
        try:
            return convert_docx_to_pdf(docx, self.dir_for(package_id), binary=soffice_binary)
        except PdfRenderError:
            return None

    def path_for(self, package_id: str, name: FileName) -> Path | None:
        path = self.dir_for(package_id) / name
        return path if path.is_file() else None

    def read(self, package_id: str, name: FileName) -> bytes:
        path = self.path_for(package_id, name)
        if path is None:
            raise FileNotFoundError(f"{name} not found for package {package_id}")
        return path.read_bytes()

    def build_zip(self, package_id: str, cover_note: str, package_json: str) -> bytes:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in ("resume.docx", "resume.pdf"):
                path = self.path_for(package_id, name)  # type: ignore[arg-type]
                if path is not None:
                    zf.write(path, name)
            zf.writestr("cover-note.md", cover_note.rstrip("\n") + "\n")
            zf.writestr("package.json", package_json)
        return buffer.getvalue()

    def delete(self, package_id: str) -> None:
        shutil.rmtree(self.dir_for(package_id), ignore_errors=True)
```

- [ ] **Step 4: Implement job text**

`apps/api/src/rhapto/services/jobtext.py`:

```python
from __future__ import annotations

import hashlib
import re
from collections.abc import Awaitable, Callable

import httpx
import trafilatura

FetchText = Callable[[str], Awaitable[str]]
MIN_TEXT_CHARS = 200
TIMEOUT_SECONDS = 20.0


class JobTextError(Exception):
    """The job posting could not be fetched or contained too little text."""


def dedupe_hash(jd_text: str) -> str:
    normalized = re.sub(r"\s+", " ", jd_text.strip().lower())[:4000]
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _strip_tags(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


async def fetch_job_text(url: str, *, client: httpx.AsyncClient | None = None) -> str:
    if not url.lower().startswith(("http://", "https://")):
        raise JobTextError("only http(s) URLs are supported")
    own_client = client is None
    client = client or httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT_SECONDS)
    try:
        try:
            response = await client.get(url, headers={"User-Agent": "rhapto/0.1 (+https://github.com)"})
        except httpx.HTTPError as exc:
            raise JobTextError(f"fetch failed: {exc}") from exc
        if response.status_code >= 400:
            raise JobTextError(f"fetch failed with HTTP {response.status_code}")
        html = response.text
    finally:
        if own_client:
            await client.aclose()
    extracted = trafilatura.extract(html, include_comments=False, include_tables=True) or _strip_tags(html)
    text = extracted.strip()
    if len(text) < MIN_TEXT_CHARS:
        raise JobTextError("too little text extracted from the page; paste the description instead")
    return text
```

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_storage.py tests/unit/test_jobtext.py -v && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 11 passed, clean. If `trafilatura.extract` returns None for the test HTML, the tag-stripping fallback still satisfies the assertions.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/services/storage.py apps/api/src/rhapto/services/jobtext.py apps/api/tests/unit/test_storage.py apps/api/tests/unit/test_jobtext.py
git commit -m "feat(services): package file storage and job posting text fetch"
```

---
### Task 5: FastAPI app factory, auth, RFC 7807 errors, health and me, API test client

**Files:**
- Create: `apps/api/src/rhapto/api/__init__.py`, `app.py`, `deps.py`, `errors.py`, `schemas.py`, `routers/__init__.py`, `routers/meta.py`
- Modify: `apps/api/pyproject.toml` (dev dep `asgi-lifespan>=2.1`)
- Create: `apps/api/tests/api/__init__.py` (empty), `apps/api/tests/api/conftest.py`, `apps/api/tests/api/test_meta.py`

**Interfaces:**
- Consumes: `Settings` (Task 1), `make_engine`, `make_session_factory`, `get_or_create_user` (Task 1), `EventBus`, `RedisEventBus`, `InMemoryEventBus`, `Enqueuer`, `ArqEnqueuer`, `InlineEnqueuer` (Task 3), `PackageStorage`, `FetchText`, `fetch_job_text`, `JobTextError` (Task 4), `EngineError`, `ProfileError`.
- Produces (`rhapto.api.deps`): `AppState` dataclass (`settings`, `session_factory`, `enqueuer`, `event_bus`, `storage`, `fetch_text`, `user_id: uuid.UUID | None`, `_engine`), `get_state(request) -> AppState`, `get_session(request) -> AsyncIterator[AsyncSession]` (yields a session; handlers commit explicitly), `current_user(request, authorization) -> uuid.UUID` (401 problem on missing or wrong bearer), `get_enqueuer`, `get_event_bus`, `get_storage`, `get_fetch_text`, `get_settings_dep`.
- Produces (`rhapto.api.errors`): `problem(status: int, title: str, detail: str | None = None, **extra) -> JSONResponse`, `install_error_handlers(app)`, `NotFound(HTTPException)` helper `not_found(what: str, ident: str)`.
- Produces (`rhapto.api.app`): `create_app(settings, *, session_factory=None, enqueuer=None, event_bus=None, storage=None, fetch_text=None) -> FastAPI`; module-level `app = create_app(get_settings())`; `API_PREFIX = "/api/v1"`.
- Produces (`rhapto.api.schemas`): `HealthOut(status: str)`, `MeOut(email: str, user_id: uuid.UUID)` (later tasks add their schemas here).
- Produces (tests/api/conftest.py): `ScriptableLLM(FakeLLMProvider)` with `script(*responses)`; fixtures `fake_llm`, `event_bus` (InMemoryEventBus), `storage` (PackageStorage under tmp_path), `fetched_text` (dict holder; `fake_fetch` returns `fetched_text["text"]` or raises `JobTextError`), `worker_ctx` (dict used by the inline enqueuer), `enqueuer` (InlineEnqueuer over `TASK_REGISTRY`, initially `{"embed_blocks": noop}` until Task 8 swaps in the real registry), `api_settings`, `app`, `client` (httpx AsyncClient through ASGITransport with lifespan, bearer header preset), `anon_client` (no auth header), `user_id` (from app state after lifespan), `imported_profile` (imports `profile.example` for the user).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/api/test_meta.py`:

```python
import httpx


async def test_health_is_public(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


async def test_me_requires_bearer(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/me")
    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["status"] == 401 and body["title"] == "Unauthorized"


async def test_me_rejects_wrong_token(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/me", headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_me_returns_user(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


async def test_unknown_route_is_problem_json(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_openapi_served(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/v1/openapi.json")
    assert response.status_code == 200 and response.json()["info"]["title"] == "Rhapto API"
```

- [ ] **Step 2: Write the API test fixtures**

`apps/api/tests/api/__init__.py`: empty file.

`apps/api/tests/api/conftest.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.api.app import create_app
from rhapto.api.deps import AppState
from rhapto.config import Settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.services.enqueue import InlineEnqueuer
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.jobtext import JobTextError
from rhapto.services.profile_sync import import_profile_dir
from rhapto.services.storage import PackageStorage

TOKEN = "test-token"


class ScriptableLLM(FakeLLMProvider):
    """FakeLLMProvider whose queue can be extended after construction."""

    def __init__(self) -> None:
        super().__init__(responses=[])

    def script(self, *responses: BaseModel | dict[str, Any]) -> None:
        self._queue.extend(responses)


async def _noop_task(ctx: dict[str, Any], **kwargs: Any) -> None:
    return None


# Task 8 replaces this with rhapto.worker.tasks.TASKS.
TASK_REGISTRY: dict[str, Callable[..., Awaitable[None]]] = {"embed_blocks": _noop_task}


@pytest.fixture
def fake_llm() -> ScriptableLLM:
    return ScriptableLLM()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    return InMemoryEventBus()


@pytest.fixture
def storage(tmp_path: Path) -> PackageStorage:
    return PackageStorage(tmp_path / "packages")


@pytest.fixture
def fetched_text() -> dict[str, str]:
    return {}


@pytest.fixture
def fake_fetch(fetched_text: dict[str, str]) -> Callable[[str], Awaitable[str]]:
    async def fetch(url: str) -> str:
        if "text" not in fetched_text:
            raise JobTextError("fetch failed with HTTP 404")
        return fetched_text["text"]

    return fetch


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        anthropic_api_key="test",
        rhapto_api_token=TOKEN,
        rhapto_user_email="test@example.com",
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
    )


@pytest.fixture
def worker_ctx(
    session_factory: async_sessionmaker[AsyncSession],
    fake_llm: ScriptableLLM,
    event_bus: InMemoryEventBus,
    storage: PackageStorage,
    api_settings: Settings,
) -> dict[str, Any]:
    return {
        "session_factory": session_factory,
        "llm": fake_llm,
        "embedder": FakeEmbeddingProvider(),
        "event_bus": event_bus,
        "storage": storage,
        "soffice_binary": api_settings.rhapto_soffice_binary,
    }


@pytest.fixture
def enqueuer(worker_ctx: dict[str, Any]) -> InlineEnqueuer:
    return InlineEnqueuer(TASK_REGISTRY, worker_ctx)


@pytest.fixture
async def app(
    api_settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    enqueuer: InlineEnqueuer,
    event_bus: InMemoryEventBus,
    storage: PackageStorage,
    fake_fetch: Callable[[str], Awaitable[str]],
) -> AsyncIterator[FastAPI]:
    application = create_app(
        api_settings, session_factory=session_factory, enqueuer=enqueuer, event_bus=event_bus, storage=storage, fetch_text=fake_fetch
    )
    async with LifespanManager(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": f"Bearer {TOKEN}"}
    ) as c:
        yield c


@pytest.fixture
async def anon_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
def user_id(app: FastAPI) -> uuid.UUID:
    state: AppState = app.state.rhapto
    assert state.user_id is not None
    return state.user_id


@pytest.fixture
async def imported_profile(session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID, demo_profile_dir: Path) -> None:
    async with session_factory() as session:
        await get_or_create_user(session, "test@example.com")
        await import_profile_dir(session, user_id, demo_profile_dir)
        await session.commit()
```

Add `"asgi-lifespan>=2.1"` to the dev group and `uv sync`.

- [ ] **Step 3: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/api/test_meta.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.api`.

- [ ] **Step 4: Implement errors, deps, schemas, meta router, app**

`apps/api/src/rhapto/api/__init__.py`:

```python
"""FastAPI application. May import services, db, engine, models, config."""
```

`apps/api/src/rhapto/api/errors.py`:

```python
from __future__ import annotations

from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from rhapto.engine.types import EngineError, ProfileError
from rhapto.services.jobtext import JobTextError

PROBLEM = "application/problem+json"


def problem(status: int, title: str, detail: str | None = None, **extra: Any) -> JSONResponse:
    body: dict[str, Any] = {"type": "about:blank", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def not_found(what: str, ident: object) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{what} {ident} not found")


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        title = HTTPStatus(exc.status_code).phrase
        detail = exc.detail if isinstance(exc.detail, str) else None
        response = problem(exc.status_code, title, detail)
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return problem(422, "Unprocessable Entity", "request validation failed", errors=exc.errors())

    @app.exception_handler(ProfileError)
    async def _profile(request: Request, exc: ProfileError) -> JSONResponse:
        return problem(422, "Unprocessable Entity", str(exc))

    @app.exception_handler(JobTextError)
    async def _jobtext(request: Request, exc: JobTextError) -> JSONResponse:
        return problem(422, "Unprocessable Entity", str(exc))

    @app.exception_handler(EngineError)
    async def _engine(request: Request, exc: EngineError) -> JSONResponse:
        return problem(500, "Internal Server Error", str(exc))
```

`apps/api/src/rhapto/api/deps.py`:

```python
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from rhapto.config import Settings
from rhapto.services.enqueue import Enqueuer
from rhapto.services.eventbus import EventBus
from rhapto.services.jobtext import FetchText
from rhapto.services.storage import PackageStorage


@dataclass
class AppState:
    settings: Settings
    session_factory: async_sessionmaker[AsyncSession]
    enqueuer: Enqueuer
    event_bus: EventBus
    storage: PackageStorage
    fetch_text: FetchText
    user_id: uuid.UUID | None = None
    engine: AsyncEngine | None = None


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.rhapto
    return state


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with get_state(request).session_factory() as session:
        yield session


def get_settings_dep(request: Request) -> Settings:
    return get_state(request).settings


def get_enqueuer(request: Request) -> Enqueuer:
    return get_state(request).enqueuer


def get_event_bus(request: Request) -> EventBus:
    return get_state(request).event_bus


def get_storage(request: Request) -> PackageStorage:
    return get_state(request).storage


def get_fetch_text(request: Request) -> FetchText:
    return get_state(request).fetch_text


async def current_user(request: Request, authorization: str | None = Header(default=None)) -> uuid.UUID:
    state = get_state(request)
    expected = state.settings.rhapto_api_token
    provided = authorization.removeprefix("Bearer ").strip() if authorization and authorization.startswith("Bearer ") else None
    if not expected or provided != expected or state.user_id is None:
        raise HTTPException(status_code=401, detail="missing or invalid bearer token", headers={"WWW-Authenticate": "Bearer"})
    return state.user_id


SessionDep = Depends(get_session)
UserDep = Depends(current_user)
```

`apps/api/src/rhapto/api/schemas.py`:

```python
from __future__ import annotations

import uuid

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: str


class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID
```

`apps/api/src/rhapto/api/routers/__init__.py`:

```python
"""API routers, one module per resource."""
```

`apps/api/src/rhapto/api/routers/meta.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.schemas import HealthOut, MeOut
from rhapto.db.models import User

router = APIRouter()


@router.get("/health", response_model=HealthOut)
async def health() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/me", response_model=MeOut)
async def me(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> MeOut:
    user = await session.get(User, user_id)
    assert user is not None
    return MeOut(email=user.email, user_id=user.id)
```

`apps/api/src/rhapto/api/app.py`:

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto import __version__
from rhapto.api.deps import AppState
from rhapto.api.errors import install_error_handlers
from rhapto.api.routers import meta
from rhapto.config import Settings, get_settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory
from rhapto.services.enqueue import ArqEnqueuer, Enqueuer
from rhapto.services.eventbus import EventBus, RedisEventBus
from rhapto.services.jobtext import FetchText, fetch_job_text
from rhapto.services.storage import PackageStorage

API_PREFIX = "/api/v1"


def create_app(
    settings: Settings,
    *,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
    enqueuer: Enqueuer | None = None,
    event_bus: EventBus | None = None,
    storage: PackageStorage | None = None,
    fetch_text: FetchText | None = None,
) -> FastAPI:
    engine = None
    if session_factory is None:
        engine = make_engine(settings.database_url)
        session_factory = make_session_factory(engine)
    state = AppState(
        settings=settings,
        session_factory=session_factory,
        enqueuer=enqueuer or ArqEnqueuer(settings.redis_url),
        event_bus=event_bus or RedisEventBus(settings.redis_url),
        storage=storage or PackageStorage(settings.rhapto_packages_dir),
        fetch_text=fetch_text or fetch_job_text,
        engine=engine,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with state.session_factory() as session:
            user = await get_or_create_user(session, settings.rhapto_user_email)
            await session.commit()
            state.user_id = user.id
        try:
            yield
        finally:
            if state.engine is not None:
                await state.engine.dispose()

    app = FastAPI(
        title="Rhapto API",
        version=__version__,
        lifespan=lifespan,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
    )
    app.state.rhapto = state
    app.add_middleware(
        CORSMiddleware, allow_origins=[settings.rhapto_web_origin], allow_methods=["*"], allow_headers=["*"], allow_credentials=False
    )
    install_error_handlers(app)
    app.include_router(meta.router, prefix=API_PREFIX, tags=["meta"])
    return app


app = create_app(get_settings())
```

Note: the module-level `app` constructs an engine lazily (SQLAlchemy connects on first use), so importing the module without a database is fine; tests build their own app via `create_app`.

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/api/test_meta.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 6 new passed, all green. If mypy flags `Header(default=None)` typing, annotate as `authorization: Annotated[str | None, Header()] = None`.

- [ ] **Step 6: Commit**

```bash
git add apps/api/pyproject.toml apps/api/uv.lock apps/api/src/rhapto/api apps/api/tests/api
git commit -m "feat(api): app factory, bearer auth, RFC 7807 errors, health and me endpoints, test client"
```

---
### Task 6: Profile routers (blocks, bases, tracks, guardrails, answers, watchlist, import, export)

**Files:**
- Create: `apps/api/src/rhapto/api/routers/profile.py`
- Modify: `apps/api/src/rhapto/api/app.py` (include router), `apps/api/src/rhapto/api/schemas.py` (add `ImportOut`)
- Test: `apps/api/tests/api/test_profile_api.py`

**Interfaces:**
- Consumes: repositories in `rhapto.db.repositories.profile` (Task 2), `profile_sync` row-to-model converters and `import_profile_dir`, `load_profile_from_db`, `dump_profile` (Task 2), deps (Task 5), `Enqueuer` (Task 3).
- Produces routes under `/api/v1/profile` (all require bearer):
  - `GET /blocks -> list[Block]`; `PUT /blocks/{block_id} (body Block, path id must equal body id) -> Block` (201 when created, 200 when updated); `DELETE /blocks/{block_id} -> 204`. After a PUT, enqueue `embed_blocks(user_id=str, block_ids=[block_id])`.
  - Same shape for `/bases/{base_id}` with `ResumeBase`, `/tracks/{track_id}` with `Track`, `/guardrails/{rule}` with `GuardrailRule`.
  - `GET /answers -> dict[str, str]`; `PUT /answers (body dict[str, str]) -> dict[str, str]`.
  - `GET /watchlist -> list[WatchlistEntry]`; `PUT /watchlist (body list[WatchlistEntry]) -> list[WatchlistEntry]` (replaces).
  - `POST /import` multipart with one or more of `blocks.yaml`, `tracks.yaml`, `bases.yaml`, `guardrails.yaml`, `answers.yaml`, `watchlist.yaml` as `files` -> `ImportOut(blocks: int, tracks: int, bases: int, guardrails: int)`; replaces the stored profile; enqueues `embed_blocks` for all block ids; 422 problem on `ProfileError`.
  - `GET /export -> application/zip` containing the six YAML files produced by `dump_profile`.
- Produces (`schemas.py`): `ImportOut`.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/api/test_profile_api.py`:

```python
import io
import zipfile
from pathlib import Path

import httpx
import pytest


async def test_blocks_crud_and_embedding_enqueued(client: httpx.AsyncClient, enqueuer) -> None:  # type: ignore[no-untyped-def]
    assert (await client.get("/api/v1/profile/blocks")).json() == []
    body = {"id": "acme-x", "type": "achievement", "content": "Did X.", "verified": True, "metric": "12 things", "tags": ["x"]}
    created = await client.put("/api/v1/profile/blocks/acme-x", json=body)
    assert created.status_code == 201 and created.json()["metric"] == "12 things"
    updated = await client.put("/api/v1/profile/blocks/acme-x", json={**body, "content": "Did X better."})
    assert updated.status_code == 200 and updated.json()["content"] == "Did X better."
    assert [b["id"] for b in (await client.get("/api/v1/profile/blocks")).json()] == ["acme-x"]
    assert ("embed_blocks", {"user_id": enqueuer.calls[0][1]["user_id"], "block_ids": ["acme-x"]}) == enqueuer.calls[0]
    assert (await client.delete("/api/v1/profile/blocks/acme-x")).status_code == 204
    assert (await client.delete("/api/v1/profile/blocks/acme-x")).status_code == 404


async def test_block_id_mismatch_is_422(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/v1/profile/blocks/one", json={"id": "two", "type": "role", "content": "c"})
    assert response.status_code == 422 and "id" in response.json()["detail"]


async def test_block_rejects_unknown_field(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/v1/profile/blocks/a", json={"id": "a", "type": "role", "content": "c", "bogus": 1})
    assert response.status_code == 422 and response.json()["title"] == "Unprocessable Entity"


@pytest.mark.parametrize(
    ("path", "key", "body"),
    [
        ("bases", "b1", {"id": "b1", "name": "Base", "block_ids": []}),
        ("tracks", "t1", {"id": "t1", "name": "Track", "resume_base": "b1"}),
        ("guardrails", "attribution", {"rule": "attribution", "active": False}),
    ],
)
async def test_generic_crud(client: httpx.AsyncClient, path: str, key: str, body: dict[str, object]) -> None:
    assert (await client.put(f"/api/v1/profile/{path}/{key}", json=body)).status_code == 201
    assert len((await client.get(f"/api/v1/profile/{path}")).json()) == 1
    assert (await client.delete(f"/api/v1/profile/{path}/{key}")).status_code == 204


async def test_answers_and_watchlist(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/profile/answers")).json() == {}
    put = await client.put("/api/v1/profile/answers", json={"name": "Maya Chen", "notice_period": "2 weeks"})
    assert put.status_code == 200 and put.json()["name"] == "Maya Chen"
    entries = [{"company": "ExampleCo", "source": "greenhouse", "board": "exampleco"}]
    assert (await client.put("/api/v1/profile/watchlist", json=entries)).json() == entries
    assert (await client.get("/api/v1/profile/watchlist")).json() == entries


async def test_import_and_export_round_trip(client: httpx.AsyncClient, demo_profile_dir: Path, enqueuer) -> None:  # type: ignore[no-untyped-def]
    files = [("files", (p.name, p.read_bytes(), "application/yaml")) for p in sorted(demo_profile_dir.glob("*.yaml"))]
    response = await client.post("/api/v1/profile/import", files=files)
    assert response.status_code == 200, response.text
    assert response.json() == {"blocks": 4, "tracks": 2, "bases": 2, "guardrails": 5}
    assert enqueuer.calls[-1][0] == "embed_blocks" and sorted(enqueuer.calls[-1][1]["block_ids"]) == ["acme-data-pm", "acme-migration", "cred-pmp", "side-llm-tool"]
    blocks = (await client.get("/api/v1/profile/blocks")).json()
    assert {b["id"] for b in blocks} == {"acme-data-pm", "acme-migration", "cred-pmp", "side-llm-tool"}

    export = await client.get("/api/v1/profile/export")
    assert export.status_code == 200 and export.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(export.content)) as zf:
        assert set(zf.namelist()) == {"blocks.yaml", "tracks.yaml", "bases.yaml", "guardrails.yaml", "answers.yaml", "watchlist.yaml"}
        assert b"Maya Chen" in zf.read("answers.yaml")


async def test_import_invalid_yaml_is_422(client: httpx.AsyncClient) -> None:
    files = [
        ("files", ("blocks.yaml", b"blocks: [{id: a, type: hobby, content: x}]\n", "application/yaml")),
        ("files", ("tracks.yaml", b"tracks: []\n", "application/yaml")),
    ]
    response = await client.post("/api/v1/profile/import", files=files)
    assert response.status_code == 422 and "blocks.yaml" in response.json()["detail"]


async def test_export_without_profile_is_422(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/profile/export")).status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/api/test_profile_api.py -v`
Expected: FAIL with 404s (router not mounted) or import errors.

- [ ] **Step 3: Implement**

Add to `apps/api/src/rhapto/api/schemas.py`:

```python
class ImportOut(BaseModel):
    blocks: int
    tracks: int
    bases: int
    guardrails: int
```

`apps/api/src/rhapto/api/routers/profile.py`:

```python
from __future__ import annotations

import io
import tempfile
import uuid
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session
from rhapto.api.errors import not_found
from rhapto.api.schemas import ImportOut
from rhapto.db.repositories import profile as repo
from rhapto.models.profile.bases import ResumeBase
from rhapto.models.profile.blocks import Block
from rhapto.models.profile.guardrails import GuardrailRule
from rhapto.models.profile.tracks import Track
from rhapto.models.profile.watchlist import WatchlistEntry
from rhapto.profile.loader import dump_profile
from rhapto.services.enqueue import Enqueuer
from rhapto.services.profile_sync import (
    base_row_to_model,
    block_row_to_model,
    guardrail_row_to_model,
    import_profile_dir,
    load_profile_from_db,
    track_row_to_model,
    watchlist_row_to_model,
)

router = APIRouter(prefix="/profile")
PROFILE_FILES = {"blocks.yaml", "tracks.yaml", "bases.yaml", "guardrails.yaml", "answers.yaml", "watchlist.yaml"}


def _check_id(path_id: str, body_id: str) -> None:
    if path_id != body_id:
        raise HTTPException(status_code=422, detail=f"path id {path_id!r} does not match body id {body_id!r}")


@router.get("/blocks", response_model=list[Block])
async def list_blocks(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[Block]:
    return [block_row_to_model(r) for r in await repo.list_blocks(session, user_id)]


@router.put("/blocks/{block_id}", response_model=Block)
async def put_block(
    block_id: str,
    body: Block,
    response: Response,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    enqueuer: Enqueuer = Depends(get_enqueuer),
) -> Block:
    _check_id(block_id, body.id)
    existed = await repo.get_block(session, user_id, block_id) is not None
    row = await repo.upsert_block(session, user_id, body)
    await session.commit()
    await enqueuer.enqueue("embed_blocks", user_id=str(user_id), block_ids=[block_id])
    response.status_code = 200 if existed else 201
    return block_row_to_model(row)


@router.delete("/blocks/{block_id}", status_code=204)
async def delete_block(block_id: str, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> Response:
    if not await repo.delete_block(session, user_id, block_id):
        raise not_found("block", block_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/bases", response_model=list[ResumeBase])
async def list_bases(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[ResumeBase]:
    return [base_row_to_model(r) for r in await repo.list_bases(session, user_id)]


@router.put("/bases/{base_id}", response_model=ResumeBase)
async def put_base(base_id: str, body: ResumeBase, response: Response, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> ResumeBase:
    _check_id(base_id, body.id)
    existed = await repo.get_base(session, user_id, base_id) is not None
    row = await repo.upsert_base(session, user_id, body)
    await session.commit()
    response.status_code = 200 if existed else 201
    return base_row_to_model(row)


@router.delete("/bases/{base_id}", status_code=204)
async def delete_base(base_id: str, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> Response:
    if not await repo.delete_base(session, user_id, base_id):
        raise not_found("base", base_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/tracks", response_model=list[Track])
async def list_tracks(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[Track]:
    return [track_row_to_model(r) for r in await repo.list_tracks(session, user_id)]


@router.put("/tracks/{track_id}", response_model=Track)
async def put_track(track_id: str, body: Track, response: Response, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> Track:
    _check_id(track_id, body.id)
    existed = await repo.get_track(session, user_id, track_id) is not None
    row = await repo.upsert_track(session, user_id, body)
    await session.commit()
    response.status_code = 200 if existed else 201
    return track_row_to_model(row)


@router.delete("/tracks/{track_id}", status_code=204)
async def delete_track(track_id: str, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> Response:
    if not await repo.delete_track(session, user_id, track_id):
        raise not_found("track", track_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/guardrails", response_model=list[GuardrailRule])
async def list_guardrails(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[GuardrailRule]:
    return [guardrail_row_to_model(r) for r in await repo.list_guardrails(session, user_id)]


@router.put("/guardrails/{rule}", response_model=GuardrailRule)
async def put_guardrail(rule: str, body: GuardrailRule, response: Response, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> GuardrailRule:
    _check_id(rule, body.rule)
    existed = await repo.get_guardrail(session, user_id, rule) is not None
    row = await repo.upsert_guardrail(session, user_id, body)
    await session.commit()
    response.status_code = 200 if existed else 201
    return guardrail_row_to_model(row)


@router.delete("/guardrails/{rule}", status_code=204)
async def delete_guardrail(rule: str, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> Response:
    if not await repo.delete_guardrail(session, user_id, rule):
        raise not_found("guardrail", rule)
    await session.commit()
    return Response(status_code=204)


@router.get("/answers", response_model=dict[str, str])
async def get_answers(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    return await repo.get_answers(session, user_id)


@router.put("/answers", response_model=dict[str, str])
async def put_answers(body: dict[str, str], user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    await repo.set_answers(session, user_id, body)
    await session.commit()
    return body


@router.get("/watchlist", response_model=list[WatchlistEntry])
async def get_watchlist(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[WatchlistEntry]:
    return [watchlist_row_to_model(r) for r in await repo.list_watchlist(session, user_id)]


@router.put("/watchlist", response_model=list[WatchlistEntry])
async def put_watchlist(body: list[WatchlistEntry], user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[WatchlistEntry]:
    await repo.replace_watchlist(session, user_id, body)
    await session.commit()
    return body


@router.post("/import", response_model=ImportOut)
async def import_profile(
    files: list[UploadFile],
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    enqueuer: Enqueuer = Depends(get_enqueuer),
) -> ImportOut:
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp)
        for upload in files:
            name = Path(upload.filename or "").name
            if name not in PROFILE_FILES:
                raise HTTPException(status_code=422, detail=f"unexpected file {name!r}; expected one of {sorted(PROFILE_FILES)}")
            (target / name).write_bytes(await upload.read())
        profile = await import_profile_dir(session, user_id, target)
    await session.commit()
    await enqueuer.enqueue("embed_blocks", user_id=str(user_id), block_ids=[b.id for b in profile.blocks])
    return ImportOut(blocks=len(profile.blocks), tracks=len(profile.tracks), bases=len(profile.bases), guardrails=len(profile.guardrails))


@router.get("/export")
async def export_profile(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> StreamingResponse:
    profile = await load_profile_from_db(session, user_id)
    with tempfile.TemporaryDirectory() as tmp:
        dump_profile(profile, Path(tmp))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(Path(tmp).glob("*.yaml")):
                zf.write(path, path.name)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="profile.zip"'})
```

In `app.py`, import `profile` alongside `meta` and add `app.include_router(profile.router, prefix=API_PREFIX, tags=["profile"])`.

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/api/test_profile_api.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 9 new passed (parametrized counts as 3), all green.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/api apps/api/tests/api/test_profile_api.py
git commit -m "feat(api): profile CRUD, import, and export endpoints"
```

---
### Task 7: Jobs repository and router (paste or URL intake, list, get, delete)

**Files:**
- Create: `apps/api/src/rhapto/db/repositories/jobs.py`, `apps/api/src/rhapto/api/routers/jobs.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (add job schemas), `apps/api/src/rhapto/api/app.py` (include router)
- Test: `apps/api/tests/api/test_jobs_api.py`

**Interfaces:**
- Consumes: `Job`, `Package`, `Application` models (Task 1), `dedupe_hash`, `FetchText`, `JobTextError` (Task 4), deps (Task 5).
- Produces (`rhapto.db.repositories.jobs`): `create_job(session, user_id, *, jd_text, source="manual", company=None, title=None, location=None, url=None) -> Job` (computes `dedupe_hash`, `discovered_at=now`), `find_duplicate(session, user_id, dedupe_hash) -> Job | None`, `list_jobs(session, user_id, *, search: str | None = None) -> list[Job]` (newest first; search matches company, title, or jd_text case-insensitively), `get_job(session, user_id, job_id) -> Job | None`, `delete_job(session, user_id, job_id) -> bool`, `latest_package(session, job_id) -> Package | None`, `application_for_job(session, job_id) -> Application | None`.
- Produces (`schemas.py`): `JobCreate(jd_text: str | None, url: str | None, company, title, location)` with a model validator requiring exactly one of `jd_text`/`url` and `jd_text` at least 50 characters when given; `PackageSummary(id, version, status, created_at)`; `JobOut(id, source, company, title, location, url, jd_text, extracted: JDExtract | None, discovered_at, latest_package: PackageSummary | None, application_status: str | None)`; `job_to_out(job, latest, application) -> JobOut` helper in the router module.
- Produces routes under `/api/v1/jobs`: `POST /` (201 `JobOut`; 409 problem with `existing_job_id` when the dedupe hash matches; 422 on fetch failure), `GET /?search=` (`list[JobOut]`), `GET /{job_id}` (`JobOut` or 404), `DELETE /{job_id}` (204 or 404; cascades packages and applications via FK, and deletes package files through storage).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/api/test_jobs_api.py`:

```python
import httpx

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


async def test_create_from_text_and_get(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/jobs", json={"jd_text": JD, "company": "ExampleCo", "title": "Data Platform PM"})
    assert response.status_code == 201, response.text
    job = response.json()
    assert job["company"] == "ExampleCo" and job["source"] == "manual" and job["latest_package"] is None
    assert job["application_status"] is None and job["extracted"] is None
    fetched = await client.get(f"/api/v1/jobs/{job['id']}")
    assert fetched.status_code == 200 and fetched.json()["jd_text"] == JD


async def test_duplicate_text_is_409_with_existing_id(client: httpx.AsyncClient) -> None:
    first = await client.post("/api/v1/jobs", json={"jd_text": JD})
    second = await client.post("/api/v1/jobs", json={"jd_text": "  " + JD.upper() + "\n"})
    assert second.status_code == 409
    assert second.json()["existing_job_id"] == first.json()["id"]


async def test_create_from_url_uses_fetcher(client: httpx.AsyncClient, fetched_text: dict[str, str]) -> None:
    fetched_text["text"] = JD
    response = await client.post("/api/v1/jobs", json={"url": "https://example.com/jobs/1"})
    assert response.status_code == 201 and response.json()["url"] == "https://example.com/jobs/1"
    assert response.json()["jd_text"] == JD


async def test_url_fetch_failure_is_422(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/jobs", json={"url": "https://example.com/missing"})
    assert response.status_code == 422 and "404" in response.json()["detail"]


async def test_requires_exactly_one_of_text_or_url(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/jobs", json={})).status_code == 422
    assert (await client.post("/api/v1/jobs", json={"jd_text": JD, "url": "https://x.example"})).status_code == 422
    assert (await client.post("/api/v1/jobs", json={"jd_text": "short"})).status_code == 422


async def test_list_and_search_newest_first(client: httpx.AsyncClient) -> None:
    await client.post("/api/v1/jobs", json={"jd_text": JD, "company": "ExampleCo", "title": "Data PM"})
    await client.post("/api/v1/jobs", json={"jd_text": "Beta Labs wants an AI Product Manager who has shipped LLM features. " * 3, "company": "Beta Labs", "title": "AI PM"})
    listed = (await client.get("/api/v1/jobs")).json()
    assert [j["company"] for j in listed] == ["Beta Labs", "ExampleCo"]
    assert [j["company"] for j in (await client.get("/api/v1/jobs", params={"search": "snowflake"})).json()] == ["ExampleCo"]


async def test_delete(client: httpx.AsyncClient) -> None:
    job_id = (await client.post("/api/v1/jobs", json={"jd_text": JD})).json()["id"]
    assert (await client.delete(f"/api/v1/jobs/{job_id}")).status_code == 204
    assert (await client.get(f"/api/v1/jobs/{job_id}")).status_code == 404
    assert (await client.delete(f"/api/v1/jobs/{job_id}")).status_code == 404


async def test_jobs_are_user_scoped(client: httpx.AsyncClient, session_factory, user_id) -> None:  # type: ignore[no-untyped-def]
    from rhapto.db.repositories.jobs import create_job
    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as session:
        other = await get_or_create_user(session, "other@example.com")
        await create_job(session, other.id, jd_text="Someone else's job description text that is long enough. " * 2)
        await session.commit()
    assert (await client.get("/api/v1/jobs")).json() == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/api/test_jobs_api.py -v`
Expected: FAIL (404 route not found / import errors).

- [ ] **Step 3: Implement the repository**

`apps/api/src/rhapto/db/repositories/jobs.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application, Job, Package
from rhapto.services.jobtext import dedupe_hash as _dedupe  # noqa: F401  (re-exported for callers)


def compute_dedupe_hash(jd_text: str) -> str:
    return _dedupe(jd_text)


async def create_job(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    jd_text: str,
    source: str = "manual",
    company: str | None = None,
    title: str | None = None,
    location: str | None = None,
    url: str | None = None,
) -> Job:
    job = Job(
        user_id=user_id, source=source, company=company, title=title, location=location, url=url,
        jd_text=jd_text, dedupe_hash=compute_dedupe_hash(jd_text), discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    return job


async def find_duplicate(session: AsyncSession, user_id: uuid.UUID, hash_value: str) -> Job | None:
    return await session.scalar(select(Job).where(Job.user_id == user_id, Job.dedupe_hash == hash_value))


async def list_jobs(session: AsyncSession, user_id: uuid.UUID, *, search: str | None = None) -> list[Job]:
    query = select(Job).where(Job.user_id == user_id)
    if search:
        pattern = f"%{search.lower()}%"
        query = query.where(or_(Job.company.ilike(pattern), Job.title.ilike(pattern), Job.jd_text.ilike(pattern)))
    return list(await session.scalars(query.order_by(Job.discovered_at.desc(), Job.id)))


async def get_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> Job | None:
    return await session.scalar(select(Job).where(Job.user_id == user_id, Job.id == job_id))


async def delete_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> bool:
    result = await session.execute(delete(Job).where(Job.user_id == user_id, Job.id == job_id))
    return bool(result.rowcount)


async def package_ids_for_job(session: AsyncSession, job_id: uuid.UUID) -> list[uuid.UUID]:
    return list(await session.scalars(select(Package.id).where(Package.job_id == job_id)))


async def latest_package(session: AsyncSession, job_id: uuid.UUID) -> Package | None:
    return await session.scalar(select(Package).where(Package.job_id == job_id).order_by(Package.version.desc()).limit(1))


async def application_for_job(session: AsyncSession, job_id: uuid.UUID) -> Application | None:
    return await session.scalar(select(Application).where(Application.job_id == job_id).order_by(Application.created_at.desc()).limit(1))
```

Layering note: `rhapto.db` importing `rhapto.services.jobtext` would violate the "db imports only models" rule. Instead, move `dedupe_hash` so both can use it without the cycle: create `apps/api/src/rhapto/db/hashing.py` containing the `dedupe_hash` function body (sha256 of the normalized first 4000 characters), have `rhapto.services.jobtext` import and re-export it from there (`from rhapto.db.hashing import dedupe_hash`), and have the repository import from `rhapto.db.hashing`. Delete the `_dedupe` import line above and use `from rhapto.db.hashing import dedupe_hash` with `compute_dedupe_hash = dedupe_hash`. The Task 4 tests for `dedupe_hash` keep importing it from `rhapto.services.jobtext` and must still pass.

- [ ] **Step 4: Implement schemas and router**

Add to `apps/api/src/rhapto/api/schemas.py` (imports: `from datetime import datetime`, `from pydantic import model_validator`, `from rhapto.models.jd_extract import JDExtract`):

```python
class JobCreate(BaseModel):
    jd_text: str | None = None
    url: str | None = None
    company: str | None = None
    title: str | None = None
    location: str | None = None

    @model_validator(mode="after")
    def _one_source(self) -> JobCreate:
        if bool(self.jd_text) == bool(self.url):
            raise ValueError("provide exactly one of jd_text or url")
        if self.jd_text is not None and len(self.jd_text.strip()) < 50:
            raise ValueError("jd_text must be at least 50 characters")
        return self


class PackageSummary(BaseModel):
    id: uuid.UUID
    version: int
    status: str
    created_at: datetime


class JobOut(BaseModel):
    id: uuid.UUID
    source: str
    company: str | None
    title: str | None
    location: str | None
    url: str | None
    jd_text: str
    extracted: JDExtract | None
    discovered_at: datetime
    latest_package: PackageSummary | None
    application_status: str | None
```

`apps/api/src/rhapto/api/routers/jobs.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_fetch_text, get_session, get_storage
from rhapto.api.errors import not_found, problem
from rhapto.api.schemas import JobCreate, JobOut, PackageSummary
from rhapto.db.models import Application, Job, Package
from rhapto.db.repositories import jobs as repo
from rhapto.models.jd_extract import JDExtract
from rhapto.services.jobtext import FetchText
from rhapto.services.storage import PackageStorage

router = APIRouter(prefix="/jobs")


def job_to_out(job: Job, latest: Package | None, application: Application | None) -> JobOut:
    return JobOut(
        id=job.id, source=job.source, company=job.company, title=job.title, location=job.location, url=job.url,
        jd_text=job.jd_text,
        extracted=JDExtract.model_validate(job.extracted_json) if job.extracted_json else None,
        discovered_at=job.discovered_at,
        latest_package=PackageSummary(id=latest.id, version=latest.version, status=latest.status, created_at=latest.created_at) if latest else None,
        application_status=application.status if application else None,
    )


async def _out(session: AsyncSession, job: Job) -> JobOut:
    return job_to_out(job, await repo.latest_package(session, job.id), await repo.application_for_job(session, job.id))


@router.post("", response_model=JobOut, status_code=201)
async def create_job(
    body: JobCreate,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    fetch_text: FetchText = Depends(get_fetch_text),
) -> JobOut | JSONResponse:
    jd_text = body.jd_text if body.jd_text is not None else await fetch_text(body.url or "")
    duplicate = await repo.find_duplicate(session, user_id, repo.compute_dedupe_hash(jd_text))
    if duplicate is not None:
        return problem(409, "Conflict", "a job with the same description already exists", existing_job_id=str(duplicate.id))
    job = await repo.create_job(
        session, user_id, jd_text=jd_text, company=body.company, title=body.title, location=body.location, url=body.url
    )
    await session.commit()
    return await _out(session, job)


@router.get("", response_model=list[JobOut])
async def list_jobs(
    search: str | None = Query(default=None), user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> list[JobOut]:
    return [await _out(session, job) for job in await repo.list_jobs(session, user_id, search=search)]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> JobOut:
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    return await _out(session, job)


@router.delete("/{job_id}", status_code=204)
async def delete_job(
    job_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: PackageStorage = Depends(get_storage),
) -> Response:
    package_ids = await repo.package_ids_for_job(session, job_id)
    if not await repo.delete_job(session, user_id, job_id):
        raise not_found("job", job_id)
    await session.commit()
    for package_id in package_ids:
        storage.delete(str(package_id))
    return Response(status_code=204)
```

Register in `app.py`: `app.include_router(jobs.router, prefix=API_PREFIX, tags=["jobs"])`. The `HTTPException` import is unused if everything goes through `problem`/`not_found`; remove it if ruff flags it.

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/api/test_jobs_api.py tests/unit/test_jobtext.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 8 new passed, all green, contracts kept.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/db apps/api/src/rhapto/services/jobtext.py apps/api/src/rhapto/api apps/api/tests/api/test_jobs_api.py
git commit -m "feat(api): jobs intake from pasted text or URL with dedupe, list, get, delete"
```

---
### Task 8: Task and package repositories, worker tasks (`tailor_job`, `embed_blocks`), arq worker settings

**Files:**
- Create: `apps/api/src/rhapto/db/repositories/tasks.py`, `apps/api/src/rhapto/db/repositories/packages.py`
- Create: `apps/api/src/rhapto/worker/__init__.py`, `apps/api/src/rhapto/worker/tasks.py`, `apps/api/src/rhapto/worker/main.py`
- Modify: `apps/api/tests/api/conftest.py` (use the real `TASKS` registry)
- Test: `apps/api/tests/unit/test_worker_tasks.py`

**Interfaces:**
- Consumes: `Task`, `Package`, `Job` models; `load_profile_from_db` (Task 2); `EventBus`, `task_channel` (Task 3); `PackageStorage` (Task 4); engine `tailor`, `TailorRequest`, `TailorResult`, `LLMBudgetExceeded`, `EngineError`; `ApplicationPackage`; providers.
- Produces (`repositories.tasks`): `create_task(session, user_id, type: str, progress: dict) -> Task`, `get_task(session, user_id, task_id) -> Task | None`, `mark_running(task)`, `set_step(task, step: str)`, `mark_succeeded(task, result_ref: str)`, `mark_failed(task, error: str)` (the mark/set helpers mutate the row and set `finished_at` where relevant; callers flush/commit).
- Produces (`repositories.packages`): `next_version(session, job_id) -> int`, `create_package(session, user_id, job_id, package: ApplicationPackage, *, selection_block_ids: list[str], parent_package_id: uuid.UUID | None, docx_path: str | None, pdf_path: str | None) -> Package`, `get_package(session, user_id, package_id) -> Package | None`, `list_packages_for_job(session, user_id, job_id) -> list[Package]` (version ascending), `package_row_to_model(row) -> ApplicationPackage`.
- Produces (`rhapto.worker.tasks`): `TASKS: dict[str, TaskFn]` with keys `tailor_job` and `embed_blocks`; `async tailor_job(ctx, task_id: str) -> None`; `async embed_blocks(ctx, user_id: str, block_ids: list[str]) -> None`; `WorkerContext` TypedDict documenting ctx keys (`session_factory`, `llm`, `embedder`, `event_bus`, `storage`, `soffice_binary`). Progress events: `{"event": "progress", "step": <name>}`, `{"event": "done", "package_id": <id>, "status": <draft|blocked>}`, `{"event": "error", "message": <str>}` on channel `task:<task_id>`.
- Produces (`rhapto.worker.main`): `WorkerSettings` for arq with `functions=[tailor_job, embed_blocks]`, `on_startup` building the ctx from settings (real providers, `RedisEventBus`, `PackageStorage`), `on_shutdown` disposing the engine, `redis_settings` from `REDIS_URL`.
- Task request contract: `task.progress_json["request"] = {"job_id": str, "track_id": str | None, "feedback": str | None, "parent_package_id": str | None}`; `task.progress_json["step"]` updated per pipeline step.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/unit/test_worker_tasks.py`:

```python
import uuid
from pathlib import Path
from typing import Any

from helpers import bullet, demo_extract, demo_resume
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import User
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.jobs import create_job
from rhapto.engine.compose import ComposeOutput
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.profile_sync import import_profile_dir
from rhapto.services.storage import PackageStorage
from rhapto.worker.tasks import TASKS, embed_blocks, tailor_job

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.", answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


def bad_output() -> dict[str, Any]:
    output = good_output()
    output["sections"][0]["entries"][0]["bullets"][1] = bullet("Cut warehouse cost 25%.", "acme-migration").model_dump()
    return output


async def _setup(session_factory: async_sessionmaker[AsyncSession], user: User, demo_profile_dir: Path, track_id: str | None = None) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        await import_profile_dir(session, user.id, demo_profile_dir)
        job = await create_job(session, user.id, jd_text=JD)
        task = await task_repo.create_task(
            session, user.id, "tailor_job",
            {"request": {"job_id": str(job.id), "track_id": track_id, "feedback": None, "parent_package_id": None}},
        )
        await session.commit()
        return job.id, task.id


def _ctx(session_factory: async_sessionmaker[AsyncSession], llm: FakeLLMProvider, bus: InMemoryEventBus, storage: PackageStorage) -> dict[str, Any]:
    return {"session_factory": session_factory, "llm": llm, "embedder": FakeEmbeddingProvider(), "event_bus": bus, "storage": storage, "soffice_binary": "soffice-missing"}


async def test_registry() -> None:
    assert set(TASKS) == {"tailor_job", "embed_blocks"} and TASKS["tailor_job"] is tailor_job


async def test_tailor_job_success_path(session_factory, user: User, demo_profile_dir: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(_ctx(session_factory, FakeLLMProvider([demo_extract(), good_output()]), bus, storage), task_id=str(task_id))

    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded" and task.finished_at is not None
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert package is not None and package.status == "draft" and package.version == 1 and package.llm_calls == 2
        assert package.track_id == "data-pm" and "acme-migration" in package.selection_block_ids
        assert package.docx_path and Path(package.docx_path).exists() and package.pdf_path is None
        job = await session.get(type(package).job.property.mapper.class_, job_id)  # Job row
        assert job is not None and job.company == "ExampleCo" and job.extracted_json is not None
    steps = [e["step"] for c, e in bus.published if e.get("event") == "progress"]
    assert steps == ["extract", "select", "compose", "validate", "render"]
    assert bus.published[-1][1]["event"] == "done" and bus.published[-1][1]["status"] == "draft"


async def test_tailor_job_blocked_still_creates_package(session_factory, user: User, demo_profile_dir: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir, track_id="ai-pm")
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(_ctx(session_factory, FakeLLMProvider([demo_extract(), bad_output(), bad_output()]), bus, storage), task_id=str(task_id))
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded"
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert package is not None and package.status == "blocked" and package.llm_calls == 3 and package.track_id == "ai-pm"
    assert bus.published[-1][1] == {"event": "done", "package_id": task.result_ref, "status": "blocked"}


async def test_tailor_job_failure_marks_task_failed(session_factory, user: User, demo_profile_dir: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(_ctx(session_factory, FakeLLMProvider([]), bus, storage), task_id=str(task_id))  # fake raises AssertionError
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "failed" and "no scripted response" in (task.error or "")
    assert bus.published[-1][1]["event"] == "error"


async def test_tailor_job_regeneration_increments_version(session_factory, user: User, demo_profile_dir: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(_ctx(session_factory, FakeLLMProvider([demo_extract(), good_output()]), bus, storage), task_id=str(task_id))
    async with session_factory() as session:
        first = (await package_repo.list_packages_for_job(session, user.id, job_id))[0]
        task2 = await task_repo.create_task(
            session, user.id, "tailor_job",
            {"request": {"job_id": str(job_id), "track_id": None, "feedback": "lean on migration", "parent_package_id": str(first.id)}},
        )
        await session.commit()
    llm = FakeLLMProvider([demo_extract(), good_output()])
    await tailor_job(_ctx(session_factory, llm, bus, storage), task_id=str(task2.id))
    async with session_factory() as session:
        packages = await package_repo.list_packages_for_job(session, user.id, job_id)
        assert [p.version for p in packages] == [1, 2] and packages[1].parent_package_id == first.id
    assert "lean on migration" in llm.calls[1].messages[0].content


async def test_embed_blocks_stores_vectors(session_factory, user: User, demo_profile_dir: Path, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        await import_profile_dir(session, user.id, demo_profile_dir)
        await session.commit()
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await embed_blocks(_ctx(session_factory, FakeLLMProvider([]), bus, storage), user_id=str(user.id), block_ids=["acme-migration", "ghost"])
    async with session_factory() as session:
        from rhapto.db.repositories.profile import get_block

        row = await get_block(session, user.id, "acme-migration")
        assert row is not None and row.embedding is not None and len(list(row.embedding)) == 384
        other = await get_block(session, user.id, "cred-pmp")
        assert other is not None and other.embedding is None
```

Replace the awkward `job = await session.get(type(package).job...` line with `from rhapto.db.models import Job` at the top and `job = await session.get(Job, job_id)`.

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/unit/test_worker_tasks.py -v`
Expected: FAIL with `ModuleNotFoundError: rhapto.worker`.

- [ ] **Step 3: Implement the repositories**

`apps/api/src/rhapto/db/repositories/tasks.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Task


async def create_task(session: AsyncSession, user_id: uuid.UUID, type: str, progress: dict[str, Any]) -> Task:
    task = Task(user_id=user_id, type=type, status="queued", progress_json=dict(progress))
    session.add(task)
    await session.flush()
    return task


async def get_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
    return await session.scalar(select(Task).where(Task.user_id == user_id, Task.id == task_id))


def mark_running(task: Task) -> None:
    task.status = "running"


def set_step(task: Task, step: str) -> None:
    task.progress_json = {**task.progress_json, "step": step}


def mark_succeeded(task: Task, result_ref: str) -> None:
    task.status = "succeeded"
    task.result_ref = result_ref
    task.finished_at = datetime.now(UTC)


def mark_failed(task: Task, error: str) -> None:
    task.status = "failed"
    task.error = error[:4000]
    task.finished_at = datetime.now(UTC)
```

`apps/api/src/rhapto/db/repositories/packages.py`:

```python
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Package
from rhapto.models.package import ApplicationPackage


async def next_version(session: AsyncSession, job_id: uuid.UUID) -> int:
    current = await session.scalar(select(func.max(Package.version)).where(Package.job_id == job_id))
    return (current or 0) + 1


async def create_package(
    session: AsyncSession,
    user_id: uuid.UUID,
    job_id: uuid.UUID,
    package: ApplicationPackage,
    *,
    selection_block_ids: list[str],
    parent_package_id: uuid.UUID | None,
    docx_path: str | None,
    pdf_path: str | None,
) -> Package:
    row = Package(
        user_id=user_id, job_id=job_id, track_id=package.track_id, version=package.version, status=package.status,
        resume_json=package.resume.model_dump(mode="json"), cover_note=package.cover_note, change_log=package.change_log,
        answers_json=dict(package.answers), guardrail_report_json=package.guardrail_report.model_dump(mode="json"),
        jd_extract_json=package.jd_extract.model_dump(mode="json"), selection_block_ids=list(selection_block_ids),
        llm_calls=package.llm_calls, docx_path=docx_path, pdf_path=pdf_path, parent_package_id=parent_package_id,
    )
    session.add(row)
    await session.flush()
    return row


async def get_package(session: AsyncSession, user_id: uuid.UUID, package_id: uuid.UUID) -> Package | None:
    return await session.scalar(select(Package).where(Package.user_id == user_id, Package.id == package_id))


async def list_packages_for_job(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID) -> list[Package]:
    return list(await session.scalars(select(Package).where(Package.user_id == user_id, Package.job_id == job_id).order_by(Package.version)))


def package_row_to_model(row: Package, *, job_company: str, job_title: str, jd_text: str, url: str | None = None, location: str | None = None) -> ApplicationPackage:
    return ApplicationPackage.model_validate(
        {
            "job": {"company": job_company, "title": job_title, "location": location, "url": url, "jd_text": jd_text},
            "track_id": row.track_id, "jd_extract": row.jd_extract_json, "resume": row.resume_json,
            "cover_note": row.cover_note, "change_log": row.change_log, "answers": row.answers_json,
            "guardrail_report": row.guardrail_report_json, "version": row.version, "status": row.status,
            "llm_calls": row.llm_calls, "created_at": row.created_at,
        }
    )
```

- [ ] **Step 4: Implement the worker**

`apps/api/src/rhapto/worker/__init__.py`:

```python
"""arq worker: background tasks that call the engine. May import services, db, engine, models, config."""
```

`apps/api/src/rhapto/worker/tasks.py`:

```python
from __future__ import annotations

import uuid
from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import EMBEDDING_DIMENSIONS, Job, Task
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.profile import get_block
from rhapto.engine.pipeline import tailor
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.select import block_text
from rhapto.engine.types import TailorRequest
from rhapto.services.enqueue import TaskFn
from rhapto.services.eventbus import EventBus, task_channel
from rhapto.services.profile_sync import block_row_to_model, load_profile_from_db
from rhapto.services.storage import PackageStorage


class WorkerContext(TypedDict):
    session_factory: async_sessionmaker[AsyncSession]
    llm: LLMProvider
    embedder: EmbeddingProvider
    event_bus: EventBus
    storage: PackageStorage
    soffice_binary: str


async def tailor_job(ctx: dict[str, Any], task_id: str) -> None:
    """Run the tailoring pipeline for the request stored on the task row; publish progress; persist the package."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    bus: EventBus = ctx["event_bus"]
    storage: PackageStorage = ctx["storage"]
    channel = task_channel(task_id)
    tid = uuid.UUID(task_id)

    async with factory() as session:
        task = await session.get(Task, tid)
        if task is None:
            return
        request = task.progress_json.get("request", {})
        task_repo.mark_running(task)
        await session.commit()
        user_id = task.user_id
        try:
            job = await session.get(Job, uuid.UUID(request["job_id"]))
            if job is None or job.user_id != user_id:
                raise ValueError("job not found for task")
            profile = await load_profile_from_db(session, user_id)
            previous = None
            parent_id = uuid.UUID(request["parent_package_id"]) if request.get("parent_package_id") else None
            if parent_id is not None:
                parent = await package_repo.get_package(session, user_id, parent_id)
                if parent is None:
                    raise ValueError("parent package not found")
                previous = package_repo.package_row_to_model(parent, job_company=job.company or "", job_title=job.title or "", jd_text=job.jd_text)

            async def on_step(step: str) -> None:
                task_repo.set_step(task, step)
                await session.commit()
                await bus.publish(channel, {"event": "progress", "step": step})

            result = await tailor(
                TailorRequest(jd_text=job.jd_text, track_id=request.get("track_id"), feedback=request.get("feedback"), previous_package=previous),
                profile, ctx["llm"], ctx["embedder"], on_step=on_step,
            )
            package = result.package
            version = await package_repo.next_version(session, job.id)
            package = package.model_copy(update={"version": version})
            row = await package_repo.create_package(
                session, user_id, job.id, package, selection_block_ids=result.selection.block_ids,
                parent_package_id=parent_id, docx_path=None, pdf_path=None,
            )
            if result.docx:
                row.docx_path = str(storage.write_docx(str(row.id), result.docx))
                pdf = storage.render_pdf(str(row.id), ctx["soffice_binary"])
                row.pdf_path = str(pdf) if pdf else None
            job.extracted_json = package.jd_extract.model_dump(mode="json")
            job.company = job.company or package.jd_extract.company
            job.title = job.title or package.jd_extract.title
            task_repo.mark_succeeded(task, str(row.id))
            await session.commit()
            await bus.publish(channel, {"event": "done", "package_id": str(row.id), "status": package.status})
        except Exception as exc:  # task boundary: record and report, never crash the worker
            await session.rollback()
            task = await session.get(Task, tid)
            if task is not None:
                task_repo.mark_failed(task, f"{type(exc).__name__}: {exc}")
                await session.commit()
            await bus.publish(channel, {"event": "error", "message": str(exc)})


async def embed_blocks(ctx: dict[str, Any], user_id: str, block_ids: list[str]) -> None:
    """Compute and store embeddings for the given blocks; unknown ids are ignored."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    embedder: EmbeddingProvider = ctx["embedder"]
    uid = uuid.UUID(user_id)
    async with factory() as session:
        rows = [r for r in [await get_block(session, uid, bid) for bid in block_ids] if r is not None]
        if not rows:
            return
        vectors = await embedder.embed([block_text(block_row_to_model(r)) for r in rows])
        for row, vector in zip(rows, vectors, strict=True):
            # Providers may differ in width (the test fake is 64-dim); the column is fixed at EMBEDDING_DIMENSIONS.
            sized = list(vector[:EMBEDDING_DIMENSIONS]) + [0.0] * max(0, EMBEDDING_DIMENSIONS - len(vector))
            row.embedding = sized
        await session.commit()


TASKS: dict[str, TaskFn] = {"tailor_job": tailor_job, "embed_blocks": embed_blocks}
```

Note: the `FakeEmbeddingProvider` used in tests has 64 dimensions while the column is 384, which is why `embed_blocks` pads or truncates to `EMBEDDING_DIMENSIONS`.

`apps/api/src/rhapto/worker/main.py`:

```python
from __future__ import annotations

from typing import Any

from arq.connections import RedisSettings

from rhapto.config import get_settings
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.embeddings import FastEmbedProvider
from rhapto.services.eventbus import RedisEventBus
from rhapto.services.storage import PackageStorage
from rhapto.worker.tasks import embed_blocks, tailor_job


async def on_startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    engine = make_engine(settings.database_url)
    ctx["engine"] = engine
    ctx["session_factory"] = make_session_factory(engine)
    ctx["llm"] = AnthropicProvider(model=settings.rhapto_llm_model, api_key=settings.anthropic_api_key)
    ctx["embedder"] = FastEmbedProvider(settings.rhapto_embedding_model)
    ctx["event_bus"] = RedisEventBus(settings.redis_url)
    ctx["storage"] = PackageStorage(settings.rhapto_packages_dir)
    ctx["soffice_binary"] = settings.rhapto_soffice_binary


async def on_shutdown(ctx: dict[str, Any]) -> None:
    await ctx["engine"].dispose()
    await ctx["event_bus"].close()


class WorkerSettings:
    functions = [tailor_job, embed_blocks]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    job_timeout = 600
```

Update `apps/api/tests/api/conftest.py`: replace the `TASK_REGISTRY` definition and `_noop_task` with `from rhapto.worker.tasks import TASKS as TASK_REGISTRY`.

- [ ] **Step 5: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/unit/test_worker_tasks.py tests/api -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 6 new passed, all green. ruff may flag the broad `except Exception`; keep the `# noqa: BLE001` only if the rule is enabled, otherwise remove the comment.

- [ ] **Step 6: Commit**

```bash
git add apps/api/src/rhapto/db/repositories apps/api/src/rhapto/worker apps/api/tests/unit/test_worker_tasks.py apps/api/tests/api/conftest.py
git commit -m "feat(worker): tailor_job and embed_blocks tasks with progress events; task and package repositories; arq settings"
```

---
### Task 9: Tailor endpoint, task status, and Server-Sent Events progress stream

**Files:**
- Create: `apps/api/src/rhapto/api/routers/tailor.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (add `TailorBody`, `TaskOut`), `apps/api/src/rhapto/api/app.py` (include router)
- Test: `apps/api/tests/api/test_tailor_api.py`

**Interfaces:**
- Consumes: `create_task`, `get_task` (Task 8), `get_job` (Task 7), `get_track` from the profile repo (Task 2), `Enqueuer`, `EventBus`, `task_channel` (Task 3), deps (Task 5), `TASKS` (Task 8, through the inline enqueuer in tests).
- Produces (`schemas.py`): `TailorBody(track_id: str | None = None, feedback: str | None = None, parent_package_id: uuid.UUID | None = None)`; `TaskOut(id, type, status, progress: dict[str, Any], error: str | None, result_ref: str | None, created_at, finished_at: datetime | None)`; `task_to_out(row) -> TaskOut` helper in the router.
- Produces routes: `POST /api/v1/jobs/{job_id}/tailor` (202 `TaskOut`; 404 unknown job; 422 unknown `track_id`; 404 unknown `parent_package_id`); `GET /api/v1/tasks/{task_id}` (`TaskOut` or 404); `GET /api/v1/tasks/{task_id}/events` (`text/event-stream`: first event `state` with the `TaskOut` JSON; then relays bus events as `progress`, `done`, or `error` events with JSON data; closes after `done`/`error`, or immediately after `state` if the task is already finished).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/api/test_tailor_api.py`:

```python
import asyncio
import json
from typing import Any

import httpx
import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.services.eventbus import InMemoryEventBus

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.", answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


async def _job(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/jobs", json={"jd_text": JD})
    assert response.status_code == 201
    return str(response.json()["id"])


def _events(raw: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for block in raw.strip().split("\n\n"):
        event, data = "", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if event:
            out.append((event, json.loads(data)))
    return out


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_runs_inline_and_task_succeeds(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    fake_llm.script(demo_extract(), good_output())
    job_id = await _job(client)
    accepted = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert accepted.status_code == 202, accepted.text
    task = accepted.json()
    assert task["type"] == "tailor_job" and task["status"] == "succeeded" and task["result_ref"]
    fetched = (await client.get(f"/api/v1/tasks/{task['id']}")).json()
    assert fetched["progress"]["step"] == "render" and fetched["finished_at"]
    job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert job["latest_package"]["id"] == task["result_ref"] and job["latest_package"]["status"] == "draft"
    assert job["company"] == "ExampleCo" and job["extracted"]["title"] == "Data Platform Program Manager"


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_validates_track_and_parent(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    assert (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"track_id": "nope"})).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"parent_package_id": missing})).status_code == 404
    assert (await client.post(f"/api/v1/jobs/{missing}/tailor", json={})).status_code == 404


async def test_tailor_without_profile_marks_task_failed(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "failed" and "no blocks" in task["error"]


@pytest.mark.usefixtures("imported_profile")
async def test_events_replays_finished_state_and_closes(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    fake_llm.script(demo_extract(), good_output())
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    async with client.stream("GET", f"/api/v1/tasks/{task['id']}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = (await response.aread()).decode()
    events = _events(raw)
    assert events[0][0] == "state" and events[0][1]["status"] == "succeeded"
    assert len(events) == 1


async def test_events_streams_progress_for_running_task(client: httpx.AsyncClient, event_bus: InMemoryEventBus, session_factory, user_id) -> None:  # type: ignore[no-untyped-def]
    from rhapto.db.repositories.tasks import create_task, mark_running

    async with session_factory() as session:
        task = await create_task(session, user_id, "tailor_job", {"request": {}})
        mark_running(task)
        await session.commit()
        task_id = str(task.id)

    async def publish_later() -> None:
        while event_bus.subscriber_count(f"task:{task_id}") == 0:
            await asyncio.sleep(0.01)
        await event_bus.publish(f"task:{task_id}", {"event": "progress", "step": "extract"})
        await event_bus.publish(f"task:{task_id}", {"event": "done", "package_id": "p", "status": "draft"})

    publisher = asyncio.create_task(publish_later())
    async with client.stream("GET", f"/api/v1/tasks/{task_id}/events") as response:
        raw = (await asyncio.wait_for(response.aread(), timeout=5)).decode()
    await publisher
    events = _events(raw)
    assert [e for e, _ in events] == ["state", "progress", "done"]
    assert events[1][1]["step"] == "extract"


async def test_events_unknown_task_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000/events")).status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/api/test_tailor_api.py -v`
Expected: FAIL (404 route not found).

- [ ] **Step 3: Implement**

Add to `schemas.py`:

```python
class TailorBody(BaseModel):
    track_id: str | None = None
    feedback: str | None = None
    parent_package_id: uuid.UUID | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    type: str
    status: str
    progress: dict[str, Any]
    error: str | None
    result_ref: str | None
    created_at: datetime
    finished_at: datetime | None
```

(`from typing import Any` at the top.)

`apps/api/src/rhapto/api/routers/tailor.py`:

```python
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from rhapto.api.deps import AppState, current_user, get_enqueuer, get_event_bus, get_session, get_state
from rhapto.api.errors import not_found
from rhapto.api.schemas import TailorBody, TaskOut
from rhapto.db.models import Task
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.profile import get_track
from rhapto.services.enqueue import Enqueuer
from rhapto.services.eventbus import EventBus, task_channel

router = APIRouter()
FINISHED = {"succeeded", "failed"}


def task_to_out(row: Task) -> TaskOut:
    return TaskOut(
        id=row.id, type=row.type, status=row.status, progress=dict(row.progress_json), error=row.error,
        result_ref=row.result_ref, created_at=row.created_at, finished_at=row.finished_at,
    )


@router.post("/jobs/{job_id}/tailor", response_model=TaskOut, status_code=202)
async def tailor_job_endpoint(
    job_id: uuid.UUID,
    body: TailorBody,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    enqueuer: Enqueuer = Depends(get_enqueuer),
) -> TaskOut:
    if await job_repo.get_job(session, user_id, job_id) is None:
        raise not_found("job", job_id)
    if body.track_id is not None and await get_track(session, user_id, body.track_id) is None:
        raise HTTPException(status_code=422, detail=f"unknown track {body.track_id!r}")
    if body.parent_package_id is not None:
        parent = await package_repo.get_package(session, user_id, body.parent_package_id)
        if parent is None or parent.job_id != job_id:
            raise not_found("package", body.parent_package_id)
    request = {
        "job_id": str(job_id), "track_id": body.track_id, "feedback": body.feedback,
        "parent_package_id": str(body.parent_package_id) if body.parent_package_id else None,
    }
    task = await task_repo.create_task(session, user_id, "tailor_job", {"request": request})
    await session.commit()  # the worker (inline or arq) must see the row
    task_id = task.id
    await enqueuer.enqueue("tailor_job", task_id=str(task_id))
    session.expire_all()
    refreshed = await task_repo.get_task(session, user_id, task_id)
    assert refreshed is not None
    return task_to_out(refreshed)


@router.get("/tasks/{task_id}", response_model=TaskOut)
async def get_task(task_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> TaskOut:
    task = await task_repo.get_task(session, user_id, task_id)
    if task is None:
        raise not_found("task", task_id)
    return task_to_out(task)


@router.get("/tasks/{task_id}/events")
async def task_events(
    task_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    bus: EventBus = Depends(get_event_bus),
    state: AppState = Depends(get_state),
) -> EventSourceResponse:
    task = await task_repo.get_task(session, user_id, task_id)
    if task is None:
        raise not_found("task", task_id)

    async def stream() -> AsyncIterator[dict[str, str]]:
        async with bus.subscription(task_channel(str(task_id))) as events:
            async with state.session_factory() as fresh:
                current = await task_repo.get_task(fresh, user_id, task_id)
            assert current is not None
            yield {"event": "state", "data": task_to_out(current).model_dump_json()}
            if current.status in FINISHED:
                return
            async for event in events:
                yield {"event": str(event.get("event", "message")), "data": json.dumps(event)}
                if event.get("event") in {"done", "error"}:
                    return

    return EventSourceResponse(stream())
```

The subscription is opened before the fresh state read so no event published between the two is lost; the fresh session comes from `state.session_factory()` because the request-scoped session closes when the handler returns while the stream keeps running.

Register in `app.py`: `app.include_router(tailor.router, prefix=API_PREFIX, tags=["tailor"])`.

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/api/test_tailor_api.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 6 new passed, all green. If `sse_starlette` emits a ping comment before the first event, the `_events` parser ignores comment lines (they start with `:`); if it interleaves pings mid-stream on a slow machine, they are also ignored.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/api apps/api/tests/api/test_tailor_api.py
git commit -m "feat(api): tailor endpoint, task status, and SSE progress stream"
```

---
### Task 10: Packages router (list, get, edit with re-validation, download zip, files)

**Files:**
- Create: `apps/api/src/rhapto/api/routers/packages.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (add `PackageOut`, `PackagePatch`), `apps/api/src/rhapto/api/app.py` (include router)
- Test: `apps/api/tests/api/test_packages_api.py`

**Interfaces:**
- Consumes: `get_package`, `list_packages_for_job`, `create_package`, `next_version`, `package_row_to_model` (Task 8); `get_job` (Task 7); `load_profile_from_db` (Task 2); `run_guardrails(resume, profile, selection_ids, extract, cover_note=...)` from the engine; `render_docx`, `OrphanBulletError`; `PackageStorage` (Task 4); deps (Task 5).
- Produces (`schemas.py`): `PackageOut(id, job_id, track_id, version, status, resume: ResumeDocument, cover_note, change_log, answers: dict[str, str], guardrail_report: GuardrailReport, jd_extract: JDExtract, llm_calls, parent_package_id: uuid.UUID | None, has_docx: bool, has_pdf: bool, created_at)`; `PackagePatch(resume: ResumeDocument)`; `package_to_out(row) -> PackageOut` helper in the router.
- Produces routes: `GET /api/v1/jobs/{job_id}/packages -> list[PackageOut]` (version ascending; 404 unknown job); `GET /api/v1/packages/{id} -> PackageOut`; `PATCH /api/v1/packages/{id}` body `PackagePatch` -> 201 `PackageOut` of the NEW version (parent = id; guardrails re-run with the stored selection and the existing cover note; DOCX re-rendered unless provenance fails; `llm_calls` 0; status per report); `GET /api/v1/packages/{id}/download -> application/zip` (`resume.docx`, `resume.pdf` if present, `cover-note.md`, `package.json`); `GET /api/v1/packages/{id}/files/{name}` for `resume.docx` (`application/vnd.openxmlformats-officedocument.wordprocessingml.document`) or `resume.pdf` (`application/pdf`), 404 when missing.

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/api/test_packages_api.py`:

```python
import io
import zipfile
from typing import Any

import httpx
import pytest
from helpers import bullet, demo_extract, demo_resume

from rhapto.engine.compose import ComposeOutput

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary, sections=resume.sections, cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.", answers={"why_this_company": "Data."},
    ).model_dump(mode="json")


async def _tailored(client: httpx.AsyncClient, fake_llm) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    fake_llm.script(demo_extract(), good_output())
    job_id = str((await client.post("/api/v1/jobs", json={"jd_text": JD})).json()["id"])
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "succeeded", task
    return job_id, str(task["result_ref"])


@pytest.mark.usefixtures("imported_profile")
async def test_list_and_get(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    job_id, package_id = await _tailored(client, fake_llm)
    listed = (await client.get(f"/api/v1/jobs/{job_id}/packages")).json()
    assert [p["version"] for p in listed] == [1] and listed[0]["id"] == package_id
    package = (await client.get(f"/api/v1/packages/{package_id}")).json()
    assert package["status"] == "draft" and package["has_docx"] is True and package["has_pdf"] is False
    assert package["resume"]["header"]["name"] == "Maya Chen" and package["guardrail_report"]["passed"] is True
    assert package["jd_extract"]["company"] == "ExampleCo" and package["llm_calls"] == 2


@pytest.mark.usefixtures("imported_profile")
async def test_patch_creates_new_validated_version(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    job_id, package_id = await _tailored(client, fake_llm)
    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["sections"][0]["entries"][0]["bullets"][0]["text"] = "Led cross-functional delivery of the customer data platform across 4 teams, on time."
    patched = await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})
    assert patched.status_code == 201, patched.text
    new = patched.json()
    assert new["version"] == 2 and new["parent_package_id"] == package_id and new["status"] == "draft"
    assert new["llm_calls"] == 0 and new["has_docx"] is True and new["cover_note"].startswith("Dear team")
    assert [p["version"] for p in (await client.get(f"/api/v1/jobs/{job_id}/packages")).json()] == [1, 2]


@pytest.mark.usefixtures("imported_profile")
async def test_patch_with_invented_metric_is_blocked(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package_id = await _tailored(client, fake_llm)
    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["sections"][0]["entries"][0]["bullets"][1] = bullet("Cut warehouse cost 25%.", "acme-migration").model_dump()
    new = (await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})).json()
    assert new["status"] == "blocked"
    assert {v["rule"] for v in new["guardrail_report"]["violations"]} == {"no-unverified-metrics"}
    assert new["has_docx"] is True  # rendered for review; only orphan bullets suppress the DOCX


@pytest.mark.usefixtures("imported_profile")
async def test_patch_with_orphan_bullet_has_no_docx(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package_id = await _tailored(client, fake_llm)
    resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
    resume["summary"] = [bullet("Made up.", "ghost").model_dump()]
    new = (await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})).json()
    assert new["status"] == "blocked" and new["has_docx"] is False
    assert any(v["rule"] == "provenance" for v in new["guardrail_report"]["violations"])
    assert (await client.get(f"/api/v1/packages/{new['id']}/files/resume.docx")).status_code == 404


@pytest.mark.usefixtures("imported_profile")
async def test_download_zip_and_files(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package_id = await _tailored(client, fake_llm)
    download = await client.get(f"/api/v1/packages/{package_id}/download")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
        assert set(zf.namelist()) == {"resume.docx", "cover-note.md", "package.json"}
        assert b'"version": 1' in zf.read("package.json")
    docx = await client.get(f"/api/v1/packages/{package_id}/files/resume.docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    assert (await client.get(f"/api/v1/packages/{package_id}/files/resume.pdf")).status_code == 404
    assert (await client.get(f"/api/v1/packages/{package_id}/files/evil.txt")).status_code == 422


async def test_unknown_package_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/v1/packages/{missing}")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{missing}/packages")).status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/api/test_packages_api.py -v`
Expected: FAIL (404 route not found).

- [ ] **Step 3: Implement**

Add to `schemas.py` (imports: `from rhapto.models.guardrail_report import GuardrailReport`, `from rhapto.models.resume_document import ResumeDocument`):

```python
class PackageOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    track_id: str
    version: int
    status: str
    resume: ResumeDocument
    cover_note: str
    change_log: str
    answers: dict[str, str]
    guardrail_report: GuardrailReport
    jd_extract: JDExtract
    llm_calls: int
    parent_package_id: uuid.UUID | None
    has_docx: bool
    has_pdf: bool
    created_at: datetime


class PackagePatch(BaseModel):
    resume: ResumeDocument
```

`apps/api/src/rhapto/api/routers/packages.py`:

```python
from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session, get_settings_dep, get_storage
from rhapto.api.errors import not_found
from rhapto.api.schemas import PackageOut, PackagePatch
from rhapto.config import Settings
from rhapto.db.models import Package
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as repo
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.resume_document import ResumeDocument
from rhapto.services.profile_sync import load_profile_from_db
from rhapto.services.storage import PackageStorage

router = APIRouter()
DOCX_MEDIA = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
FileName = Literal["resume.docx", "resume.pdf"]


def package_to_out(row: Package) -> PackageOut:
    return PackageOut(
        id=row.id, job_id=row.job_id, track_id=row.track_id, version=row.version, status=row.status,
        resume=ResumeDocument.model_validate(row.resume_json), cover_note=row.cover_note, change_log=row.change_log,
        answers=dict(row.answers_json), guardrail_report=GuardrailReport.model_validate(row.guardrail_report_json),
        jd_extract=JDExtract.model_validate(row.jd_extract_json), llm_calls=row.llm_calls,
        parent_package_id=row.parent_package_id, has_docx=row.docx_path is not None, has_pdf=row.pdf_path is not None,
        created_at=row.created_at,
    )


async def _get(session: AsyncSession, user_id: uuid.UUID, package_id: uuid.UUID) -> Package:
    row = await repo.get_package(session, user_id, package_id)
    if row is None:
        raise not_found("package", package_id)
    return row


@router.get("/jobs/{job_id}/packages", response_model=list[PackageOut])
async def list_packages(job_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> list[PackageOut]:
    if await job_repo.get_job(session, user_id, job_id) is None:
        raise not_found("job", job_id)
    return [package_to_out(r) for r in await repo.list_packages_for_job(session, user_id, job_id)]


@router.get("/packages/{package_id}", response_model=PackageOut)
async def get_package(package_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> PackageOut:
    return package_to_out(await _get(session, user_id, package_id))


@router.patch("/packages/{package_id}", response_model=PackageOut, status_code=201)
async def patch_package(
    package_id: uuid.UUID,
    body: PackagePatch,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: PackageStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings_dep),
) -> PackageOut:
    """Edited resume -> re-validate with the stored selection -> re-render -> new version. Never bypasses guardrails."""
    parent = await _get(session, user_id, package_id)
    job = await job_repo.get_job(session, user_id, parent.job_id)
    assert job is not None
    profile = await load_profile_from_db(session, user_id)
    extract = JDExtract.model_validate(parent.jd_extract_json)
    report = run_guardrails(body.resume, profile, parent.selection_block_ids, extract, cover_note=parent.cover_note)
    try:
        docx = render_docx(body.resume, profile.block_map())
    except OrphanBulletError:
        docx = b""
    model = repo.package_row_to_model(parent, job_company=job.company or extract.company, job_title=job.title or extract.title, jd_text=job.jd_text, url=job.url, location=job.location)
    model = model.model_copy(
        update={
            "resume": body.resume, "guardrail_report": report, "status": "draft" if report.passed else "blocked",
            "llm_calls": 0, "version": await repo.next_version(session, parent.job_id),
        }
    )
    row = await repo.create_package(
        session, user_id, parent.job_id, model, selection_block_ids=list(parent.selection_block_ids),
        parent_package_id=parent.id, docx_path=None, pdf_path=None,
    )
    if docx:
        row.docx_path = str(storage.write_docx(str(row.id), docx))
        pdf = storage.render_pdf(str(row.id), settings.rhapto_soffice_binary)
        row.pdf_path = str(pdf) if pdf else None
    await session.commit()
    return package_to_out(row)


@router.get("/packages/{package_id}/download")
async def download_package(
    package_id: uuid.UUID,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: PackageStorage = Depends(get_storage),
) -> Response:
    row = await _get(session, user_id, package_id)
    job = await job_repo.get_job(session, user_id, row.job_id)
    assert job is not None
    model = repo.package_row_to_model(row, job_company=job.company or "", job_title=job.title or "", jd_text=job.jd_text, url=job.url, location=job.location)
    data = storage.build_zip(str(row.id), row.cover_note, model.model_dump_json(indent=2))
    filename = f"rhapto-package-v{row.version}.zip"
    return Response(content=data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/packages/{package_id}/files/{name}")
async def package_file(
    package_id: uuid.UUID,
    name: str,
    user_id: uuid.UUID = Depends(current_user),
    session: AsyncSession = Depends(get_session),
    storage: PackageStorage = Depends(get_storage),
) -> FileResponse:
    if name not in ("resume.docx", "resume.pdf"):
        raise HTTPException(status_code=422, detail="name must be resume.docx or resume.pdf")
    row = await _get(session, user_id, package_id)
    path = storage.path_for(str(row.id), name)  # type: ignore[arg-type]
    if path is None:
        raise not_found("file", name)
    media = DOCX_MEDIA if name == "resume.docx" else "application/pdf"
    return FileResponse(path, media_type=media, filename=name)
```

Register in `app.py`: `app.include_router(packages.router, prefix=API_PREFIX, tags=["packages"])`.

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/api/test_packages_api.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 6 new passed, all green.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/api apps/api/tests/api/test_packages_api.py
git commit -m "feat(api): packages list, get, validated edit as new version, zip download, files"
```

---
### Task 11: Applications router (kanban tracker)

**Files:**
- Create: `apps/api/src/rhapto/db/repositories/applications.py`, `apps/api/src/rhapto/api/routers/applications.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (add application schemas), `apps/api/src/rhapto/api/app.py` (include router)
- Test: `apps/api/tests/api/test_applications_api.py`

**Interfaces:**
- Consumes: `Application`, `Job`, `Package`, `APPLICATION_STATUSES` (Task 1); `get_job` (Task 7); `get_package` (Task 8); deps (Task 5).
- Produces (`repositories.applications`): `create_application(session, user_id, job_id, package_id: uuid.UUID | None) -> Application` (status `queued`, history `[{"status": "queued", "at": iso}]`), `get_application(session, user_id, application_id) -> Application | None`, `list_applications(session, user_id) -> list[Application]` (newest first), `set_status(application, status: str) -> None` (appends history when changed; sets `applied_at` the first time status becomes `applied`), `delete_application(session, user_id, application_id) -> bool`, `application_for_job` already exists in the jobs repo.
- Produces (`schemas.py`): `StatusChange(status: str, at: datetime)`; `ApplicationCreate(job_id: uuid.UUID, package_id: uuid.UUID | None = None)`; `ApplicationPatch(status: str | None = None, notes: str | None = None)` with a validator restricting `status` to `APPLICATION_STATUSES`; `JobRef(id, company, title)`; `ApplicationOut(id, job: JobRef, package_id, status, applied_at, notes, status_history: list[StatusChange], created_at, updated_at)`; `BoardOut(columns: dict[str, list[ApplicationOut]])` with every status present as a key, in `APPLICATION_STATUSES` order.
- Produces routes under `/api/v1/applications`: `POST` (201; 404 unknown job or package; 409 problem when the job already has an application, with `existing_application_id`), `GET` (`BoardOut`), `GET /{id}`, `PATCH /{id}` (`ApplicationOut`; 422 invalid status), `DELETE /{id}` (204).

- [ ] **Step 1: Write the failing tests**

`apps/api/tests/api/test_applications_api.py`:

```python
import httpx

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3
STATUSES = ["discovered", "queued", "applied", "screen", "interview", "offer", "closed"]


async def _job(client: httpx.AsyncClient, company: str = "ExampleCo") -> str:
    response = await client.post("/api/v1/jobs", json={"jd_text": JD + company, "company": company, "title": "PM"})
    return str(response.json()["id"])


async def test_create_and_board(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    created = await client.post("/api/v1/applications", json={"job_id": job_id})
    assert created.status_code == 201, created.text
    app = created.json()
    assert app["status"] == "queued" and app["job"] == {"id": job_id, "company": "ExampleCo", "title": "PM"}
    assert [h["status"] for h in app["status_history"]] == ["queued"] and app["applied_at"] is None
    board = (await client.get("/api/v1/applications")).json()
    assert list(board["columns"]) == STATUSES
    assert [a["id"] for a in board["columns"]["queued"]] == [app["id"]]
    assert (await client.get(f"/api/v1/jobs/{job_id}")).json()["application_status"] == "queued"


async def test_one_application_per_job(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    first = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()
    second = await client.post("/api/v1/applications", json={"job_id": job_id})
    assert second.status_code == 409 and second.json()["existing_application_id"] == first["id"]


async def test_unknown_job_or_package_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post("/api/v1/applications", json={"job_id": missing})).status_code == 404
    job_id = await _job(client)
    assert (await client.post("/api/v1/applications", json={"job_id": job_id, "package_id": missing})).status_code == 404


async def test_patch_status_and_notes_with_history(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    app_id = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()["id"]
    moved = (await client.patch(f"/api/v1/applications/{app_id}", json={"status": "applied", "notes": "Sent via portal"})).json()
    assert moved["status"] == "applied" and moved["applied_at"] is not None and moved["notes"] == "Sent via portal"
    assert [h["status"] for h in moved["status_history"]] == ["queued", "applied"]
    same = (await client.patch(f"/api/v1/applications/{app_id}", json={"status": "applied"})).json()
    assert len(same["status_history"]) == 2  # unchanged status does not append
    later = (await client.patch(f"/api/v1/applications/{app_id}", json={"status": "interview"})).json()
    assert later["applied_at"] == moved["applied_at"]
    board = (await client.get("/api/v1/applications")).json()
    assert [a["id"] for a in board["columns"]["interview"]] == [app_id] and board["columns"]["queued"] == []


async def test_patch_invalid_status_422(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    app_id = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()["id"]
    assert (await client.patch(f"/api/v1/applications/{app_id}", json={"status": "hired"})).status_code == 422


async def test_delete(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    app_id = (await client.post("/api/v1/applications", json={"job_id": job_id})).json()["id"]
    assert (await client.delete(f"/api/v1/applications/{app_id}")).status_code == 204
    assert (await client.get(f"/api/v1/applications/{app_id}")).status_code == 404
    assert (await client.get(f"/api/v1/jobs/{job_id}")).json()["application_status"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `cd apps/api && uv run pytest tests/api/test_applications_api.py -v`
Expected: FAIL (404 route not found).

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/db/repositories/applications.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def create_application(session: AsyncSession, user_id: uuid.UUID, job_id: uuid.UUID, package_id: uuid.UUID | None) -> Application:
    row = Application(
        user_id=user_id, job_id=job_id, package_id=package_id, status="queued", notes="",
        status_history_json=[{"status": "queued", "at": _now_iso()}],
    )
    session.add(row)
    await session.flush()
    return row


async def get_application(session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> Application | None:
    return await session.scalar(select(Application).where(Application.user_id == user_id, Application.id == application_id))


async def list_applications(session: AsyncSession, user_id: uuid.UUID) -> list[Application]:
    return list(await session.scalars(select(Application).where(Application.user_id == user_id).order_by(Application.created_at.desc())))


def set_status(application: Application, status: str) -> None:
    if status == application.status:
        return
    application.status = status
    application.status_history_json = [*application.status_history_json, {"status": status, "at": _now_iso()}]
    if status == "applied" and application.applied_at is None:
        application.applied_at = datetime.now(UTC)


async def delete_application(session: AsyncSession, user_id: uuid.UUID, application_id: uuid.UUID) -> bool:
    result = await session.execute(delete(Application).where(Application.user_id == user_id, Application.id == application_id))
    return bool(result.rowcount)
```

Add to `schemas.py` (import `field_validator` from pydantic and `APPLICATION_STATUSES` from `rhapto.db.models`):

```python
class StatusChange(BaseModel):
    status: str
    at: datetime


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    package_id: uuid.UUID | None = None


class ApplicationPatch(BaseModel):
    status: str | None = None
    notes: str | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(APPLICATION_STATUSES)}")
        return value


class JobRef(BaseModel):
    id: uuid.UUID
    company: str | None
    title: str | None


class ApplicationOut(BaseModel):
    id: uuid.UUID
    job: JobRef
    package_id: uuid.UUID | None
    status: str
    applied_at: datetime | None
    notes: str
    status_history: list[StatusChange]
    created_at: datetime
    updated_at: datetime


class BoardOut(BaseModel):
    columns: dict[str, list[ApplicationOut]]
```

`apps/api/src/rhapto/api/routers/applications.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.errors import not_found, problem
from rhapto.api.schemas import ApplicationCreate, ApplicationOut, ApplicationPatch, BoardOut, JobRef, StatusChange
from rhapto.db.models import APPLICATION_STATUSES, Application, Job
from rhapto.db.repositories import applications as repo
from rhapto.db.repositories import jobs as job_repo
from rhapto.db.repositories import packages as package_repo

router = APIRouter(prefix="/applications")


def application_to_out(row: Application, job: Job) -> ApplicationOut:
    return ApplicationOut(
        id=row.id, job=JobRef(id=job.id, company=job.company, title=job.title), package_id=row.package_id,
        status=row.status, applied_at=row.applied_at, notes=row.notes,
        status_history=[StatusChange.model_validate(h) for h in row.status_history_json],
        created_at=row.created_at, updated_at=row.updated_at,
    )


async def _out(session: AsyncSession, row: Application) -> ApplicationOut:
    job = await session.get(Job, row.job_id)
    assert job is not None
    return application_to_out(row, job)


@router.post("", response_model=ApplicationOut, status_code=201)
async def create_application(
    body: ApplicationCreate, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> ApplicationOut | JSONResponse:
    job = await job_repo.get_job(session, user_id, body.job_id)
    if job is None:
        raise not_found("job", body.job_id)
    if body.package_id is not None:
        package = await package_repo.get_package(session, user_id, body.package_id)
        if package is None or package.job_id != job.id:
            raise not_found("package", body.package_id)
    existing = await job_repo.application_for_job(session, job.id)
    if existing is not None:
        return problem(409, "Conflict", "this job already has an application", existing_application_id=str(existing.id))
    row = await repo.create_application(session, user_id, job.id, body.package_id)
    await session.commit()
    return application_to_out(row, job)


@router.get("", response_model=BoardOut)
async def board(user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> BoardOut:
    columns: dict[str, list[ApplicationOut]] = {status: [] for status in APPLICATION_STATUSES}
    for row in await repo.list_applications(session, user_id):
        columns.setdefault(row.status, []).append(await _out(session, row))
    return BoardOut(columns=columns)


@router.get("/{application_id}", response_model=ApplicationOut)
async def get_application(application_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> ApplicationOut:
    row = await repo.get_application(session, user_id, application_id)
    if row is None:
        raise not_found("application", application_id)
    return await _out(session, row)


@router.patch("/{application_id}", response_model=ApplicationOut)
async def patch_application(
    application_id: uuid.UUID, body: ApplicationPatch, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> ApplicationOut:
    row = await repo.get_application(session, user_id, application_id)
    if row is None:
        raise not_found("application", application_id)
    if body.status is not None:
        repo.set_status(row, body.status)
    if body.notes is not None:
        row.notes = body.notes
    await session.commit()
    await session.refresh(row)
    return await _out(session, row)


@router.delete("/{application_id}", status_code=204)
async def delete_application(application_id: uuid.UUID, user_id: uuid.UUID = Depends(current_user), session: AsyncSession = Depends(get_session)) -> Response:
    if not await repo.delete_application(session, user_id, application_id):
        raise not_found("application", application_id)
    await session.commit()
    return Response(status_code=204)
```

Register in `app.py`: `app.include_router(applications.router, prefix=API_PREFIX, tags=["applications"])`.

- [ ] **Step 4: Run tests, lint, and type-check**

Run: `cd apps/api && uv run pytest tests/api/test_applications_api.py -v && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports`
Expected: 6 new passed, all green.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/rhapto/db/repositories/applications.py apps/api/src/rhapto/api apps/api/tests/api/test_applications_api.py
git commit -m "feat(api): application tracker with kanban board, status history, and notes"
```

---
### Task 12: Docker api and worker targets, full Compose stack, layering contracts, README backend section, end-to-end smoke

**Files:**
- Modify: `apps/api/Dockerfile`, `docker-compose.yml`, `apps/api/.importlinter`, `README.md`, `.dockerignore`
- Create: `scripts/smoke-api.sh`

**Interfaces:**
- Produces Docker targets `api` (uvicorn on 8000, runs migrations first) and `worker` (arq, LibreOffice, embedding model); Compose services `api` and `worker` on top of `db` and `redis`; import-linter contracts for every layer; a README section explaining how to run the backend and how the exit codes and statuses map.

- [ ] **Step 1: Import-linter contracts**

Replace `apps/api/.importlinter` with:

```ini
[importlinter]
root_package = rhapto

[importlinter:contract:engine-is-pure]
name = engine must not import application layers
type = forbidden
source_modules =
    rhapto.engine
forbidden_modules =
    rhapto.config
    rhapto.profile
    rhapto.db
    rhapto.services
    rhapto.worker
    rhapto.api
    rhapto.cli

[importlinter:contract:db-imports-only-models]
name = db must not import engine, profile, services, worker, api, cli, or config
type = forbidden
source_modules =
    rhapto.db
forbidden_modules =
    rhapto.engine
    rhapto.profile
    rhapto.services
    rhapto.worker
    rhapto.api
    rhapto.cli
    rhapto.config

[importlinter:contract:profile-imports-only-models-and-engine]
name = profile must not import db, services, worker, api, cli, or config
type = forbidden
source_modules =
    rhapto.profile
forbidden_modules =
    rhapto.db
    rhapto.services
    rhapto.worker
    rhapto.api
    rhapto.cli
    rhapto.config

[importlinter:contract:services-do-not-import-entrypoints]
name = services must not import worker, api, or cli
type = forbidden
source_modules =
    rhapto.services
forbidden_modules =
    rhapto.worker
    rhapto.api
    rhapto.cli

[importlinter:contract:worker-and-api-are-separate]
name = worker and api must not import each other or cli
type = forbidden
source_modules =
    rhapto.worker
    rhapto.api
forbidden_modules =
    rhapto.cli
```

Add one more contract so the worker never imports the api and vice versa:

```ini
[importlinter:contract:worker-api-independence]
name = worker and api are independent
type = independence
modules =
    rhapto.worker
    rhapto.api
```

Run `cd apps/api && uv run lint-imports` and expect every contract kept. If `db-imports-only-models` is broken because `rhapto.db.hashing` is imported by `rhapto.services.jobtext` (allowed) but `rhapto.db.repositories.jobs` imports services (not allowed), fix the import direction as Task 7 specified (db owns `hashing.py`; services import from db).

- [ ] **Step 2: Dockerfile targets**

Replace `apps/api/Dockerfile` with:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/pyproject.toml apps/api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY apps/api/src ./src
COPY apps/api/alembic.ini ./alembic.ini
COPY apps/api/alembic ./alembic
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"

# API: migrations then uvicorn.
FROM base AS api
EXPOSE 8000
CMD ["sh", "-c", "rhapto db upgrade && uvicorn rhapto.api.app:app --host 0.0.0.0 --port 8000"]

# Heavy layer shared by worker and cli: LibreOffice for PDF and the embedding model.
FROM base AS heavy
RUN apt-get update \
    && apt-get install -y --no-install-recommends libreoffice-writer fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
ENV FASTEMBED_CACHE_PATH=/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')"

FROM heavy AS worker
CMD ["arq", "rhapto.worker.main.WorkerSettings"]

FROM heavy AS cli
WORKDIR /work
ENTRYPOINT ["rhapto"]
CMD ["--help"]
```

`alembic.ini` uses `%(here)s/alembic` and `%(here)s/src`, so copying it to `/app/alembic.ini` with `alembic/` and `src/` beside it keeps `rhapto db upgrade` working inside the image (`Path(__file__).resolve().parents[3]` from `/app/src/rhapto/cli/main.py` is `/app`).

- [ ] **Step 3: Compose api and worker**

Add to `docker-compose.yml` under `services` (keep `db` and `redis` as they are):

```yaml
  api:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
      target: api
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://rhapto:rhapto@db:5432/rhapto
      REDIS_URL: redis://redis:6379/0
      RHAPTO_PACKAGES_DIR: /data/packages
    ports:
      - "8000:8000"
    volumes:
      - packages:/data/packages
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  worker:
    build:
      context: .
      dockerfile: apps/api/Dockerfile
      target: worker
    env_file: .env
    environment:
      DATABASE_URL: postgresql+asyncpg://rhapto:rhapto@db:5432/rhapto
      REDIS_URL: redis://redis:6379/0
      RHAPTO_PACKAGES_DIR: /data/packages
      FASTEMBED_CACHE_PATH: /models
    volumes:
      - packages:/data/packages
      - models:/models
    depends_on:
      api:
        condition: service_started
      redis:
        condition: service_healthy
```

and under `volumes` add `packages:` and `models:`.

- [ ] **Step 4: Smoke script and README**

`scripts/smoke-api.sh`:

```bash
#!/usr/bin/env bash
# End-to-end smoke against a running compose stack: health, auth, profile import, job intake, tailor, package download.
# Requires: docker compose up -d (all services), .env with RHAPTO_API_TOKEN and ANTHROPIC_API_KEY, curl, jq.
set -euo pipefail
BASE="${RHAPTO_API_URL:-http://localhost:8000/api/v1}"
TOKEN="${RHAPTO_API_TOKEN:-$(grep -E '^RHAPTO_API_TOKEN=' .env | cut -d= -f2-)}"
auth=(-H "Authorization: Bearer $TOKEN")

echo "health: $(curl -fsS "$BASE/health")"
echo "me: $(curl -fsS "${auth[@]}" "$BASE/me")"
files=()
for f in profile.example/*.yaml; do files+=(-F "files=@$f"); done
echo "import: $(curl -fsS "${auth[@]}" -X POST "$BASE/profile/import" "${files[@]}")"
JD='ExampleCo is hiring a Data Platform Program Manager to lead our Snowflake migration and ETL modernisation across product, data engineering, and analytics teams. Must have warehouse migration experience and cross-functional leadership.'
job=$(curl -fsS "${auth[@]}" -H 'content-type: application/json' -X POST "$BASE/jobs" -d "{\"jd_text\": $(printf '%s' "$JD" | jq -Rs .), \"company\": \"ExampleCo\", \"title\": \"Data Platform Program Manager\"}")
job_id=$(echo "$job" | jq -r .id)
echo "job: $job_id"
task=$(curl -fsS "${auth[@]}" -H 'content-type: application/json' -X POST "$BASE/jobs/$job_id/tailor" -d '{}')
task_id=$(echo "$task" | jq -r .id)
echo "task: $task_id (waiting for the worker)"
for _ in $(seq 1 60); do
  status=$(curl -fsS "${auth[@]}" "$BASE/tasks/$task_id" | jq -r .status)
  [ "$status" = "succeeded" ] || [ "$status" = "failed" ] && break
  sleep 2
done
curl -fsS "${auth[@]}" "$BASE/tasks/$task_id" | jq '{status, error, step: .progress.step}'
package_id=$(curl -fsS "${auth[@]}" "$BASE/tasks/$task_id" | jq -r .result_ref)
[ "$package_id" != "null" ] && curl -fsS "${auth[@]}" "$BASE/packages/$package_id/download" -o out/smoke-package.zip && echo "downloaded out/smoke-package.zip"
```

Make it executable (`git update-index --chmod=+x scripts/smoke-api.sh`). Append to `README.md`:

````markdown
## Backend (phase 0.2)

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY and RHAPTO_API_TOKEN
docker compose up -d          # db, redis, api (http://localhost:8000), worker
docker compose exec api rhapto profile import /work/profile   # or use POST /api/v1/profile/import
open http://localhost:8000/api/v1/docs
```

Every request except `/api/v1/health` needs `Authorization: Bearer <RHAPTO_API_TOKEN>`. Paste a job description with
`POST /api/v1/jobs`, start tailoring with `POST /api/v1/jobs/{id}/tailor`, follow progress on
`GET /api/v1/tasks/{id}/events` (Server-Sent Events), then fetch, edit, or download the package under `/api/v1/packages`.
Editing a package re-runs the guardrails and creates a new version; a `blocked` status means a guardrail failed and the
report says why. The tracker lives under `/api/v1/applications`. Nothing here submits an application anywhere.

Development without Docker for the app itself: `docker compose up -d db redis`, then from `apps/api`:
`uv run rhapto db upgrade`, `uv run uvicorn rhapto.api.app:app --reload`, and in another shell
`uv run arq rhapto.worker.main.WorkerSettings`. Tests: `uv run pytest` (API tests need the compose `db`).
`bash scripts/smoke-api.sh` exercises a running stack end to end (needs `curl` and `jq`).
````

Add a `.dockerignore` entry for `apps/web/` (the future frontend) so backend builds stay small, and keep `apps/api/tests/` excluded.

- [ ] **Step 5: Build and smoke the full stack**

From the repo root (Docker Desktop running):

```bash
docker compose build api worker
docker compose up -d
docker compose ps
curl -fsS http://localhost:8000/api/v1/health
```

Expected: all four services running, health returns `{"status":"ok"}`. Then run `MSYS_NO_PATHCONV=1 bash scripts/smoke-api.sh` only if `.env` has a real `ANTHROPIC_API_KEY`; otherwise run the first three steps of the script manually (health, me, import) and note that tailoring was not exercised live. Stop the app services afterwards with `docker compose stop api worker` (leave db and redis for the tests).

- [ ] **Step 6: Full verification and commit**

```bash
cd apps/api && uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run lint-imports
cd ../.. && bash scripts/codegen.sh && git diff --exit-code apps/api/src/rhapto/models
uv run --project apps/api python scripts/check-no-personal-data.py
git add apps/api/Dockerfile apps/api/.importlinter docker-compose.yml README.md .dockerignore scripts/smoke-api.sh
git commit -m "build: api and worker images, full compose stack, layering contracts, backend README, smoke script"
```

---

## Self-review notes

- Spec coverage: section 6 tables (Task 1; `scores` deferred to 0.3 as the spec says), section 7 endpoints (Tasks 5 to 11: profile, jobs, tailoring with SSE, packages, applications, meta), section 8 worker tasks and progress relay (Tasks 3, 8, 9), section 10 compose and images (Tasks 1, 12), section 11 API tests against a real Postgres with inline tasks and fakes (every task), CLI `profile import/export` and `db upgrade` (Task 2).
- Deviations from the spec recorded here: profile tables reference each other by profile-level string ids rather than UUID foreign keys (keeps YAML round-trips exact); `packages` gains `selection_block_ids` and `jd_extract_json` so edits can be re-validated without the engine's selection step; `applications` enforces one application per job; URL intake uses trafilatura with a tag-stripping fallback.
- Type consistency: `run_guardrails(resume, profile, selection_ids, extract, cover_note=None)` matches the stage 1 final fix wave; `TaskFn = Callable[..., Awaitable[None]]` is shared by `enqueue.py` and `worker/tasks.py`; `PackageStorage.path_for` takes the `FileName` Literal; `JobOut.latest_package` uses `PackageSummary` defined in Task 7 and reused by Task 9's test.
