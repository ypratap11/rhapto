# Multi-tenancy Phase A+B Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship request-scoped identity, Cloudflare Access authentication behind an invite allowlist,
a same-origin proxy, per-user poll fan-out, and a synchronous first-screen backfill (Phase A) —
followed by account deletion and a bounded-retention backup regime (Phase B) — so the owner's wife
can be invited onto the running single-tenant instance without losing, corrupting, or exposing the
owner's existing data, and without breaking the box's memory/timeout budget.

**Architecture:** `current_user`'s external contract (`Depends(current_user) -> uuid.UUID`) never
changes, so no router is touched. A `Principal` type and `resolve_principal` dependency sit
underneath it and are the only thing that changes shape between `token` mode (today's single bearer
secret, preserved byte-for-byte) and `access` mode (Cloudflare Access JWT, verified against a
last-good-cached JWKS, checked against a two-layer invite allowlist). No `jobs` schema change is
needed for Phase A or B — every table is already correctly `user_id`-scoped since migration `0010`.
The first screen is filled by a single synchronous `INSERT ... SELECT` row copy on account creation,
never by a poll. Account deletion is files-before-rows, and backups get a real retention bound.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 async, Alembic, Postgres 16 + pgvector, arq
(Redis-backed task queue), Next.js (App Router) + TypeScript, `PyJWT` (new dependency, RS256 via the
already-present `cryptography` package), Typer CLI.

**Spec:**
- `.superpowers/sdd/multi-tenancy/architecture.md` (APPROVED WITH CONDITIONS)
- `.superpowers/sdd/multi-tenancy/functional-spec.md` (16 acceptance criteria, AC 1/2 amended
  "within the invited set")
- `CLAUDE.md` (non-negotiable product rules, working agreement, delivery pipeline)

## Global Constraints

- **Scope is Phase A (A1–A5) and Phase B (B1–B2) only.** Phase C (the `postings` split) is out of
  scope and no task below plans, previews, or depends on it.
- **Alembic head is `0010_tenancy_unique_constraints`.** The one new migration in this plan is
  numbered `0011`.
- **Every task leaves `pytest`, `ruff check .`, and `mypy src` (run from `apps/api`) clean, and — for
  any task touching `apps/web` — `pnpm test`, `pnpm lint`, and `pnpm typecheck` (run from
  `apps/web`) clean.** No task may be merged red. If a change cannot be made green in one task, it is
  split expand/migrate/contract and the split is stated in the task.
- **`token` mode's observable behaviour is preserved byte-for-byte**: same `secrets.compare_digest`
  comparison, same 401 detail string `"missing or invalid bearer token"`, same `WWW-Authenticate:
  Bearer` header, same 503 `"server not ready"` before bootstrap completes, same response bodies. This
  is a constraint on *responses*, not on "zero additional internal statements" — Task 6's `mark_seen`
  necessarily adds one atomic `UPDATE` to every authenticated request in both modes; it is written as
  a single statement with no preceding `SELECT` specifically so it stays cheap and does not change the
  `select_counter` budget any endpoint is tested against (verified: `apps/api/tests/api/test_dashboard_api.py:152`
  asserts `len(select_counter) <= 8` for the dashboard request). The existing tests
  `test_me_requires_bearer`, `test_me_rejects_wrong_token`, `test_me_returns_user`, and
  `test_me_is_503_when_the_user_is_not_bootstrapped_yet` (`apps/api/tests/api/test_meta.py`) must pass
  **unmodified**.
- **A5's backfill selects on a positive allowlist of public source ids**, supplied by its caller as
  `list(SOURCES.keys())` from `rhapto.services.discovery.sources.SOURCES` — **never** `source <>
  'manual'` or any other denylist, and the repository function itself takes no dependency on the
  `services.discovery` package (see Task 5, fixing plan-review finding I10). It must not copy
  `extracted_json`, `repost_of`, `search_id`, `best_fit`, `best_track_id`, `location_tier`,
  `hidden_at`, or `rescued`, and it must respect the existing partial unique index
  `uq_jobs_user_source_external` on `(user_id, source, external_id) WHERE external_id IS NOT NULL`
  (`apps/api/alembic/versions/0002_discovery.py:33-40`) — verified in this revision after the prior
  version of this plan missed it (plan-review finding C5).
- **The A5 seed (backfill + marking `users.seeded_at`) never runs inside `current_user`.** It is a
  separately-committed, idempotent step triggered by a dedicated endpoint the web app calls once per
  session (plan-review finding C6): `current_user` must stay fast and side-effect-light, because every
  endpoint depends on it, and a failure inside it is indistinguishable from an auth failure.
- **Migration `0011` adds four columns to `users`**, not three: `idp_subject`, `last_seen_at`,
  `exempt_from_pruning`, and `seeded_at` (nullable, `NULL` until Task 5's seed step sets it). Keeping
  all four in one migration avoids a second migration number for Task 5's marker column.
- **`RHAPTO_USER_EMAIL` must equal the owner's Cloudflare Access email before `access` mode is
  enabled**, enforced by a startup assertion and verified by a `GET /api/v1/me` comparison in the
  deploy runbook.
- **Deletion removes package files from disk before deleting rows**, and the daily prune cron and
  CLI delete path never touch another account's rows (enforced by the `ON DELETE CASCADE` FKs already
  on every `UserScopedMixin` table, verified in `apps/api/src/rhapto/db/base.py:27-30` — nothing here
  is shared between accounts in Phase A/B, since `postings` does not exist yet).
- **The 90-day deletion promise is published with its true bound** — "deleted within 90 days of
  inactivity, and gone from every backup within a further 14 days" — never a flat "90 days".
- **No placeholders.** Every code step below is real code against the file and line numbers verified
  in this session; every test body is a complete, runnable test.
- **Model/effort note (per `CLAUDE.md`'s delivery pipeline):** this decomposition was produced by the
  senior developer role at a mid-tier model; implementation (role 4) should run on the cheapest model
  that fits each task, named explicitly in that role's report.

---

## Task 1 (A1): `Principal`, `resolve_principal`, and migration `0011`

Introduces the identity abstraction underneath `current_user` without changing `current_user`'s
external contract (`Depends(current_user) -> uuid.UUID`), so no router changes. `token` mode is
re-expressed on top of `Principal` with byte-identical behaviour. `access` mode's real verification
arrives in Task 3; here it is a real, working 501 stub — not a placeholder, a defined behaviour for a
mode that is not yet reachable (the default is `token` and no deployment can select `access` before
Task 3 ships).

Verified before writing this task: `apps/api/src/rhapto/api/deps.py:74-94` (current `current_user`,
using `secrets.compare_digest`, the exact 401 body, and the 503-when-`state.user_id is None` check);
`apps/api/src/rhapto/api/app.py:72-78` (lifespan calls `get_or_create_user(session,
settings.rhapto_user_email)` and sets `state.user_id`); `apps/api/src/rhapto/config.py` (current
`Settings` fields); `apps/api/src/rhapto/db/models.py:35-39` (`User` has no `idp_subject` or
`last_seen_at` yet); `apps/api/alembic/versions/0010_tenancy_unique_constraints.py` (head, confirms
`0011` is the next free revision); `apps/api/tests/api/test_meta.py` (the four tests this task must
not change).

**Files:**
- Create: `apps/api/src/rhapto/api/auth.py`
- Create: `apps/api/alembic/versions/0011_user_lifecycle_columns.py`
- Modify: `apps/api/src/rhapto/api/deps.py` (`current_user`)
- Modify: `apps/api/src/rhapto/config.py` (add `rhapto_auth_mode`)
- Modify: `apps/api/src/rhapto/db/models.py` (`User` gains four columns)
- Modify: `apps/api/src/rhapto/api/schemas.py` (`MeOut.auth_mode`)
- Modify: `apps/api/src/rhapto/api/routers/meta.py` (`me()` returns `auth_mode`)
- Modify: `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts` (regenerated, Step 11)
- Modify: `apps/web/src/components/jobs/TailorButton.test.tsx` (two `MeOut` literals gain `auth_mode`
  — re-review finding 1, `pnpm typecheck` would otherwise fail)
- Test: `apps/api/tests/api/test_auth_principal.py`
- Test: `apps/api/tests/db/test_migrations_0011.py`
- Test: `apps/api/tests/api/test_meta.py` (extend, one new test)

**Interfaces:**
- Consumes: `AppState` (defined in `apps/api/src/rhapto/api/deps.py`: `settings`, `user_id:
  uuid.UUID | None`, unchanged), accessed by `auth.py` via `request.app.state.rhapto` directly — not
  via `deps.get_state`, to avoid the circular import described in Step 7 (plan-review C1).
- Produces (for Task 3 and Task 6 to build on):
  ```python
  # rhapto/api/auth.py
  from typing import Literal
  AuthMode = Literal["token", "access"]

  @dataclass(frozen=True)
  class Principal:
      mode: AuthMode
      subject: str   # "token" in token mode; the IdP `sub` in access mode (Task 3)
      email: str     # casefolded identity key

  async def resolve_principal(
      request: Request, authorization: Annotated[str | None, Header()] = None
  ) -> Principal: ...
  ```
  `current_user`'s signature remains `async def current_user(...) -> uuid.UUID`, still injectable via
  `Depends(current_user)` with no change at any call site (`UserDep = Annotated[uuid.UUID,
  Depends(current_user)]`, defined per-router, e.g. `apps/api/src/rhapto/api/routers/jobs.py:28`).
  `Settings.rhapto_auth_mode: AuthMode = "token"` (new field, Task 3 adds `rhapto_access_team`,
  `rhapto_access_aud`, `rhapto_allowed_emails`, `rhapto_allowed_email_domains`; Task 6 adds
  `rhapto_inactive_days`). `MeOut.auth_mode: Literal["token", "access"]` (new field, consumed by
  Task 2's `TokenGate`). `User.idp_subject: str | None`, `User.seeded_at: datetime | None` (not read
  until Task 5), `User.last_seen_at: datetime` (not read by
  any code until Task 6), `User.exempt_from_pruning: bool` (not read until Task 7).

- [ ] **Step 1: Write the failing migration test**

```python
# apps/api/tests/db/test_migrations_0011.py
from __future__ import annotations

import os
import uuid

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from rhapto.db.session import make_engine


async def test_0011_adds_user_lifecycle_columns(engine: AsyncEngine) -> None:
    def inspect_users(sync_conn):
        cols = {c["name"] for c in inspect(sync_conn).get_columns("users")}
        uniques = {
            tuple(sorted(u["column_names"]))
            for u in inspect(sync_conn).get_unique_constraints("users")
        }
        return cols, uniques

    async with engine.connect() as conn:
        cols, uniques = await conn.run_sync(inspect_users)
    assert {"idp_subject", "last_seen_at", "exempt_from_pruning", "seeded_at"} <= cols
    assert ("idp_subject",) in uniques


async def test_0011_backfills_seeded_at_for_pre_existing_rows() -> None:
    """This is the specific assertion that stops Task 5's bootstrap endpoint from running a
    backfill over the owner's live account: migration 0011 must not just add `seeded_at`, it must
    stamp every row that existed before it ran, so `seeded_at IS NULL` never means "the owner,
    pre-migration" -- only "a genuinely new account". The shared `migrated_db` fixture upgrades
    straight to head and can't exercise "insert a row, then run 0011", so this test drives Alembic
    against its own scratch database: create it, upgrade to 0010, insert a row directly, upgrade to
    0011, assert its seeded_at is no longer NULL, then drop the scratch database. Verified against
    the actual migration file, not assumed: `0011_user_lifecycle_columns.py`'s `upgrade()` ends with
    exactly `UPDATE users SET seeded_at = now() WHERE seeded_at IS NULL` (Step 3, this task).
    """
    import asyncpg

    from alembic.config import Config

    from alembic import command

    base_url = os.environ.get("RHAPTO_TEST_DATABASE_URL", DEFAULT_TEST_URL)
    admin_dsn = _dsn(base_url).rsplit("/", 1)[0] + "/postgres"
    scratch_name = f"rhapto_test_0011_backfill_{uuid.uuid4().hex[:8]}"
    scratch_url_asyncpg = _dsn(base_url).rsplit("/", 1)[0] + f"/{scratch_name}"
    scratch_url = base_url.rsplit("/", 1)[0] + f"/{scratch_name}"

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{scratch_name}"')
    finally:
        await admin.close()

    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        os.environ["DATABASE_URL"] = scratch_url
        command.upgrade(cfg, "0010")

        scratch_engine = make_engine(scratch_url)
        pre_existing_id = uuid.uuid4()
        try:
            async with scratch_engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO users (id, email, settings_json, created_at, updated_at) "
                        "VALUES (:id, :email, '{}'::jsonb, now(), now())"
                    ),
                    {"id": str(pre_existing_id), "email": "owner-pre-0011@example.com"},
                )
            command.upgrade(cfg, "0011")
            async with scratch_engine.connect() as conn:
                row = (
                    await conn.execute(
                        text("SELECT seeded_at FROM users WHERE id = :id"),
                        {"id": str(pre_existing_id)},
                    )
                ).first()
            assert row is not None
            assert row[0] is not None
        finally:
            await scratch_engine.dispose()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{scratch_name}" WITH (FORCE)')
        finally:
            await admin.close()
        os.environ["DATABASE_URL"] = _dsn(base_url).replace("postgresql://", "postgresql+asyncpg://")
```

`_dsn` and `DEFAULT_TEST_URL` mirror the helpers already in `apps/api/tests/conftest.py` (same
`postgresql+asyncpg://` ↔ `postgresql://` conversion, same env var); import them from there
(`from conftest import _dsn, DEFAULT_TEST_URL`) rather than duplicating the logic, if the test
runner's import layout allows it — `apps/api/tests/` has no top-level package `__init__.py`
(verified), so `tests/db/` importing a name from the root `tests/conftest.py` module needs
`pythonpath = ["tests", "tests/unit"]` (already set in `pyproject.toml`) to resolve `conftest` as a
bare module; confirm this resolves before relying on it, and inline the two-line helpers locally in
this test file otherwise.

- [ ] **Step 2: Run it to see it fail**

Run (from `apps/api`): `pytest tests/db/test_migrations_0011.py -v`
Expected: FAIL on both tests — `migrated_db` fixture upgrades to `head`, which is still `0010`, so
`test_0011_adds_user_lifecycle_columns`'s columns don't exist; `test_0011_backfills_seeded_at_for_pre_existing_rows`
fails at `command.upgrade(cfg, "0010")` finding no such revision file, or at the later `0011` upgrade
finding no `seeded_at` column to select (or `command.upgrade` errors outright if the migration file
is entirely absent — either way, not a pass).

- [ ] **Step 3: Write the migration**

```python
# apps/api/alembic/versions/0011_user_lifecycle_columns.py
"""user lifecycle columns: idp_subject, last_seen_at, exempt_from_pruning, seeded_at

Revision ID: 0011
Revises: 0010

Four additive columns on `users`, needed by Phase A identity (`idp_subject`, looked up by A3's
access-mode principal resolution — never used as the lookup key, `email` is, because Access can
reissue a `sub` across an IdP change while the email stays stable; `seeded_at`, Task 5's idempotency
marker for the first-screen backfill) and Phase B lifecycle (`last_seen_at`, `exempt_from_pruning`,
not read by any code until Task 6/7). Bundled into one migration because they are all additive,
metadata-only changes to the same table, and the architecture places the first three together;
`seeded_at` rides along rather than opening a second migration for one nullable column.

`last_seen_at` defaults to `now()`, which backfills every existing row (the owner's account) to "seen
now" -- correct, not a bug: it grants a fresh 90 days from the moment this migration runs, rather than
making the owner's account eligible for pruning on day one.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("idp_subject", sa.Text(), nullable=True))
    op.create_unique_constraint("uq_users_idp_subject", "users", ["idp_subject"])
    op.add_column(
        "users",
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "exempt_from_pruning",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("users", sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=True))
    # Fixes re-review finding 5: without this, every pre-existing row (the owner's account, on
    # this branch) has seeded_at IS NULL, and Task 5's POST /me/bootstrap treats NULL as "not yet
    # seeded" -- so the owner's first authenticated request after this migration would run
    # backfill_public_jobs *against his own account*, an unplanned write to exactly the data AC 15
    # exists to protect. Backfilling every existing row to "already seeded" is correct: an
    # already-populated account has nothing this backfill would add anyway.
    op.execute("UPDATE users SET seeded_at = now() WHERE seeded_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "seeded_at")
    op.drop_column("users", "exempt_from_pruning")
    op.drop_column("users", "last_seen_at")
    op.drop_constraint("uq_users_idp_subject", "users", type_="unique")
    op.drop_column("users", "idp_subject")
```

(Hygiene, not a code change: `apps/api/alembic/versions/__pycache__/0010_shared_job_pool.cpython-312.pyc`
is a stale compiled artifact from the abandoned shared-job-pool branch. Alembic reads `.py` files only,
so it is harmless, but delete it in this task's commit for cleanliness: `git rm --cached
apps/api/alembic/versions/__pycache__/0010_shared_job_pool.cpython-312.pyc` if tracked, or a plain
`rm` if it is untracked build output.)

- [ ] **Step 4: Run the migration test again**

Run: `pytest tests/db/test_migrations_0011.py -v`
Expected: both `test_0011_adds_user_lifecycle_columns` and
`test_0011_backfills_seeded_at_for_pre_existing_rows` PASS.

- [ ] **Step 5: Add the columns to the ORM model**

```python
# apps/api/src/rhapto/db/models.py — in class User (currently lines 35-39)
class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("idp_subject", name="uq_users_idp_subject"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    idp_subject: Mapped[str | None] = mapped_column(Text)
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    exempt_from_pruning: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    seeded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

- [ ] **Step 6: Add `rhapto_auth_mode` to `Settings`**

```python
# apps/api/src/rhapto/config.py — inside class Settings, after rhapto_user_email
from typing import Literal
AuthMode = Literal["token", "access"]
...
    rhapto_auth_mode: AuthMode = "token"
```

- [ ] **Step 7: Write `rhapto/api/auth.py` — with no runtime import of `deps.py`**

**Fixes plan-review finding C1** (a prior version of this task made `auth.py` import `get_state` from
`deps.py` at module level while `deps.py` imported `Principal`/`resolve_principal` from `auth.py` at
module level — a circular import, verified: `get_state` is defined at
`apps/api/src/rhapto/api/deps.py:40`, so whichever module imports first hits an unbound name in the
other. Fix (the reviewer's "cheaper alternative"): `auth.py` never imports anything from `deps.py` at
runtime. It reads `request.app.state.rhapto` directly — the same attribute `get_state` reads
(`apps/api/src/rhapto/api/app.py:99`: `app.state.rhapto = state`) — and only imports the `AppState`
*type* under `TYPE_CHECKING`, which mypy sees but Python never executes. `deps.py` keeps importing
`Principal`/`resolve_principal` from `auth.py` normally; the dependency is now one-directional.

```python
# apps/api/src/rhapto/api/auth.py
from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Literal

from fastapi import Header, HTTPException, Request

if TYPE_CHECKING:
    from rhapto.api.deps import AppState

AuthMode = Literal["token", "access"]


def _state(request: Request) -> AppState:
    """Reads the same `request.app.state.rhapto` attribute `deps.get_state` reads, without
    importing `deps.py` (which imports this module) — see the C1 fix note above."""
    return request.app.state.rhapto  # type: ignore[no-any-return]


@dataclass(frozen=True)
class Principal:
    """Who made this request, resolved before `current_user` maps it to a `users.id`.

    `subject` is the literal string "token" in token mode (there is no per-request subject, only
    the one instance secret) and the IdP `sub` claim in access mode (Task 3). `email` is always
    casefolded and is the identity key in both modes.
    """

    mode: AuthMode
    subject: str
    email: str


async def resolve_principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    state = _state(request)
    mode = state.settings.rhapto_auth_mode
    if mode == "access":
        # Task 3 replaces this branch with real Cloudflare Access JWT verification, the JWKS
        # cache, and the allowlist check. Unreachable today: the default is "token" and no
        # deployment can select "access" before Task 3 ships.
        raise HTTPException(status_code=501, detail="access mode is not yet supported")
    expected = state.settings.rhapto_api_token
    provided = (
        authorization.removeprefix("Bearer ").strip()
        if authorization and authorization.startswith("Bearer ")
        else None
    )
    if not expected or not secrets.compare_digest(provided or "", expected):
        raise HTTPException(
            status_code=401,
            detail="missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Principal(mode="token", subject="token", email=state.settings.rhapto_user_email.casefold())
```

- [ ] **Step 8: Re-express `current_user` on top of `resolve_principal`**

```python
# apps/api/src/rhapto/api/deps.py — replace the current_user function (lines 74-94)
from rhapto.api.auth import Principal, resolve_principal  # add to imports


async def current_user(
    request: Request,
    principal: Annotated[Principal, Depends(resolve_principal)],
) -> uuid.UUID:
    state = get_state(request)
    if principal.mode == "token":
        if state.user_id is None:
            # The lifespan bootstraps the user row; a request that beats it is a readiness
            # problem, not an auth problem.
            raise HTTPException(status_code=503, detail="server not ready")
        return state.user_id
    # access mode: Task 3 maps principal.email to a users.id (get-or-create on first sign-in).
    raise HTTPException(status_code=501, detail="access mode is not yet supported")
```

Add `from fastapi import Depends` to `deps.py`'s imports if not already present (it is not, per the
file read in this session — only `Header`, `HTTPException`, `Request` are imported from `fastapi`
today).

- [ ] **Step 9: Write the new-behaviour test**

```python
# apps/api/tests/api/test_auth_principal.py
from __future__ import annotations

import httpx
from fastapi import FastAPI

from rhapto.api.deps import AppState


async def test_principal_email_is_the_owner_email_in_token_mode(client: httpx.AsyncClient) -> None:
    """token mode's Principal carries the bootstrapped owner's email, casefolded."""
    response = await client.get("/api/v1/me")
    assert response.status_code == 200
    assert response.json()["email"] == "test@example.com"


async def test_access_mode_is_a_defined_501_not_a_crash(
    app: FastAPI, anon_client: httpx.AsyncClient
) -> None:
    # Settings is a pydantic BaseSettings with neither frozen=True nor validate_assignment set
    # (verified: Settings.model_config = SettingsConfigDict(env_file=".env", extra="ignore"),
    # config.py:12), so plain attribute assignment on an already-constructed instance works —
    # no object.__setattr__ needed. Both `app`/`api_settings` are function-scoped fixtures
    # (tests/api/conftest.py:109,145), so this mutation never leaks into another test.
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    response = await anon_client.get("/api/v1/me")
    assert response.status_code == 501
```

- [ ] **Step 10: Add `auth_mode` to `MeOut`, so `TokenGate` (Task 2) can tell the two modes apart**

**Fixes plan-review finding C3** (Task 2's part). Verified `MeOut` today
(`apps/api/src/rhapto/api/schemas.py:21-26`) has no `auth_mode` field, and `architecture.md` §6 names
this as the mechanism the web app needs. Adding it here, in Task 1, rather than in Task 2, because it
depends only on `Settings.rhapto_auth_mode` (already added in this task) and has a stable, correct
value (`"token"`) from the moment this task ships — Task 3 does not need to touch it again.

```python
# apps/api/src/rhapto/api/schemas.py — MeOut
class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID
    llm_configured: bool
    auth_mode: Literal["token", "access"]
```

```python
# apps/api/src/rhapto/api/routers/meta.py — the me() handler's return
    return MeOut(
        email=user.email,
        user_id=user.id,
        llm_configured=await is_llm_configured(session, settings, user_id),
        auth_mode=settings.rhapto_auth_mode,
    )
```

Add `test_me_returns_the_auth_mode` to `apps/api/tests/api/test_meta.py`:

```python
async def test_me_returns_the_auth_mode(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/me")
    assert response.json()["auth_mode"] == "token"
```

This is additive to `MeOut` and does not change any of the four byte-for-byte tests listed in Global
Constraints (none of them asserts the full response body, only `status_code` and the fields it names).

- [ ] **Step 11: Regenerate the OpenAPI document and the web client's generated types**

Run (from `apps/api`): `python scripts/export_openapi.py` — writes
`packages/schemas/openapi.json` with `MeOut.auth_mode` included.
Run (from `apps/web`): `pnpm gen:api` — regenerates `src/lib/api/schema.d.ts` from that document.
Both files are committed as part of this task (Step 14), so `apps/web`'s `MeOut` type (re-exported at
`apps/web/src/lib/api/queries.ts:37`, `export type MeOut = Schemas["MeOut"]`) picks up `auth_mode`
before Task 2 needs it.

**Fixes re-review breakage item 1 — `MeOut` becoming stricter breaks `apps/web`'s typecheck.**
`apps/web/src/components/jobs/TailorButton.test.tsx:16` declares `let meData: MeOut | undefined`, and
two literals build it without the new field: line 72
(`meData = { user_id: "u1", email: "dev@example.com", llm_configured: true }`) and line 245 (the same
shape with `llm_configured: false`). `apps/web/tsconfig.json` includes `**/*.tsx` and excludes only
`node_modules`, so `pnpm typecheck` type-checks test files too — once `auth_mode` is required, both
literals fail `tsc --noEmit`. Fix both in this task:

```typescript
// apps/web/src/components/jobs/TailorButton.test.tsx:72 and :245 — add auth_mode to both literals
meData = { user_id: "u1", email: "dev@example.com", llm_configured: true, auth_mode: "token" };
// ...and, at line 245:
meData = { user_id: "u1", email: "dev@example.com", llm_configured: false, auth_mode: "token" };
```

(Task 6 adds `deletion_due_at` to `MeOut` and must extend these same two literals again — noted in
Task 6's own steps.)

- [ ] **Step 12: Run the full existing auth suite plus the new tests**

Run: `pytest tests/api/test_meta.py tests/api/test_auth_principal.py -v`
Expected: all of `test_health_is_public`, `test_me_requires_bearer`, `test_me_rejects_wrong_token`,
`test_me_returns_user`, `test_me_is_503_when_the_user_is_not_bootstrapped_yet`,
`test_unknown_route_is_problem_json`, `test_openapi_served`, `test_me_returns_the_auth_mode`, plus the
two new auth-principal tests — PASS, with the four listed-in-Global-Constraints tests **unmodified
from git history**.

- [ ] **Step 13: Full local verification**

Run: `pytest` (from `apps/api`) — expect the full suite green (baseline plus the new tests).
Run: `ruff check .` — expect no findings.
Run: `mypy src` — expect no errors (the `Principal` dataclass and `resolve_principal` are fully
typed; `Annotated[Principal, Depends(resolve_principal)]` matches the pattern
`Annotated[uuid.UUID, Depends(current_user)]` already used throughout the routers; `_state`'s
`# type: ignore[no-any-return]` is the only suppressed check in this task, scoped to the one line
that reads an untyped `Starlette` `State` attribute).
Run (from `apps/web`): `pnpm typecheck` — expect green, including `TailorButton.test.tsx` after
Step 11's two-literal fix. This task commits `schema.d.ts`, so this is the first task where an
`apps/web` typecheck is part of its own gate, not just a later web-touching task's.

- [ ] **Step 14: Commit**

```bash
git add apps/api/src/rhapto/api/auth.py apps/api/src/rhapto/api/deps.py \
  apps/api/src/rhapto/config.py apps/api/src/rhapto/db/models.py \
  apps/api/src/rhapto/api/schemas.py apps/api/src/rhapto/api/routers/meta.py \
  apps/api/alembic/versions/0011_user_lifecycle_columns.py \
  packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts \
  apps/web/src/components/jobs/TailorButton.test.tsx \
  apps/api/tests/api/test_auth_principal.py apps/api/tests/api/test_meta.py \
  apps/api/tests/db/test_migrations_0011.py
git commit -m "$(cat <<'EOF'
Introduce Principal/resolve_principal under current_user (A1)

current_user's external contract (Depends(current_user) -> uuid.UUID) is unchanged, so no router
is touched. token mode is re-expressed on top of the new Principal type with byte-identical
behaviour (same compare_digest check, same 401/503 bodies). access mode is a defined 501 stub,
replaced by Task 3. auth.py reads request.app.state.rhapto directly instead of importing deps.get_state,
so the two modules do not import each other (plan-review C1). Migration 0011 adds users.idp_subject,
users.last_seen_at, users.exempt_from_pruning and users.seeded_at -- additive, and backfills
seeded_at on every pre-existing row so Task 5's bootstrap endpoint never runs against the owner's
own account (re-review finding 5). MeOut gains auth_mode so the web app (Task 2) can tell modes
apart; TailorButton.test.tsx's two MeOut literals updated so apps/web's typecheck stays green
(re-review finding 1).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 6 (identity is the mechanism every per-account scope depends on),
11 (foundation for A2's session separation), 15 (migration is purely additive; `RHAPTO_USER_EMAIL`
bootstrap path in `app.py` is untouched by this task).

---

## Task 2 (A2): Same-origin Next.js proxy, CORS gated by mode, `TokenGate` unlocks in access mode

This task's scope changed substantially from the version plan review rejected. Three fixes, in order
of how they were found:

- **C2 — `NEXT_PUBLIC_API_URL=""` never produced a same-origin client.** Verified:
  `apps/web/src/lib/api/client.ts:5`, `process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000"` — `""` is falsy, so it silently fell through to the localhost default. The
  same bug is repeated in `getSettings()` (`client.ts:53` area) for the stored `rhapto.apiUrl`. Fixed
  in Step 1-4 below by distinguishing "unset" from "explicitly empty".
- **C3 — `TokenGate` gated every route on a `localStorage` bearer token that access-mode users never
  have.** Verified: `apps/web/src/components/shell/TokenGate.tsx:22-24,32-41` — `hasToken()` is the
  only signal it reads. An invited person authenticated by Cloudflare would see the landing page or
  the "Connect to your Rhapto API" card forever. Fixed in Steps 12-13 by making `TokenGate` unlock on
  `useMe()` succeeding when the deployment is same-origin (access mode), and leaving the existing
  token-mode gate untouched otherwise.
- **I4 — the planned `localStorage` namespacing targeted dead code.** Verified: `apps/web/src/lib/skipped.ts`
  has no callers anywhere in `apps/web/src` outside its own test (`grep -rn
  "readSkipped|skipJob|unskipAll|useSkipped" apps/web/src` matches only `skipped.ts` and
  `skipped.test.ts`) — `NotInterestedButton.tsx` uses the server-side `useHideJob`/`useUnhideJob`
  mutations instead. The only *live* per-item `localStorage` state is
  `apps/web/src/lib/apply-prompt.ts` (`APPLY_OPENED_PREFIX = "rhapto.apply-opened."`, keyed by raw
  job id) — but a job id is a per-row UUID (`Job.id`, `db/models.py:166`) that is never shared between
  two accounts' rows (each account's `jobs` rows, including A5's backfilled ones, get their own fresh
  `gen_random_uuid()`), and the UI only ever renders the current account's own job ids (every job
  query is scoped by `user_id` in `db/repositories/jobs.py`). So a second person sharing a browser can
  never see or trigger the first person's `apply-opened` entry — there is no id to collide on. **This
  plan does not namespace any `localStorage` key.** `rhapto.token`/`rhapto.apiUrl` are meaningless in
  access mode (no token is ever stored there — see the `TokenGate` fix), and `rhapto.theme`
  (`apps/web/src/components/ui/theme-toggle.tsx`) is a cosmetic preference, not account data. AC 11's
  "no shared or leaked session state" is satisfied because access mode stores no identity-bearing
  state in `localStorage` at all, not because keys are namespaced — a stronger property, verified
  rather than assumed.

Also verified before writing this task: `apps/api/src/rhapto/api/app.py:100-106` (CORS middleware
installed unconditionally, `allow_credentials=False`); `apps/web/src/lib/api/sse.ts` (the streaming
`fetch` reader, `response.body.getReader()`, never `await response.text()`); no
`apps/web/src/app/api/**/route.ts` exists today (verified by directory listing) — the proxy route is
new; `apps/web/src/lib/api/queries.ts:79`, `export function useMe() { return useQuery({ queryKey:
keys.me, queryFn: () => unwrap(apiClient().GET("/api/v1/me")) }); }`. `apps/web/AGENTS.md` warns this
checkout's Next.js has breaking changes from training-data Next.js; the coder must read the Route
Handlers and streaming-response docs under `apps/web/node_modules/next/dist/docs/` before writing
`route.ts`, rather than assuming a textbook App Router API.

**Files:**
- Create: `apps/web/src/app/api/v1/[...path]/route.ts`
- Modify: `apps/api/src/rhapto/api/app.py` (gate `CORSMiddleware` by `rhapto_auth_mode`)
- Modify: `apps/web/src/lib/api/client.ts` (fix `DEFAULT_API_URL`/`getSettings` empty-string
  handling; add `SAME_ORIGIN_DEPLOYMENT`)
- Modify: `apps/web/src/components/shell/TokenGate.tsx` (unlock via `useMe()` in access mode)
- Test: `apps/api/tests/api/test_cors_mode.py`
- Test: `apps/web/src/app/api/v1/[...path]/route.test.ts`
- Test: `apps/web/src/lib/api/client.test.ts` (extend existing file)
- Test: `apps/web/src/components/shell/TokenGate.test.tsx` (extend existing file)

**Interfaces:**
- Consumes: `Settings.rhapto_auth_mode` (Task 1), `MeOut.auth_mode` (Task 1) indirectly — `TokenGate`
  does not read `auth_mode` itself; it reads the build-time `SAME_ORIGIN_DEPLOYMENT` sentinel (which a
  same-origin deployment sets by leaving `NEXT_PUBLIC_API_URL=""`) and `useMe()`'s success/failure,
  which is a cheaper, equally correct signal available before any request completes.
- Produces: `SAME_ORIGIN_DEPLOYMENT: boolean` and a fixed `DEFAULT_API_URL`/`getSettings()` in
  `apps/web/src/lib/api/client.ts`. No other task in this plan consumes either directly.

- [ ] **Step 1: Write the failing test for the empty-string fallback bug**

```typescript
// apps/web/src/lib/api/client.test.ts — append
import { afterEach, describe, expect, it, vi } from "vitest";

describe("DEFAULT_API_URL / SAME_ORIGIN_DEPLOYMENT", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("treats an explicitly empty NEXT_PUBLIC_API_URL as same-origin, not the localhost fallback", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    vi.resetModules();
    const mod = await import("./client");
    expect(mod.DEFAULT_API_URL).toBe("");
    expect(mod.SAME_ORIGIN_DEPLOYMENT).toBe(true);
  });

  it("falls back to localhost only when NEXT_PUBLIC_API_URL is truly unset", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", undefined);
    vi.resetModules();
    const mod = await import("./client");
    expect(mod.DEFAULT_API_URL).toBe("http://localhost:8000");
    expect(mod.SAME_ORIGIN_DEPLOYMENT).toBe(false);
  });
});
```

- [ ] **Step 2: Run it to see it fail**

Run: `pnpm test client.test.ts` (from `apps/web`)
Expected: FAIL — today `DEFAULT_API_URL` is `"http://localhost:8000"` in both cases, and
`SAME_ORIGIN_DEPLOYMENT` does not exist.

- [ ] **Step 3: Fix the fallback and add the sentinel**

```typescript
// apps/web/src/lib/api/client.ts — replace line 5, add SAME_ORIGIN_DEPLOYMENT
export const SAME_ORIGIN_DEPLOYMENT = process.env.NEXT_PUBLIC_API_URL === "";

export const DEFAULT_API_URL =
  process.env.NEXT_PUBLIC_API_URL === undefined
    ? "http://localhost:8000"
    : process.env.NEXT_PUBLIC_API_URL.replace(/\/+$/, "");
```

```typescript
// apps/web/src/lib/api/client.ts — replace getSettings (the same || bug on the stored value)
export function getSettings(): ConnectionSettings {
  const s = storage();
  const storedApiUrl = s?.getItem(STORAGE_KEYS.apiUrl);
  const apiUrl = (storedApiUrl !== null && storedApiUrl !== undefined ? storedApiUrl : DEFAULT_API_URL).replace(
    /\/+$/,
    "",
  );
  return { token: s?.getItem(STORAGE_KEYS.token) ?? "", apiUrl };
}
```

- [ ] **Step 4: Run the tests again, then the existing client tests**

Run: `pnpm test client.test.ts` (from `apps/web`)
Expected: PASS, including every pre-existing test in this file (none of them sets
`NEXT_PUBLIC_API_URL="")`, so `DEFAULT_API_URL`'s value in those tests is unchanged).

- [ ] **Step 5: Write the failing API test for CORS gating**

```python
# apps/api/tests/api/test_cors_mode.py
from __future__ import annotations

import httpx

from rhapto.api.app import create_app
from rhapto.config import Settings


async def test_cors_is_installed_in_token_mode(api_settings: Settings, session_factory, storage) -> None:
    api_settings.rhapto_auth_mode = "token"
    app = create_app(api_settings, session_factory=session_factory, storage=storage)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"


async def test_cors_is_absent_in_access_mode(api_settings: Settings, session_factory, storage) -> None:
    api_settings.rhapto_auth_mode = "access"
    app = create_app(api_settings, session_factory=session_factory, storage=storage)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert "access-control-allow-origin" not in response.headers
```

`api_settings` and `session_factory`/`storage` fixtures already exist in
`apps/api/tests/api/conftest.py` / `apps/api/tests/conftest.py`; this test constructs its own `app`
directly (rather than using the `app` fixture) because it needs two different `rhapto_auth_mode`
values, and `create_app` is already parameterised the way the `app` fixture calls it.

- [ ] **Step 6: Run it to see it fail**

Run: `pytest tests/api/test_cors_mode.py -v`
Expected: FAIL on `test_cors_is_absent_in_access_mode` — today's `app.py` installs `CORSMiddleware`
unconditionally, so the header is present regardless of mode.

- [ ] **Step 7: Gate the middleware by mode**

```python
# apps/api/src/rhapto/api/app.py — replace lines 100-106
    if settings.rhapto_auth_mode == "token":
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.rhapto_web_origin],
            allow_methods=["*"],
            allow_headers=["*"],
            allow_credentials=False,
        )
```

- [ ] **Step 8: Run the CORS tests again, then the full API suite**

Run: `pytest tests/api/test_cors_mode.py -v` — expect PASS.
Run: `pytest` (from `apps/api`) — expect green (no other test asserts CORS headers are present
unconditionally; verified by the absence of any other `access-control-allow-origin` assertion in the
suite via `grep -rn "access-control-allow-origin" apps/api/tests`).

- [ ] **Step 9: Write the proxy route**

```typescript
// apps/web/src/app/api/v1/[...path]/route.ts
const UPSTREAM = process.env.RHAPTO_API_INTERNAL_URL ?? "http://api:8000";

// Forwarded verbatim from the incoming request; the client's own `Authorization` and any
// client-supplied `Cf-Access-Jwt-Assertion` are dropped so the only assertion that can ever reach
// the API is the one Cloudflare's edge attached to *this* request. range/accept-encoding are
// forwarded because the package-download endpoints may want them.
const FORWARD_REQUEST_HEADERS = ["accept", "content-type", "range", "accept-encoding"];

// undici's fetch accepts `duplex` to stream a request body through, but not every installed DOM
// lib types it yet; declaring our own permissive intersection avoids both an untyped call and a
// brittle `@ts-expect-error` that becomes an error itself the day the ambient lib catches up —
// verify with `pnpm typecheck` after writing this file.
type FetchInitWithDuplex = RequestInit & { duplex?: "half" };

async function proxy(request: Request, path: string[]): Promise<Response> {
  if (path.some((segment) => segment === "..")) {
    return new Response("invalid path", { status: 400 });
  }
  const upstreamUrl = new URL(`${UPSTREAM}/api/v1/${path.join("/")}${new URL(request.url).search}`);
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const assertion = request.headers.get("cf-access-jwt-assertion");
  if (assertion) headers.set("Cf-Access-Jwt-Assertion", assertion);

  const init: FetchInitWithDuplex = {
    method: request.method,
    headers,
    body: ["GET", "HEAD"].includes(request.method) ? undefined : request.body,
    duplex: request.body ? "half" : undefined,
  };
  const upstream = await fetch(upstreamUrl, init);

  const responseHeaders = new Headers(upstream.headers);
  if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
    responseHeaders.set("Cache-Control", "no-store");
    responseHeaders.set("X-Accel-Buffering", "no");
  }
  return new Response(upstream.body, { status: upstream.status, headers: responseHeaders });
}

export async function GET(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function POST(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function PUT(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function PATCH(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
export async function DELETE(request: Request, { params }: { params: Promise<{ path: string[] }> }) {
  return proxy(request, (await params).path);
}
```

Before writing this file, read the Route Handlers page and the streaming-response notes under
`apps/web/node_modules/next/dist/docs/` (per `apps/web/AGENTS.md`) and correct the `params` shape
(`Promise<{ path: string[] }>` above matches Next's async-params convention in recent versions, but
this checkout's docs are the source of truth, not this plan) and the request/response streaming API
before treating the code above as final — adjust to match what those docs say, keeping the same
contract: forward method/body/query, strip everything except `accept`/`content-type` from the
request, forward exactly one `Cf-Access-Jwt-Assertion` from the incoming request, mark SSE responses
`no-store`/`no-buffering`, stream the body through without buffering.

- [ ] **Step 10: Write the proxy route test**

```typescript
// apps/web/src/app/api/v1/[...path]/route.test.ts
import { describe, expect, it, vi } from "vitest";
import { GET } from "./route";

describe("api proxy route", () => {
  it("strips a client-supplied Cf-Access-Jwt-Assertion and forwards the edge's own", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ status: "ok" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/health", {
      headers: {
        "Cf-Access-Jwt-Assertion": "edge-issued-token",
        Authorization: "Bearer client-supplied-should-be-dropped",
      },
    });
    const response = await GET(request, { params: Promise.resolve({ path: ["health"] }) });
    expect(response.status).toBe(200);
    // fetchSpy.mock.calls[0] is `unknown[] | undefined` under noUncheckedIndexedAccess
    // (tsconfig.json:8) -- chain the optional access rather than indexing calls[0] directly
    // (re-review breakage item 4).
    const forwardedHeaders = fetchSpy.mock.calls[0]?.[1]?.headers as Headers;
    expect(forwardedHeaders.get("Cf-Access-Jwt-Assertion")).toBe("edge-issued-token");
    expect(forwardedHeaders.has("authorization")).toBe(false);
    fetchSpy.mockRestore();
  });

  it("marks an SSE upstream response no-store with buffering disabled", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(
      new Response("data: {}\n\n", {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );
    const request = new Request("http://localhost:3000/api/v1/tasks/abc/events");
    const response = await GET(request, { params: Promise.resolve({ path: ["tasks", "abc", "events"] }) });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(response.headers.get("X-Accel-Buffering")).toBe("no");
    fetchSpy.mockRestore();
  });
});
```

- [ ] **Step 11: Run it to see it fail, then pass**

Run: `pnpm test route.test.ts` (from `apps/web`)
Expected: FAIL before `route.ts` exists / before headers are handled; PASS after Step 9.

- [ ] **Step 12: Make `TokenGate` unlock in access mode**

```typescript
// apps/web/src/components/shell/TokenGate.tsx — full replacement
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore } from "react";
import { Landing } from "@/components/landing/Landing";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { hasToken, SAME_ORIGIN_DEPLOYMENT } from "@/lib/api/client";
import { useMe } from "@/lib/api/queries";

function subscribe(onStoreChange: () => void): () => void {
  window.addEventListener("storage", onStoreChange);
  window.addEventListener("rhapto-settings", onStoreChange);
  return () => {
    window.removeEventListener("storage", onStoreChange);
    window.removeEventListener("rhapto-settings", onStoreChange);
  };
}

function getSnapshot(): boolean | null {
  return hasToken();
}

function getServerSnapshot(): boolean | null {
  return null;
}

// Token-mode-only: in access mode there is no token to enter, so /settings there is just the
// LLM-key screen like any other authenticated page, and this bypass does not apply.
const PUBLIC_ROUTES = new Set(["/settings", "/about"]);

export function TokenGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const tokenPresent = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  // Called unconditionally, per React's rules of hooks, but only consulted in the access-mode
  // branch below. In token mode this issues one background /me request that 401s until a token
  // is entered; that failure is inert here, exactly as an unused query result always is.
  const me = useMe();

  if (SAME_ORIGIN_DEPLOYMENT) {
    // access mode: Cloudflare authenticated this request at the edge before it reached Rhapto at
    // all; there is no bearer token to check. /me succeeding (this instance's own allowlist check
    // passed too) is what "signed in" means here.
    if (me.isPending) return null;
    if (me.isSuccess) return <>{children}</>;
    return (
      <Card className="mx-auto max-w-md">
        <CardHeader>
          <CardTitle>Access refused</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-muted-foreground">
          <p>
            This Rhapto instance is invite-only. If you believe you should have access, ask the
            owner to add your email to the invite list.
          </p>
        </CardContent>
      </Card>
    );
  }

  if (PUBLIC_ROUTES.has(pathname)) return <>{children}</>;
  if (tokenPresent === null) return null;
  if (tokenPresent) return <>{children}</>;
  if (pathname === "/") return <Landing />;
  return (
    <Card className="mx-auto max-w-md">
      <CardHeader>
        <CardTitle>Connect to your Rhapto API</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm text-muted-foreground">
        <p>
          Enter the API URL and the bearer token from your <code>.env</code> to start.
        </p>
        <Link href="/settings" className="text-accent underline">
          Open settings
        </Link>
        <p>
          New here?{" "}
          <Link href="/about" className="text-accent underline">
            See what Rhapto does
          </Link>{" "}
          first.
        </p>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 13: Update `TokenGate.test.tsx` — wrap every render in a `QueryClientProvider`, mock `useMe`**

`useMe()` is now called unconditionally, so every existing test in this file must render inside a
`QueryClientProvider`, or `useQuery` throws for lack of a context. Add a shared helper and mock
`@/lib/api/queries` so token-mode tests (which never consult `useMe`'s value) don't need a real
network call, then add the access-mode cases:

**Fixes re-review breakage item 8.** Reassigning a property directly on a `vi.mock`-returned ESM
namespace object is read-only in several vitest/module-registry versions, which would leave the
coder to discover which fallback compiles. Use a mutable flag the mock factory closes over instead —
deterministic in every vitest version, no reassignment of the mocked namespace itself:

```typescript
// apps/web/src/components/shell/TokenGate.test.tsx — additions at the top of the file
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

const sameOriginFlag = { value: false };
vi.mock("@/lib/api/client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/client")>();
  return {
    ...actual,
    get SAME_ORIGIN_DEPLOYMENT() {
      return sameOriginFlag.value;
    },
  };
});
vi.mock("@/lib/api/queries", () => ({ useMe: vi.fn(() => ({ isPending: true, isSuccess: false })) }));

function renderGate(children: React.ReactNode) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}
```

Every existing `render(<TokenGate>...)` call in this file becomes `renderGate(<TokenGate>...)`; their
assertions are otherwise unchanged, since `sameOriginFlag.value` starts `false`, exercising the same
token-mode branch they always did. Add a new `describe` block for the access-mode branch, flipping the
flag rather than the mocked module:

```typescript
// apps/web/src/components/shell/TokenGate.test.tsx — new describe block
import { useMe } from "@/lib/api/queries";

describe("TokenGate in access mode", () => {
  beforeEach(() => {
    sameOriginFlag.value = true;
  });
  afterEach(() => {
    sameOriginFlag.value = false;
  });

  it("renders nothing while /me is pending", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: true, isSuccess: false } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    const { container } = renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders children once /me succeeds, with no token in localStorage", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: true } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.getByText("secret content")).toBeInTheDocument();
  });

  it("refuses access when /me fails (not on the invite list), never showing the token-mode card", () => {
    vi.mocked(useMe).mockReturnValue({ isPending: false, isSuccess: false } as ReturnType<typeof useMe>);
    pathname.current = "/jobs";
    renderGate(<TokenGate><p>secret content</p></TokenGate>);
    expect(screen.queryByText("secret content")).not.toBeInTheDocument();
    expect(screen.getByText(/invite-only/i)).toBeInTheDocument();
    expect(screen.queryByText(/Connect to your Rhapto API/i)).not.toBeInTheDocument();
  });
});
```

`clientModule.SAME_ORIGIN_DEPLOYMENT` is reassigned directly on the mocked module namespace, which
`vi.mock`'s factory-returned object permits; if the installed vitest version makes the mocked export
read-only, use `vi.mocked(clientModule, { partial: true })` or re-run `vi.mock` per-test with a
factory closing over a mutable flag instead — verify against `pnpm test` rather than assuming either
form compiles and runs first try.

- [ ] **Step 14: Run the updated test file, then the full suites**

Run: `pnpm test TokenGate.test.tsx` (from `apps/web`) — expect all existing token-mode tests plus the
three new access-mode tests to PASS.
Run (apps/api): `pytest`, `ruff check .`, `mypy src` — green (nothing in `apps/api/src` changed in
this task beyond the CORS gate from Step 7).
Run (apps/web): `pnpm test`, `pnpm lint`, `pnpm typecheck` — green.

- [ ] **Step 15: Commit**

```bash
git add apps/web/src/app/api/v1/\[...path\]/route.ts apps/web/src/app/api/v1/\[...path\]/route.test.ts \
  apps/web/src/lib/api/client.ts apps/web/src/lib/api/client.test.ts \
  apps/web/src/components/shell/TokenGate.tsx apps/web/src/components/shell/TokenGate.test.tsx \
  apps/api/src/rhapto/api/app.py apps/api/tests/api/test_cors_mode.py
git commit -m "$(cat <<'EOF'
Same-origin API proxy; fix the NEXT_PUBLIC_API_URL="" fallback bug; unlock TokenGate in access mode (A2)

The Next.js route handler at /api/v1/[...path] proxies to the API container over the compose
network, stripping any client-supplied Cf-Access-Jwt-Assertion and forwarding only the edge's own;
SSE responses stream through unbuffered. CORS is now installed only in token mode, where the
localhost 3000/8000 split is real.

Fixes two defects that made access mode unreachable from the browser (plan-review C2, C3):
DEFAULT_API_URL and getSettings() both treated an explicitly empty NEXT_PUBLIC_API_URL/rhapto.apiUrl
as "unset" via `||`, silently falling back to http://localhost:8000 instead of same-origin; and
TokenGate gated every route on a localStorage bearer token that access-mode users never have, so an
invited person who authenticated successfully saw the landing page forever. TokenGate now unlocks on
useMe() succeeding when the deployment is same-origin.

No localStorage key is namespaced by user (plan-review I4): lib/skipped.ts has no live callers, and
apply-prompt.ts's job-id keys cannot collide across accounts because job ids are per-row UUIDs no
two accounts ever share. Access mode stores no identity-bearing state in localStorage at all.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 1, 2, 3, 11 (an allowlisted, authenticated person can now actually
reach the application — this was the substance of C3 — and no identity-bearing `localStorage` state
exists to leak between two people sharing a browser).

---

## Task 3 (A3): Cloudflare Access mode — JWKS cache, invite allowlist, bootstrap suppression, startup assertion

Verified before writing: `apps/api/src/rhapto/api/app.py:72-78` (the lifespan call to
`get_or_create_user(settings.rhapto_user_email)` that must be suppressed in `access` mode);
`apps/api/src/rhapto/db/repositories/users.py` (`get_or_create_user`, `list_user_ids` — both
unchanged); `apps/api/src/rhapto/cli/main.py` (`alembic_config()`, `run_migrations()`,
`_with_user()` as the pattern new CLI commands follow; no `accounts` sub-app exists yet);
`apps/api/pyproject.toml` (no JWT library present today — `pyjwt` is a new dependency; `cryptography>=42`
is already present and is what `pyjwt[crypto]` uses for RS256).

**Files:**
- Modify: `apps/api/src/rhapto/api/auth.py` (real `access`-mode verification, `JwksCache`)
- Modify: `apps/api/src/rhapto/api/deps.py` (`current_user`'s access-mode branch: get-or-create by
  email, allowlist check)
- Modify: `apps/api/src/rhapto/api/app.py` (suppress the token-mode bootstrap in access mode; startup
  assertion)
- Modify: `apps/api/src/rhapto/config.py` (`rhapto_access_team`, `rhapto_access_aud`,
  `rhapto_allowed_emails`, `rhapto_allowed_email_domains`)
- Modify: `apps/api/src/rhapto/cli/main.py` (new `accounts` Typer sub-app: `set-email`)
- Modify: `apps/api/src/rhapto/db/repositories/users.py` (`get_or_create_user`: `ON CONFLICT` — C6)
- Modify: `apps/api/pyproject.toml` (add `pyjwt[crypto]>=2.9`)
- Test: `apps/api/tests/api/test_access_mode.py`
- Test: `apps/api/tests/unit/test_accounts_set_email.py` (not `tests/cli/`, which does not exist —
  plan-review I11)
- Test: concurrent get-or-create regression, added to whichever existing `tests/unit/`/`tests/db/`
  module already covers `get_or_create_user` (grep for it first — no `test_users_repo.py` exists
  today; re-review item 9)

**Interfaces:**
- Consumes: `Principal`/`resolve_principal` (Task 1), `Settings.rhapto_auth_mode` (Task 1),
  `get_or_create_user` (unchanged, `apps/api/src/rhapto/db/repositories/users.py`).
- Produces:
  ```python
  # rhapto/api/auth.py
  class JwksCache:
      async def key_for(self, kid: str) -> RSAPublicKey: ...  # raises HTTPException(503) only when
                                                                 # neither a fresh nor a retained fetch
                                                                 # has the kid

  def is_allowed_email(email: str, allowed_emails: str, allowed_domains: str) -> bool: ...
  ```
  `current_user`'s access-mode branch (previously a 501 stub) now does: allowlist check (403, no user
  row created, if the email is not allowed) → get-or-create by email → 200 with a `users.id`. Task 5
  adds the first-screen seed call at the exact point a user row is newly created here.

- [ ] **Step 1: Add the JWT dependency**

```toml
# apps/api/pyproject.toml — in the main dependency list, alongside "cryptography>=42"
    "pyjwt[crypto]>=2.9",
```

Run: `uv sync` (or the project's equivalent lock/install step) from `apps/api`.

- [ ] **Step 2: Add the new settings**

```python
# apps/api/src/rhapto/config.py — inside class Settings, after rhapto_auth_mode
    rhapto_access_team: str = ""
    rhapto_access_aud: str = ""
    rhapto_allowed_emails: str = ""          # comma-separated, exact, casefolded
    rhapto_allowed_email_domains: str = ""   # comma-separated, casefolded, no leading "@"
```

- [ ] **Step 3: Write the failing allowlist test (pure function, no network)**

```python
# apps/api/tests/api/test_access_mode.py
from __future__ import annotations

from rhapto.api.auth import is_allowed_email


def test_exact_email_match() -> None:
    assert is_allowed_email("Wife@Example.com", "wife@example.com", "")


def test_domain_match() -> None:
    assert is_allowed_email("friend@company.io", "", "company.io")


def test_no_match_is_refused() -> None:
    assert not is_allowed_email("stranger@gmail.com", "wife@example.com", "company.io")


def test_empty_allowlist_fails_closed() -> None:
    assert not is_allowed_email("anyone@example.com", "", "")
```

- [ ] **Step 4: Run it to see it fail**

Run: `pytest tests/api/test_access_mode.py -v`
Expected: FAIL — `is_allowed_email` does not exist yet.

- [ ] **Step 5: Implement `is_allowed_email` and the JWKS cache**

**Fixes plan-review finding I8.** The earlier draft of `JwksCache` had two bugs, both verified against
its own code rather than assumed: `_refresh` stamped `self._fetched_at = now` *before* the HTTP call,
so a failed fetch still reset the TTL and suppressed retries for a further 600s; and it merged into
`self._keys` (`self._keys[kid] = ...`) rather than replacing the set, so a key Cloudflare rotated out
stayed trusted forever with no code path able to remove it. Fixed below by keeping a separate
`_last_attempt_at` (for the 30s floor, updated on every attempt) from `_fetched_at` (updated only on a
*successful* fetch), and by replacing the active key set on success while demoting the previous set to
a `_retained` fallback consulted only when a fetch fails. The unused `PyJWKClient` construction is
also removed — dead code in the earlier draft, since keys are parsed from the raw JSON response
instead.

```python
# apps/api/src/rhapto/api/auth.py — additions
from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from jwt.exceptions import InvalidTokenError


def is_allowed_email(email: str, allowed_emails: str, allowed_domains: str) -> bool:
    """Casefolded exact-match or domain-match against the two comma-separated allowlists.

    An empty allowlist fails closed: "unconfigured" must never mean "open", matching the
    codebase's existing posture on an empty `rhapto_api_token`.
    """
    normalized = email.casefold().strip()
    exact = {e.strip().casefold() for e in allowed_emails.split(",") if e.strip()}
    domains = {d.strip().casefold().lstrip("@") for d in allowed_domains.split(",") if d.strip()}
    if not exact and not domains:
        return False
    if normalized in exact:
        return True
    domain = normalized.rsplit("@", 1)[-1] if "@" in normalized else ""
    return domain in domains


class JwksCache:
    """Per-process JWKS cache with last-good-key retention (architecture.md §1.3).

    An unreachable JWKS endpoint does not fail requests as long as the *retained* set (the last
    successfully fetched one) still has the requested `kid` -- Cloudflare rotates keys with
    overlap, so a retained set stays valid far longer than any plausible outage. Only when the
    retained set also lacks the `kid` does this raise, and the caller turns that into a 503 (not
    401): "we cannot check" is not "you are not authorised".
    """

    def __init__(self, jwks_url: str, *, ttl_seconds: float = 600, refetch_floor: float = 30) -> None:
        self._jwks_url = jwks_url
        self._ttl = ttl_seconds
        self._floor = refetch_floor
        self._keys: dict[str, Any] = {}      # the last successfully fetched set
        self._retained: dict[str, Any] = {}  # the set before that, kept only as a fallback
        self._fetched_at: float = 0.0        # set only on a successful fetch
        self._last_attempt_at: float = 0.0   # set on every attempt, success or failure

    async def _refresh(self) -> None:
        now = time.monotonic()
        if now - self._last_attempt_at < self._floor:
            return
        self._last_attempt_at = now
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()
            fetched: dict[str, Any] = {}
            for jwk in response.json().get("keys", []):
                kid = jwk.get("kid")
                if kid:
                    fetched[kid] = jwt.PyJWK(jwk).key
        if self._keys:
            self._retained = self._keys
        self._keys = fetched
        self._fetched_at = now

    async def key_for(self, kid: str) -> Any:
        now = time.monotonic()
        if kid not in self._keys or now - self._fetched_at > self._ttl:
            try:
                await self._refresh()
            except httpx.HTTPError:
                pass  # fall through to whatever self._keys/self._retained already hold
        if kid in self._keys:
            return self._keys[kid]
        if kid in self._retained:
            return self._retained[kid]
        from fastapi import HTTPException

        raise HTTPException(
            status_code=503, detail="cannot verify identity right now", headers={"Retry-After": "30"}
        )
```

- [ ] **Step 6: Run the pure-function tests again**

Run: `pytest tests/api/test_access_mode.py -v -k "not verify"`
Expected: PASS for the four `is_allowed_email` tests.

- [ ] **Step 7: Wire real verification into `resolve_principal`**

```python
# apps/api/src/rhapto/api/auth.py — replace the access-mode branch of resolve_principal
_jwks_caches: dict[str, JwksCache] = {}  # keyed by team domain, one cache per process


def _jwks_cache_for(team: str) -> JwksCache:
    if team not in _jwks_caches:
        _jwks_caches[team] = JwksCache(f"https://{team}.cloudflareaccess.com/cdn-cgi/access/certs")
    return _jwks_caches[team]


async def resolve_principal(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> Principal:
    state = _state(request)  # from Task 1 — reads request.app.state.rhapto directly, no import of deps.py
    settings = state.settings
    if settings.rhapto_auth_mode != "access":
        expected = settings.rhapto_api_token
        provided = (
            authorization.removeprefix("Bearer ").strip()
            if authorization and authorization.startswith("Bearer ")
            else None
        )
        if not expected or not secrets.compare_digest(provided or "", expected):
            raise HTTPException(
                status_code=401,
                detail="missing or invalid bearer token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return Principal(mode="token", subject="token", email=settings.rhapto_user_email.casefold())

    assertions = request.headers.getlist("cf-access-jwt-assertion")
    if len(assertions) > 1:
        raise HTTPException(status_code=400, detail="multiple Cf-Access-Jwt-Assertion headers")
    if not assertions:
        raise HTTPException(status_code=401, detail="missing Cf-Access-Jwt-Assertion")
    token = assertions[0]
    try:
        unverified = jwt.get_unverified_header(token)
        kid = unverified["kid"]
        key = await _jwks_cache_for(settings.rhapto_access_team).key_for(kid)
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=settings.rhapto_access_aud,
            issuer=f"https://{settings.rhapto_access_team}.cloudflareaccess.com",
            leeway=60,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except HTTPException:
        raise
    except (InvalidTokenError, KeyError) as exc:
        raise HTTPException(status_code=401, detail="invalid identity assertion") from exc
    email = claims.get("email")
    if not email:
        raise HTTPException(status_code=401, detail="identity assertion has no email claim")
    return Principal(mode="access", subject=str(claims.get("sub", "")), email=str(email).casefold())
```

`Request.headers.getlist` is Starlette's multi-value header accessor (verified available on
Starlette's `Headers`, which FastAPI's `Request.headers` is) — this is how the duplicate-header rule
(§1.2) is enforced without relying on the single `Header()` FastAPI param, which coalesces repeated
headers rather than rejecting them.

- [ ] **Step 8: Make `get_or_create_user` safe under concurrent first sign-ins**

**Fixes plan-review finding C6 (the account-duplication half; the seeding half is fixed in Task 5).**
Verified: `get_or_create_user` (`apps/api/src/rhapto/db/repositories/users.py:11-18`) is a plain
select-then-insert with no `ON CONFLICT`. A brand-new browser tab fires several requests in parallel
on first load (`useMe()` plus the page's own queries), so two `current_user` invocations for the same
brand-new email routinely race: both see no existing row, both `INSERT`, and `users.email`'s unique
constraint (`db/models.py:38`, `unique=True`) turns the loser into an unhandled `IntegrityError` — a
500 on the invited person's very first request. Fixed with `INSERT ... ON CONFLICT (email) DO NOTHING`
followed by a re-select, so the loser of the race simply reads the winner's row instead of erroring.

```python
# apps/api/src/rhapto/db/repositories/users.py — replace get_or_create_user
from sqlalchemy.dialects.postgresql import insert as pg_insert


async def get_or_create_user(session: AsyncSession, email: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None:
        return user
    stmt = pg_insert(User).values(email=email).on_conflict_do_nothing(index_elements=["email"])
    await session.execute(stmt)
    await session.flush()
    user = await session.scalar(select(User).where(User.email == email))
    assert user is not None  # the row now exists, either from this INSERT or the racing one
    return user
```

Add to `apps/api/tests/unit/test_users_repo.py` (or the existing test module for this repository —
grep `apps/api/tests` for `get_or_create_user` to find where its current tests live and add
alongside them, rather than creating a new file for one test):

```python
async def test_concurrent_get_or_create_never_raises(session_factory) -> None:
    import asyncio

    async def create() -> uuid.UUID:
        async with session_factory() as s:
            u = await get_or_create_user(s, "racer@example.com")
            await s.commit()
            return u.id

    ids = await asyncio.gather(create(), create(), create())
    assert len(set(ids)) == 1
```

Run: `pytest tests/unit/test_users_repo.py -k concurrent -v` (adjust the path to wherever the test
landed) — expect PASS; run it once against the unmodified function first (temporarily) to confirm it
reproduces the `IntegrityError` this fix closes, per this plan's TDD convention.

- [ ] **Step 9: Wire the allowlist and get-or-create into `current_user`**

```python
# apps/api/src/rhapto/api/deps.py — replace the access-mode branch of current_user
from rhapto.api.auth import is_allowed_email
from rhapto.db.repositories.users import get_or_create_user


async def current_user(
    request: Request,
    principal: Annotated[Principal, Depends(resolve_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> uuid.UUID:
    state = get_state(request)
    if principal.mode == "token":
        if state.user_id is None:
            raise HTTPException(status_code=503, detail="server not ready")
        return state.user_id
    settings = state.settings
    if not is_allowed_email(
        principal.email, settings.rhapto_allowed_emails, settings.rhapto_allowed_email_domains
    ):
        raise HTTPException(status_code=403, detail="this instance is invite-only")
    user = await get_or_create_user(session, principal.email)
    await session.commit()
    return user.id
```

This is deliberately the *only* thing `current_user`'s access-mode branch does — no seeding, no
backfill. Task 5 adds a separate, dedicated endpoint for that (plan-review C6: every endpoint depends
on `current_user`, so it must stay fast and its failure must never look like an auth failure).
(`AsyncSession` and `get_session` are already imported/defined in `deps.py`; `Depends` needs adding
to the `fastapi` import, as in Task 1 Step 8.)

- [ ] **Step 10: Suppress the token-mode bootstrap and add the startup assertion**

**Fixes re-review finding I9 (previously claimed fixed but the check was absent from the code — the
resolution log described an assertion the lifespan body never actually contained).**
`RHAPTO_ACCESS_TEAM=""` produces a JWKS URL of `https://.cloudflareaccess.com/...` (every request
503s, since the fetch fails and no key is ever retained) and `RHAPTO_ACCESS_AUD=""` makes every
`jwt.decode(..., audience="")` call fail its audience check (every request 401s) — both fail closed,
which is directionally right, but with no actionable startup error telling the operator why. The
non-empty check below must be a real, separate `raise` in the lifespan body, checked **before** the
allowlist query (an empty team/aud makes that query meaningless anyway):

```python
# apps/api/src/rhapto/api/app.py — replace the lifespan body's bootstrap block (lines 74-78)
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        warn_if_fake_llm(settings)
        if settings.rhapto_auth_mode == "access":
            if not settings.rhapto_access_team or not settings.rhapto_access_aud:
                raise RuntimeError(
                    "RHAPTO_AUTH_MODE=access requires RHAPTO_ACCESS_TEAM and RHAPTO_ACCESS_AUD to "
                    "both be set; refusing to start with either empty, since every request would "
                    "otherwise fail with no actionable error (503 from an unreachable JWKS host, or "
                    "401 from an audience check that can never pass)."
                )
            async with state.session_factory() as session:
                allowed = await _any_allowed_user_exists(session, settings)
            if not allowed:
                raise RuntimeError(
                    "RHAPTO_AUTH_MODE=access but no users row matches RHAPTO_ALLOWED_EMAILS/"
                    "RHAPTO_ALLOWED_EMAIL_DOMAINS. Refusing to start: this is the failure mode "
                    "that makes the owner's existing account appear to have vanished. Run "
                    "`rhapto accounts set-email <old> <new>` first if RHAPTO_USER_EMAIL does not "
                    "match the owner's Cloudflare Access email."
                )
        else:
            async with state.session_factory() as session:
                user = await get_or_create_user(session, settings.rhapto_user_email)
                await session.commit()
                state.user_id = user.id
        try:
            yield
        finally:
            for collaborator in (state.enqueuer, state.event_bus):
                close = getattr(collaborator, "close", None)
                if close is not None:
                    await close()
            await state.discovery_http.aclose()
            if state.engine is not None:
                await state.engine.dispose()
```

```python
# apps/api/src/rhapto/api/app.py — new module-level helper
from rhapto.api.auth import is_allowed_email
from rhapto.db.models import User
from sqlalchemy import select


async def _any_allowed_user_exists(session: AsyncSession, settings: Settings) -> bool:
    emails = await session.scalars(select(User.email))
    return any(
        is_allowed_email(e, settings.rhapto_allowed_emails, settings.rhapto_allowed_email_domains)
        for e in emails
    )
```

- [ ] **Step 11: Add `rhapto accounts set-email` — fixing plan-review minor 3**

The lookup now casefolds `old_email` (every stored email is casefolded already, via
`is_allowed_email`/`Principal.email` in access mode; an un-casefolded lookup here would silently find
nothing for `Wife@Example.com` even though the stored row is `wife@example.com`), and checks that
`new_email` isn't already taken before writing, raising a clear error instead of a raw `IntegrityError`.

```python
# apps/api/src/rhapto/cli/main.py — new sub-app, following the existing db_app/profile_app pattern
accounts_app = typer.Typer(no_args_is_help=True, help="Account maintenance.")
app.add_typer(accounts_app, name="accounts")


@accounts_app.command("set-email")
def accounts_set_email(old_email: str = typer.Argument(...), new_email: str = typer.Argument(...)) -> None:
    """Rename an account's email -- run before flipping RHAPTO_AUTH_MODE to access, so the owner's
    bootstrapped account matches his Cloudflare Access email exactly."""
    settings = Settings()
    new_casefolded = new_email.casefold()

    async def rename() -> str:
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as session:
                from sqlalchemy import select as sa_select

                from rhapto.db.models import User

                user = await session.scalar(
                    sa_select(User).where(User.email == old_email.casefold())
                )
                if user is None:
                    return "not_found"
                taken = await session.scalar(
                    sa_select(User).where(User.email == new_casefolded, User.id != user.id)
                )
                if taken is not None:
                    return "taken"
                user.email = new_casefolded
                await session.commit()
                return "ok"
        finally:
            await engine.dispose()

    result = asyncio.run(rename())
    if result == "not_found":
        typer.echo(f"error: no account found with email {old_email!r}", err=True)
        raise typer.Exit(1)
    if result == "taken":
        typer.echo(f"error: {new_email!r} is already in use by another account", err=True)
        raise typer.Exit(1)
    typer.echo(f"renamed {old_email} -> {new_email}")
```

- [ ] **Step 12: Write the access-mode integration tests**

Every test below mutates `state.settings` directly rather than restoring it afterwards. This is safe
only because `app`/`api_settings` are function-scoped fixtures (`tests/api/conftest.py:109,145`, per
Task 1's verification), so each test gets its own fresh `Settings` and there is nothing to leak into
the next test (plan-review minor 2).

```python
# apps/api/tests/api/test_access_mode.py — append
import time

import httpx
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI

from rhapto.api.deps import AppState


@pytest.fixture
def rsa_keypair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key, key.public_key()


@pytest.fixture
def signed_assertion(rsa_keypair):
    private_key, _ = rsa_keypair
    now = int(time.time())

    def make(email: str, *, aud: str = "test-aud", team: str = "test-team") -> str:
        return pyjwt.encode(
            {"email": email, "sub": "idp-sub-1", "aud": aud, "iss": f"https://{team}.cloudflareaccess.com",
             "iat": now, "exp": now + 300},
            private_key,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )

    return make


async def test_valid_assertion_for_allowed_email_creates_an_account(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch
) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    from rhapto.api import auth as auth_module

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("Wife@Example.com")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 200
    assert response.json()["email"] == "wife@example.com"


async def test_non_allowlisted_email_gets_403_and_no_account(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch, session_factory
) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    from rhapto.api import auth as auth_module
    from rhapto.db.models import User
    from sqlalchemy import select

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("stranger@gmail.com")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 403
    async with session_factory() as session:
        existing = await session.scalar(select(User).where(User.email == "stranger@gmail.com"))
    assert existing is None


async def test_duplicate_assertion_headers_is_400(app: FastAPI, signed_assertion) -> None:
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    token = signed_assertion("wife@example.com")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        request = c.build_request(
            "GET", "/api/v1/me", headers=[("Cf-Access-Jwt-Assertion", token), ("Cf-Access-Jwt-Assertion", token)]
        )
        response = await c.send(request)
    assert response.status_code == 400


async def test_a_list_valued_aud_claim_is_accepted_when_it_contains_the_configured_aud(
    app: FastAPI, rsa_keypair, monkeypatch
) -> None:
    """Fixes plan-review I9: architecture.md §1.2 specifies 'aud contains RHAPTO_ACCESS_AUD', not
    'aud equals it' -- Cloudflare can issue a token whose aud is a list when an Access application
    is shared across more than one AUD tag. PyJWT's decode(audience=...) already checks membership
    against a list or scalar aud claim; this pins that behaviour rather than adding new logic."""
    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "wife@example.com"

    from rhapto.api import auth as auth_module

    private_key, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    now = int(time.time())
    token = pyjwt.encode(
        {
            "email": "wife@example.com", "sub": "idp-sub-1",
            "aud": ["test-aud", "some-other-aud"],
            "iss": "https://test-team.cloudflareaccess.com", "iat": now, "exp": now + 300,
        },
        private_key, algorithm="RS256", headers={"kid": "test-kid"},
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
    assert response.status_code == 200


async def test_startup_refuses_empty_access_team_or_aud(
    api_settings: Settings, session_factory, storage
) -> None:
    """Fixes re-review I9: this is the actual code-level regression test the earlier resolution log
    claimed existed. Builds its own app (the `app` fixture's lifespan already ran with token-mode
    defaults before this test body runs) and asserts the lifespan itself refuses to start."""
    from asgi_lifespan import LifespanManager

    from rhapto.api.app import create_app

    api_settings.rhapto_auth_mode = "access"
    api_settings.rhapto_access_team = ""
    api_settings.rhapto_access_aud = ""
    api_settings.rhapto_allowed_emails = "wife@example.com"
    application = create_app(api_settings, session_factory=session_factory, storage=storage)
    with pytest.raises(RuntimeError, match="RHAPTO_ACCESS_TEAM and RHAPTO_ACCESS_AUD"):
        async with LifespanManager(application):
            pass
```

**Fixes plan-review I11.** Put the new CLI tests in `apps/api/tests/unit/`, alongside the existing
`test_cli.py` — there is no `apps/api/tests/cli/` directory today, and `tests/unit/` carries no
`__init__.py` (matching `test_cli.py`'s own location):

```python
# apps/api/tests/unit/test_accounts_set_email.py
from __future__ import annotations

import asyncio

from typer.testing import CliRunner

from rhapto.cli.main import app
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

runner = CliRunner()


def test_set_email_renames_an_existing_account(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            await get_or_create_user(session, "user@example.com")
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "set-email", "user@example.com", "owner@realdomain.com"])
    assert result.exit_code == 0, result.output
    assert "renamed" in result.output


def test_set_email_unknown_account_exits_1(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    result = runner.invoke(app, ["accounts", "set-email", "nobody@example.com", "x@example.com"])
    assert result.exit_code == 1


def test_set_email_refuses_a_taken_target(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            await get_or_create_user(session, "one@example.com")
            await get_or_create_user(session, "two@example.com")
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "set-email", "one@example.com", "two@example.com"])
    assert result.exit_code == 1
    assert "already in use" in result.output
```

- [ ] **Step 13: Run the new tests, then the full suite**

Run: `pytest tests/api/test_access_mode.py tests/unit/test_accounts_set_email.py -v` — expect PASS.
Run: `pytest` — expect green, including the four A1-listed token-mode tests unmodified.
Run: `ruff check .` and `mypy src` — expect clean (add `pyjwt` to the mypy override list in
`pyproject.toml` only if `mypy src` reports missing stubs for it; PyJWT ships inline types, so this
is likely unnecessary — verify against the actual `mypy src` output rather than pre-emptively adding
an override).

- [ ] **Step 14: Commit**

```bash
git add apps/api/src/rhapto/api/auth.py apps/api/src/rhapto/api/deps.py apps/api/src/rhapto/api/app.py \
  apps/api/src/rhapto/config.py apps/api/src/rhapto/cli/main.py apps/api/pyproject.toml \
  apps/api/src/rhapto/db/repositories/users.py \
  apps/api/tests/api/test_access_mode.py apps/api/tests/unit/test_accounts_set_email.py
git commit -m "$(cat <<'EOF'
Implement Cloudflare Access mode: JWKS verification, invite allowlist, bootstrap suppression (A3)

Access mode verifies the Cf-Access-Jwt-Assertion RS256 against a last-good-cached JWKS (replacing
the key set on a successful refresh and falling back to the previous one only when a refresh fails,
plan-review I8), rejects a duplicated assertion header with 400, and enforces
RHAPTO_ALLOWED_EMAILS/_DOMAINS a second time in the API (403, no users row created, if the email is
not on the list). The token-mode bootstrap that would otherwise create a second, empty owner
account is suppressed in access mode, replaced by a startup assertion requiring RHAPTO_ACCESS_TEAM/
_AUD to be set (plan-review I9) and that an allowed users row already exists. get_or_create_user now
uses ON CONFLICT DO NOTHING so two concurrent first-sign-in requests for the same new email cannot
raise an IntegrityError (plan-review C6, the account-duplication half). `rhapto accounts set-email`
lets the owner correct RHAPTO_USER_EMAIL before the mode flip, now casefolding its lookup and
refusing a taken target (plan-review minor 3).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 1, 2, 15 (the startup assertion and `set-email` CLI are the direct
mitigation for the owner's account appearing to vanish).

---

## Task 4 (A4): Per-user poll fan-out, PDF concurrency-1 gate, dead-code removal

Verified before writing: `apps/api/src/rhapto/worker/tasks.py:362-388` (`poll_all_sources` today loops
over `list_user_ids` and calls `poll_sources` inline, in-process, per user — it does not enqueue a
separate arq job per user); `apps/api/src/rhapto/worker/tasks.py:300-359` (`poll_now`, the
user-triggered path, has no lock); `apps/api/src/rhapto/worker/tasks.py:224-235`
(`render_package_pdf`, no concurrency gate); `apps/api/src/rhapto/worker/main.py:39-69`
(`enqueue_location_backfill`/`_location_backfill_done`, and the import of
`users_needing_location_backfill` from `rhapto.services.scoring` — both dead code the migration
`0005` location-tier backfill has finished five migrations ago); `apps/api/src/rhapto/worker/main.py:104-105`
(`max_jobs = 2`, `job_timeout = 600`); no `advisory` lock usage exists anywhere in
`apps/api/src/rhapto` today (grepped).

**This task's fixture fix is not optional decoration — plan-review finding C4 showed the earlier
version of this task left at least six existing tests red while claiming green:** `poll_user`/`poll_now`
reading `ctx["engine"]` breaks `test_poll_now_runs_and_publishes`,
`test_poll_now_records_failure`, `test_poll_now_reports_success_for_a_result_tied_to_a_saved_search`
(all in `apps/api/tests/unit/test_worker_discovery.py`, all built on the module-level `ctx_for(factory,
bus)` helper at that file's line ~61, which has no `engine` key); `poll_all_sources` reading
`ctx["redis"]` breaks `test_poll_all_sources_never_raises_and_continues_after_failure` and
`test_poll_all_sources_gives_each_user_their_own_session` (same file, same helper, no `redis` key —
and both tests also assert the inline per-user loop this task deletes); and adding `"poll_user"` to
`TASKS` breaks `test_worker_tasks.py::test_registry`'s exact-set assertion (`apps/api/tests/unit/test_worker_tasks.py:102-112`,
`assert set(TASKS) == {...}` with seven names, not eight). Step 7 below fixes all four files.

**Also fixes re-review breakage item 2 — the dead-code deletion (Step 9) itself was not green as
written.** The earlier version asserted "the only caller was `worker/main.py`" without grepping for
one; verified false. `users_needing_location_backfill` is imported at module level by
`apps/api/tests/unit/test_scoring_service.py:15` (so deleting the function fails collection of that
whole file) and asserted against in five places at `:235-251`.
`enqueue_location_backfill`/`_location_backfill_done` are exercised directly by
`test_startup_backfills_users_whose_jobs_predate_location_priority` (`test_worker_discovery.py:287`)
and `test_startup_backfill_never_fails_the_worker` (`:304`). Step 9 below deletes these tests too, not
just the code.

**Files:**
- Modify: `apps/api/src/rhapto/worker/tasks.py` (new `poll_user` task; `poll_all_sources` becomes a
  thin dispatcher; advisory lock in `poll_user` and `poll_now`; concurrency-1 gate in
  `render_package_pdf`)
- Modify: `apps/api/src/rhapto/worker/main.py` (register `poll_user`; delete
  `enqueue_location_backfill`/`_location_backfill_done`/the `on_startup` call to it)
- Modify: `apps/api/src/rhapto/services/scoring.py` (delete `users_needing_location_backfill`, now
  unused)
- Modify: `apps/api/tests/api/conftest.py` (`worker_ctx` gains `engine`/`redis`)
- Modify: `apps/api/tests/unit/test_worker_discovery.py` (`ctx_for` gains `engine`/`redis`; the two
  `poll_all_sources` tests are replaced by `poll_user`-targeted equivalents; the two
  location-backfill tests at `:287`/`:304` are deleted — re-review item 2)
- Modify: `apps/api/tests/unit/test_worker_tasks.py` (`test_registry`'s expected set gains `"poll_user"`)
- Modify: `apps/api/tests/unit/test_scoring_service.py` (delete the `users_needing_location_backfill`
  import and its five assertions at `:235-251` — re-review item 2)
- Test: `apps/api/tests/unit/test_poll_fan_out.py`
- Test: `apps/api/tests/api/test_pdf_concurrency_gate.py` (in `tests/api/`, not `tests/unit/` — see
  Step 10, re-review breakage item 3)

**Interfaces:**
- Consumes: `ctx["session_factory"]`, `ctx["engine"]` (set in the *real* worker's `on_startup`,
  `worker/main.py:75-76` — but verified **absent** from the test doubles `worker_ctx`
  (`tests/api/conftest.py`) and `ctx_for` (`tests/unit/test_worker_discovery.py`) before this task,
  which is exactly plan-review finding C4; Step 7 adds it to both), `list_user_ids` (unchanged,
  `db/repositories/users.py`), `poll_sources` (unchanged, `services/discovery/poller.py:291`).
- Produces:
  ```python
  # rhapto/worker/tasks.py
  async def poll_user(ctx: dict[str, Any], user_id: str) -> None: ...  # one user's poll, its own
                                                                          # 600s budget, advisory-locked

  async def with_user_poll_lock(
      engine: AsyncEngine, user_id: uuid.UUID
  ) -> AsyncContextManager[bool]: ...  # yields True iff the lock was acquired; always releases
  ```
  `TASKS["poll_user"] = poll_user` and `WorkerSettings.functions` gains `poll_user`, for Task 6/7 (and
  any future caller) to enqueue against.

- [ ] **Step 1: Write the failing fan-out test**

```python
# apps/api/tests/unit/test_poll_fan_out.py
from __future__ import annotations

import uuid
from typing import Any

import pytest

from rhapto.db.repositories.users import get_or_create_user
from rhapto.worker.tasks import poll_all_sources


class RecordingRedis:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue_job(self, task: str, **kwargs: Any) -> None:
        self.enqueued.append((task, kwargs))


async def test_poll_all_sources_enqueues_one_poll_user_job_per_user(session_factory) -> None:
    async with session_factory() as session:
        u1 = await get_or_create_user(session, "one@example.com")
        u2 = await get_or_create_user(session, "two@example.com")
        await session.commit()
        u1_id, u2_id = u1.id, u2.id

    redis = RecordingRedis()
    await poll_all_sources({"session_factory": session_factory, "redis": redis})

    enqueued_user_ids = {kwargs["user_id"] for _, kwargs in redis.enqueued if _ == "poll_user"}
    assert enqueued_user_ids == {str(u1_id), str(u2_id)}


async def test_poll_all_sources_returns_without_polling_inline(session_factory, monkeypatch) -> None:
    """The cron entry point must not call poll_sources itself -- that is poll_user's job now."""
    import rhapto.worker.tasks as tasks_module

    async def boom(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("poll_all_sources must not call poll_sources directly")

    monkeypatch.setattr(tasks_module, "poll_sources", boom)
    redis = RecordingRedis()
    await poll_all_sources({"session_factory": session_factory, "redis": redis})
```

- [ ] **Step 2: Run it to see it fail**

Run: `pytest tests/unit/test_poll_fan_out.py -v`
Expected: FAIL — today's `poll_all_sources` has no `ctx["redis"]` usage and calls `poll_sources`
inline (would trip the `boom` monkeypatch in the second test; the first test's `redis.enqueued` stays
empty).

- [ ] **Step 3: Add the advisory lock helper**

```python
# apps/api/src/rhapto/worker/tasks.py — new helper, near the top after imports
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


@asynccontextmanager
async def with_user_poll_lock(engine: AsyncEngine, user_id: uuid.UUID) -> AsyncIterator[bool]:
    """A Postgres session-level advisory lock keyed on `user_id`, so the cron's `poll_user` and a
    hand-triggered `poll_now` can never interleave for the same user (audit B11). Non-blocking
    (`pg_try_advisory_lock`): the caller that loses the race skips its poll for this cycle rather
    than queuing behind the other one, which is the right trade for a cron that runs again on its
    own schedule. Advisory locks are connection-scoped, so the lock and its release must use the
    same underlying connection -- a bare `AsyncSession` from a pooled sessionmaker does not
    guarantee that, so this opens its own connection directly.
    """
    key = int.from_bytes(user_id.bytes[:8], "big", signed=True)
    async with engine.connect() as conn:
        acquired = bool((await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": key})).scalar())
        try:
            yield acquired
        finally:
            if acquired:
                await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
```

`int.from_bytes(user_id.bytes[:8], "big", signed=True)` maps a uuid's first 8 bytes to a signed
64-bit integer, which is what `pg_try_advisory_lock(bigint)` takes; collisions across two different
`user_id`s are astronomically unlikely (64 bits of a random uuid) and, even if they occurred, would
only cause one user's poll to skip a cycle, not corrupt or cross-deliver any data.

- [ ] **Step 4: Split `poll_all_sources` into a dispatcher, and add `poll_user`**

```python
# apps/api/src/rhapto/worker/tasks.py — replace poll_all_sources (previously lines 362-388)
async def poll_user(ctx: dict[str, Any], user_id: str) -> None:
    """One user's scheduled poll, its own 600s job_timeout, advisory-locked against a concurrent
    poll_now for the same user."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    engine: AsyncEngine = ctx["engine"]
    bus: EventBus = ctx["event_bus"]
    uid = uuid.UUID(user_id)
    async with with_user_poll_lock(engine, uid) as acquired:
        if not acquired:
            logger.info("skipping scheduled poll for user %s: a poll is already in progress", user_id)
            return
        try:
            async with factory() as session:
                summary = await poll_sources(
                    session, uid, http=ctx["discovery_http"], embedder=ctx["embedder"], fernet=_poll_fernet()
                )
            await bus.publish(DISCOVERY_CHANNEL, {"event": "discovery", "new_jobs": summary.new_jobs})
        except Exception:
            logger.exception("scheduled poll failed for user %s", user_id)


async def poll_all_sources(ctx: dict[str, Any]) -> None:
    """Cron entry point: enqueue one poll_user job per user and return immediately, so a slow or
    stuck poll for one user never holds another user's poll behind it inside a single 600s task
    (architecture.md §2.3 -- two users used to exceed job_timeout in the old inline loop)."""
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    async with factory() as session:
        user_ids = await list_user_ids(session)
    for user_id in user_ids:
        await ctx["redis"].enqueue_job("poll_user", user_id=str(user_id))
```

- [ ] **Step 5: Register `poll_user`**

```python
# apps/api/src/rhapto/worker/tasks.py — TASKS dict
TASKS: dict[str, TaskFn] = {
    "tailor_job": tailor_job,
    "embed_blocks": embed_blocks,
    "render_package_pdf": render_package_pdf,
    "poll_now": poll_now,
    "poll_all_sources": poll_all_sources,
    "poll_user": poll_user,
    "score_jobs": score_jobs,
    "rescore_jobs": rescore_jobs,
}
```

```python
# apps/api/src/rhapto/worker/main.py — WorkerSettings.functions
    functions = [
        tailor_job, embed_blocks, render_package_pdf, poll_now, poll_user, score_jobs, rescore_jobs,
    ]
```

Add `poll_user` to `worker/main.py`'s import from `rhapto.worker.tasks`.

- [ ] **Step 6: Add the lock to `poll_now`**

```python
# apps/api/src/rhapto/worker/tasks.py — inside poll_now, wrap the poll_sources call
    async with factory() as session:
        tid: uuid.UUID | None = None
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

            async with with_user_poll_lock(ctx["engine"], active.user_id) as acquired:
                if not acquired:
                    task_repo.mark_failed(active, "a poll is already running for this account")
                    await session.commit()
                    await bus.publish(channel, {"event": "error", "message": "a poll is already running"})
                    return
                summary = await poll_sources(
                    session, active.user_id, http=ctx["discovery_http"], embedder=ctx["embedder"],
                    on_step=on_step, fernet=_poll_fernet(),
                )
            task_repo.mark_succeeded(active, f"new:{summary.new_jobs}")
            # ... rest of the function body is unchanged from here (the results/publish block)
```

- [ ] **Step 7: Fix the four existing test files `ctx["engine"]`/`ctx["redis"]` break — plan-review C4**

**(a) `apps/api/tests/api/conftest.py` — `worker_ctx` gains `engine`:**

```python
# apps/api/tests/api/conftest.py — worker_ctx fixture, add the `engine` parameter and key
@pytest.fixture
def worker_ctx(
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    llm_resolver: RecordingResolver,
    event_bus: InMemoryEventBus,
    storage: PackageStorage,
    api_settings: Settings,
) -> dict[str, Any]:
    return {
        "session_factory": session_factory,
        "engine": engine,
        "llm_resolver": llm_resolver,
        "embedder": FakeEmbeddingProvider(dimensions=384),
        "event_bus": event_bus,
        "storage": storage,
        "soffice_binary": api_settings.rhapto_soffice_binary,
        "discovery_http": FakeDiscoveryHttp({}),
    }
```

`engine` is already defined as a fixture in `apps/api/tests/conftest.py` (the parent conftest), so
`worker_ctx` can depend on it directly with no new import beyond `AsyncEngine` from
`sqlalchemy.ext.asyncio` (already imported in this file for `async_sessionmaker[AsyncSession]`
annotations). `worker_ctx` never calls `poll_all_sources`, so it does not need a `redis` key.

**(b) `apps/api/tests/unit/test_worker_discovery.py` — `ctx_for` gains `engine` and `redis`:**

```python
# apps/api/tests/unit/test_worker_discovery.py — replace ctx_for
class RecordingRedis:
    """A minimal arq-pool double: records every enqueue_job call, does not run anything."""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, dict[str, Any]]] = []

    async def enqueue_job(self, task: str, **kwargs: Any) -> None:
        self.enqueued.append((task, kwargs))


def ctx_for(
    factory: async_sessionmaker[AsyncSession], bus: InMemoryEventBus, engine: AsyncEngine
) -> dict[str, Any]:
    return {
        "session_factory": factory,
        "engine": engine,
        "redis": RecordingRedis(),
        "embedder": FakeEmbeddingProvider(dimensions=384),
        "event_bus": bus,
        "discovery_http": fake_http_for("greenhouse"),
        "allow_dimension_mismatch": False,
    }
```

Add `from sqlalchemy.ext.asyncio import AsyncEngine` to this file's existing
`sqlalchemy.ext.asyncio` import line. Every test in this file that calls `ctx_for(session_factory,
bus)` now needs the `engine: AsyncEngine` fixture added to its own parameter list and threaded
through: `ctx_for(session_factory, bus, engine)`. Grep this file for `ctx_for(` to find every call
site — `test_poll_now_runs_and_publishes`, `test_poll_now_records_failure`,
`test_poll_now_reports_success_for_a_result_tied_to_a_saved_search`, and both `poll_all_sources`
tests replaced below are the ones this session verified exist.

**(c) Replace the two `poll_all_sources` tests with `poll_user`-targeted equivalents** — the fan-out
behaviour they no longer exercise (`poll_all_sources` used to poll inline; it now only enqueues) is
already proven by `test_poll_fan_out.py` (Step 1); what they were *actually* protecting — one user's
failure not affecting another, and each user getting its own session — is a property of `poll_user`
now, since the cron no longer loops in-process at all:

```python
# apps/api/tests/unit/test_worker_discovery.py — replace
# test_poll_all_sources_never_raises_and_continues_after_failure and
# test_poll_all_sources_gives_each_user_their_own_session with:
async def test_poll_user_records_failure_without_raising(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed(session, user)

    async def fake_poll_sources(*args: Any, **kwargs: Any) -> PollSummary:
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_tasks, "poll_sources", fake_poll_sources)
    ctx = ctx_for(session_factory, InMemoryEventBus(), engine)
    await worker_tasks.poll_user(ctx, str(user.id))  # must not raise despite the fetch failing


async def test_poll_user_opens_a_fresh_session_per_call(
    session_factory: async_sessionmaker[AsyncSession],
    session: AsyncSession,
    user: User,
    engine: AsyncEngine,
) -> None:
    """Regression guard for the shared-session bug Phase 0 already fixed: poll_user must call
    session_factory() fresh on every invocation, not hold one open across calls for different
    users. Fixes re-review item 7: the earlier version of this test only counted rows afterwards,
    which proves nothing about session identity -- this counts factory() invocations instead,
    which is what the Phase 0 bug (one shared AsyncSession, and therefore one identity map, across
    a whole per-user loop) was actually about.
    """
    other = await get_or_create_user(session, "other@example.com")
    await seed(session, user)
    await seed(session, other)
    await session.commit()

    call_count = 0
    real_factory = session_factory

    def counting_factory() -> Any:
        nonlocal call_count
        call_count += 1
        return real_factory()

    ctx = ctx_for(counting_factory, InMemoryEventBus(), engine)
    await worker_tasks.poll_user(ctx, str(user.id))
    await worker_tasks.poll_user(ctx, str(other.id))

    assert call_count == 2  # one fresh session per call, never reused across users
```

**(d) `apps/api/tests/unit/test_worker_tasks.py` — `test_registry`'s expected set:**

```python
# apps/api/tests/unit/test_worker_tasks.py — replace the set(TASKS) assertion
async def test_registry() -> None:
    assert set(TASKS) == {
        "tailor_job",
        "embed_blocks",
        "render_package_pdf",
        "poll_now",
        "poll_all_sources",
        "poll_user",
        "score_jobs",
        "rescore_jobs",
    }
    assert TASKS["tailor_job"] is tailor_job
    assert TASKS["render_package_pdf"] is render_package_pdf
```

- [ ] **Step 8: Add the PDF concurrency-1 gate**

```python
# apps/api/src/rhapto/worker/tasks.py — module-level, near the other module-level state
import asyncio as _asyncio  # already imported as `asyncio` above; no new import needed

_PDF_RENDER_LOCK = asyncio.Lock()
```

```python
# apps/api/src/rhapto/worker/tasks.py — render_package_pdf (previously lines 224-235)
async def render_package_pdf(ctx: dict[str, Any], package_id: str) -> None:
    """Render the PDF for an already-persisted package's DOCX, off the API's request path.

    Serialised process-wide: two concurrent LibreOffice invocations cost ~200-300MB each on top
    of the worker's ~1.87GB resident set, and max_jobs=2 means two PDF renders are otherwise
    reachable at once -- an OOM the box can already hit with one user and two queued packages
    (architecture.md §2.1).
    """
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    storage: PackageStorage = ctx["storage"]
    async with factory() as session:
        row = await session.get(Package, uuid.UUID(package_id))
        if row is None or row.docx_path is None:
            return
        async with _PDF_RENDER_LOCK:
            pdf = await asyncio.to_thread(storage.render_pdf, package_id, ctx["soffice_binary"])
        if pdf is not None:
            row.pdf_path = str(pdf)
        await session.commit()
```

Apply the same `async with _PDF_RENDER_LOCK:` wrap around the `storage.render_pdf` call inside
`tailor_job` (currently `asyncio.to_thread(storage.render_pdf, str(row.id), ctx["soffice_binary"])`,
around what is today `tailor_job`'s line 191-193) — the same LibreOffice invocation, reached from a
second call site.

- [ ] **Step 9: Delete the dead location-backfill code — and the tests that exercise it (re-review item 2)**

Deleting the code alone reds two files, verified in this revision by actually grepping rather than
asserting: `users_needing_location_backfill` is imported at module level by
`apps/api/tests/unit/test_scoring_service.py:15` and asserted against at `:235,238,242,246,251`;
`enqueue_location_backfill`/`_location_backfill_done` are exercised by
`test_startup_backfills_users_whose_jobs_predate_location_priority` (`test_worker_discovery.py:287-297`)
and `test_startup_backfill_never_fails_the_worker` (`:304-306`). All of this is deleted in the same
commit as the production code, not left for a later task to discover red.

```python
# apps/api/src/rhapto/worker/main.py — delete enqueue_location_backfill,
# _location_backfill_done, the `await enqueue_location_backfill(ctx)` call inside on_startup,
# and the `from rhapto.services.scoring import users_needing_location_backfill` import.
```

```python
# apps/api/src/rhapto/services/scoring.py — delete users_needing_location_backfill entirely
```

```python
# apps/api/tests/unit/test_worker_discovery.py — delete these two tests in full:
#   test_startup_backfills_users_whose_jobs_predate_location_priority (lines ~287-297)
#   test_startup_backfill_never_fails_the_worker (lines ~304-306)
# and the `RecordingRedis` class immediately above them if (and only if) grepping this file confirms
# no other test in it still uses that name — the new C4 fixture work (Step 7) added its own
# `RecordingRedis` inside `ctx_for`'s module, so check for a naming collision before assuming this
# one is safe to remove outright.
```

```python
# apps/api/tests/unit/test_scoring_service.py — delete `users_needing_location_backfill` from the
# `from rhapto.services.scoring import (...)` import block (lines ~9-15), and delete the five
# assertion lines at ~235,238,242,246,251 (and any test function whose body becomes empty as a
# result — confirm by reading the surrounding test bodies before deleting, since this plan has not
# reproduced them in full here).
```

Run: `grep -rn users_needing_location_backfill apps/api/src apps/api/tests` after all four edits
above — expect zero matches, confirming nothing was missed (the exact verification step the earlier
draft skipped).

- [ ] **Step 10: Write the concurrency-gate test — with real `Package` rows, in `tests/api/` (plan-review I3, re-review item 3)**

The earlier version of this test passed with or without the lock: `worker_ctx` has no `Package` rows,
so `render_package_pdf` returns at `row is None`, `fake_render_pdf` is never called, `max_concurrent`
stays `0`, and `assert max_concurrent <= 1` is trivially true before the lock exists. Fixed by
inserting two real `Package` rows (each needing a `Job` row for its `job_id` FK — verified
`Package.job_id` is `ForeignKey("jobs.id", ondelete="CASCADE")`, `db/models.py:213-215`) and by
asserting `== 1`, not `<= 1`, so a regression that removes the lock fails this test rather than
passing it by accident. **Placed in `apps/api/tests/api/`, not `tests/unit/`**: `worker_ctx` is
defined in `apps/api/tests/api/conftest.py:121` and is invisible to `tests/unit/` (pytest fixtures do
not cross directories) — the previous placement would have errored on fixture lookup before ever
exercising the lock, the same defect class the PDF gate's whole point is to catch:

```python
# apps/api/tests/api/test_pdf_concurrency_gate.py
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, Package, User
from rhapto.services.storage import PackageStorage
from rhapto.worker.tasks import render_package_pdf


async def _make_package(session: AsyncSession, user: User, storage: PackageStorage, tag: str) -> str:
    job = Job(
        user_id=user.id, source="manual", jd_text="A real job description. " * 6,
        dedupe_hash=f"hash-{tag}-{uuid.uuid4()}", discovered_at=datetime.now(UTC),
    )
    session.add(job)
    await session.flush()
    package = Package(
        user_id=user.id, job_id=job.id, track_id="pm", version=1, status="draft",
        resume_json={}, cover_note="", change_log="", guardrail_report_json={}, jd_extract_json={},
    )
    session.add(package)
    await session.flush()
    package.docx_path = str(storage.write_docx(str(package.id), b"fake docx bytes"))
    await session.commit()
    return str(package.id)


async def test_two_concurrent_renders_never_overlap(
    worker_ctx: dict[str, Any], user: User, session: AsyncSession, monkeypatch
) -> None:
    storage: PackageStorage = worker_ctx["storage"]
    session_factory: async_sessionmaker[AsyncSession] = worker_ctx["session_factory"]
    package_id_a = await _make_package(session, user, storage, "a")
    async with session_factory() as second_session:
        package_id_b = await _make_package(second_session, user, storage, "b")

    concurrent = 0
    max_concurrent = 0

    def fake_render_pdf(package_id: str, soffice_binary: str) -> None:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        time.sleep(0.05)
        concurrent -= 1
        return None

    # Patch the *instance*, not the class. `render_package_pdf` calls `storage.render_pdf(...)`;
    # patching PackageStorage.render_pdf at the class level makes that attribute lookup go through
    # the descriptor protocol, so Python binds `storage` as an implicit `self` and the call arrives
    # with three positional arguments against fake_render_pdf's two -- confirmed by actually running
    # it: `TypeError: fake_render_pdf() takes 2 positional arguments but 3 were given` (this test
    # failed to execute across three review rounds for exactly this reason). Assigning the plain
    # function directly to the instance's own `__dict__` skips the descriptor protocol entirely, so
    # the call reaches fake_render_pdf with exactly the two arguments it declares.
    monkeypatch.setattr(storage, "render_pdf", fake_render_pdf)
    await asyncio.gather(
        render_package_pdf(worker_ctx, package_id_a),
        render_package_pdf(worker_ctx, package_id_b),
    )
    assert max_concurrent == 1
```

Run this test once against the code from *before* Step 8's `_PDF_RENDER_LOCK` is added (temporarily
revert that one change) to confirm it fails first — `max_concurrent` should read `2` — per this plan's
TDD convention, then restore the lock and confirm it passes.

- [ ] **Step 11: Run the new tests, then the full suite**

Run: `pytest tests/unit/test_poll_fan_out.py tests/api/test_pdf_concurrency_gate.py tests/unit/test_worker_discovery.py tests/unit/test_worker_tasks.py tests/unit/test_scoring_service.py -v` — expect PASS, including every pre-existing test in the last three files.
Run: `pytest` — expect the full suite green.
Run: `ruff check .` and `mypy src` — expect clean.

- [ ] **Step 12: Commit**

```bash
git add apps/api/src/rhapto/worker/tasks.py apps/api/src/rhapto/worker/main.py \
  apps/api/src/rhapto/services/scoring.py \
  apps/api/tests/api/conftest.py \
  apps/api/tests/unit/test_worker_discovery.py apps/api/tests/unit/test_worker_tasks.py \
  apps/api/tests/unit/test_scoring_service.py \
  apps/api/tests/unit/test_poll_fan_out.py apps/api/tests/api/test_pdf_concurrency_gate.py
git commit -m "$(cat <<'EOF'
Per-user poll fan-out, advisory lock, PDF concurrency-1 gate (A4)

poll_all_sources now enqueues one poll_user arq job per user and returns immediately, instead of
polling every user inline inside one 600s task -- two users used to exceed job_timeout and the
second user's poll was killed mid-run. poll_user and poll_now both take a per-user Postgres
advisory lock so a cron poll and a hand-triggered poll can never interleave for the same account.
render_package_pdf and tailor_job's PDF step share a process-wide asyncio.Lock, since two
concurrent LibreOffice renders can exceed the worker's 2GB cap, proven this time with real Package
rows in tests/api/ (where the worker_ctx fixture it needs actually lives -- re-review item 3)
rather than a vacuously-passing test in the wrong directory (plan-review I3). Deleted the
location-tier backfill one-shot, five migrations past its usefulness, along with the four tests
across two files that exercised it (re-review item 2 -- verified by grep, not asserted).

worker_ctx and ctx_for now carry engine/redis doubles so the new ctx["engine"]/ctx["redis"] reads
don't break every existing poll_now/poll_all_sources test (plan-review C4); the two
poll_all_sources-level failure/session tests moved to poll_user, since the cron no longer polls
in-process at all.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 6 (a fan-out is what makes account #2's poll not corrupt/kill
account #1's), 10 (contained cost per user is meaningless if one user's poll starves another's).

---

## Task 5 (A5): The full first screen — an idempotent seed, triggered once per session, never inside `current_user`

**This task changed shape after plan review rejected the earlier version outright**, on three
findings, all fixed below:

- **C5 — the backfill could violate `uq_jobs_user_source_external`, permanently bricking sign-in.**
  Verified: `apps/api/alembic/versions/0002_discovery.py:33-40` creates a **partial unique index**
  `uq_jobs_user_source_external (user_id, source, external_id) WHERE external_id IS NOT NULL` — a
  constraint the previous draft of this task checked for `(user_id, dedupe_hash)` but never checked
  for this one. `SELECT DISTINCT ON (dedupe_hash)` collapses by *text hash*, not by source identity:
  two rows for the same `(source, external_id)` whose JD text changed between polls have two different
  `dedupe_hash` values, both survive that `DISTINCT ON`, and inserting both for one new account raises
  a unique violation. Fixed in Step 3 by deduping on `(source, COALESCE(external_id, dedupe_hash))`
  instead, plus a second `NOT EXISTS` guard on `(user_id, source, external_id)` and a bare `ON CONFLICT
  DO NOTHING` as a last-resort race guard — the plan reviewer's ruling was explicit that these three
  are not alternatives to each other.
- **C6 — the seed must never run inside `current_user`.** The previous draft ran the backfill (and a
  second `get_or_create_user`-style read) inside the dependency every single endpoint in the API
  depends on: any endpoint could pay for a multi-hundred-row `INSERT ... SELECT`, and any failure in
  it presented as an auth failure. Fixed by leaving `current_user` exactly as Task 3 wrote it (get-
  or-create, nothing else) and adding a **separate, dedicated `POST /api/v1/me/bootstrap` endpoint**
  the web app calls once per session, gated by `Depends(current_user)` like any other endpoint rather
  than living inside the dependency itself.
- **I1 — `derive_searches` at first sign-in was guaranteed to be a no-op.** Verified:
  `services/discovery/search.py:62-92` creates one saved search *per track*
  (`for track in await profile_repo.list_tracks(...)`), and a brand-new account has zero tracks. The
  previous draft called it from the seed step anyway, which did nothing and implied a promise
  ("the cron picks the account up on its next interval") that wasn't actually kept. This task **does
  not call `derive_searches`**; Phase D's onboarding flow (out of scope, owned elsewhere) is the
  correct place to call it, once the user has tracks to derive searches from — stated here so Role 4
  and Phase D's author both see the gap named rather than silently absent.

Also fixes **I10** — the earlier draft's `backfill_public_jobs` imported `SOURCES` directly
(`from rhapto.services.discovery.sources import SOURCES`), and that package's `__init__.py:53-65`
imports eleven concrete source modules at import time purely for `@register` side effects, dragging
the whole discovery stack into the DB repository layer. Fixed by having the repository function accept
`public_sources: Sequence[str]` as a parameter; the caller (the new router endpoint) supplies
`list(SOURCES.keys())`. And **I2** — the previous draft's own test called `list_jobs(...)` as if it
returned bare `Job` rows; verified `apps/api/src/rhapto/db/repositories/jobs.py:63` declares
`list_jobs(...) -> list[tuple[Job, str | None]]` (job, search name), so the fixed test below indexes
`rows[0][0]`.

Verified before writing: `apps/api/src/rhapto/db/models.py:164-205` (`Job` has 27 columns total,
counting `UserScopedMixin.user_id` and `TimestampMixin`'s two columns; no unique constraint on
`(user_id, dedupe_hash)` exists); `apps/api/src/rhapto/services/discovery/sources/__init__.py:16`
(`SOURCES: dict[str, SourceClass] = {}`, the positive-allowlist registry); `apps/api/src/rhapto/services/discovery/poller.py:45`
(`INGEST_MAX_AGE_DAYS = 90`); `apps/api/src/rhapto/db/repositories/jobs.py:16-40` (`create_job`
defaults `source="manual"`, confirming `"manual"` is never in `SOURCES`); `apps/api/src/rhapto/db/repositories/jobs.py:63,144-151,180`
(`list_jobs`'s signature and its default `bucket == "fit"` **already** including `Job.best_fit.is_(None)`
rows, ordered `nulls_last` rather than hidden); `apps/web/src/components/ui/fit-ring.tsx:42-56`
(**already** renders a `null` fit as a dashed ring with `title="Not scored yet"` rather than hiding
the card) — **both of the architecture's "must not silently no-op" first-screen requirements are
already satisfied by existing code**, confirmed here with a regression test rather than new product
code; `apps/api/src/rhapto/api/routers/meta.py` (the router `POST /api/v1/me/bootstrap` is added to);
`User.seeded_at` (added by Task 1's migration `0011`, unused until now).

**Files:**
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py` (new `backfill_public_jobs`, takes
  `public_sources` as a parameter — I10)
- Modify: `apps/api/src/rhapto/api/routers/meta.py` (new `POST /me/bootstrap` endpoint)
- Modify: `apps/api/src/rhapto/api/schemas.py` (`BootstrapOut`)
- Modify: `apps/web/src/lib/api/queries.ts` (a `useBootstrap` mutation)
- Modify: `apps/web/src/app/providers.tsx` (or wherever the app-wide query client lives — call the
  bootstrap mutation once per authenticated session; the implementer confirms the exact file by
  reading `apps/web/src/app/providers.tsx` and `apps/web/src/app/layout.tsx` before choosing)
- Modify: `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts` (regenerated)
- Test: `apps/api/tests/db/test_backfill_public_jobs.py`
- Test: `apps/api/tests/api/test_access_mode.py` (extend: the bootstrap endpoint, end-to-end)

**Interfaces:**
- Consumes: `is_allowed_email`/`get_or_create_user` (Task 3, unchanged by this task), `User.seeded_at`
  (Task 1).
- Produces:
  ```python
  # rhapto/db/repositories/jobs.py
  async def backfill_public_jobs(
      session: AsyncSession, user_id: uuid.UUID, *, public_sources: Sequence[str]
  ) -> int:
      """Row count inserted. Idempotent: safe to call more than once for the same user, and safe
      under concurrent callers (bare ON CONFLICT DO NOTHING)."""

  # rhapto/api/schemas.py
  class BootstrapOut(BaseModel):
      seeded: bool  # True the one time this call actually ran the backfill; False every other time
  ```
  `POST /api/v1/me/bootstrap` is the only caller of `backfill_public_jobs` in this plan. No other
  task depends on either.

- [ ] **Step 1: Write the failing backfill tests**

```python
# apps/api/tests/db/test_backfill_public_jobs.py
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job
from rhapto.db.repositories.jobs import backfill_public_jobs
from rhapto.db.repositories.users import get_or_create_user


async def _seed_job(session: AsyncSession, owner_id: uuid.UUID, **overrides) -> Job:
    defaults = dict(
        user_id=owner_id,
        source="greenhouse",
        external_id="ext-1",
        url="https://boards.example.com/1",
        company="Acme",
        title="Engineer",
        location="Remote",
        posted_at=datetime.now(UTC),
        jd_text="A real job description, long enough to pass validation. " * 3,
        jd_embedding=[0.1] * 384,
        dedupe_hash=f"hash-{uuid.uuid4()}",
        identity_hash=f"identity-{uuid.uuid4()}",
        discovered_at=datetime.now(UTC),
        miss_count=0,
    )
    defaults.update(overrides)
    job = Job(**defaults)
    session.add(job)
    await session.flush()
    return job


PUBLIC_SOURCES = ["greenhouse", "lever"]  # real SOURCES keys used only as test fixtures here (I10:
                                           # the repository function itself never imports SOURCES)


async def test_copies_a_public_job_into_the_new_account(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id)
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 1
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1
    assert rows[0].jd_embedding is not None  # the cached vector rides along


async def test_never_copies_a_manual_job(session: AsyncSession) -> None:
    """The highest-consequence line of SQL in Phase A: a hand-pasted recruiter email must never
    reach a second account."""
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="manual", external_id=None, url=None)
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 0
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert rows == []


async def test_excluded_columns_are_never_copied(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    other_owner_job = await _seed_job(session, owner.id, source="greenhouse")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    another_owner_track_job = await _seed_job(
        session,
        owner.id,
        source="lever",
        external_id="ext-2",
        dedupe_hash=f"hash-{uuid.uuid4()}",
        best_fit=88,
        best_track_id="pm",
        location_tier="preferred",
        hidden_at=datetime.now(UTC),
        rescued=True,
        extracted_json={"company": "Acme", "title": "Engineer", "context_tags": []},
        repost_of=other_owner_job.id,
    )
    await session.commit()

    await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    for row in rows:
        assert row.extracted_json is None
        assert row.repost_of is None
        assert row.best_fit is None
        assert row.best_track_id is None
        assert row.location_tier is None
        assert row.hidden_at is None
        assert row.rescued is False
        assert row.search_id is None


async def test_excludes_unlisted_and_stale_jobs(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse", unlisted_at=datetime.now(UTC))
    await _seed_job(
        session,
        owner.id,
        source="lever",
        external_id="ext-old",
        dedupe_hash=f"hash-{uuid.uuid4()}",
        posted_at=datetime.now(UTC) - timedelta(days=91),
    )
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()
    assert count == 0


async def test_is_idempotent(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse")
    await session.commit()

    first = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()
    second = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert first == 1
    assert second == 0
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1


async def test_two_rows_sharing_source_and_external_id_with_different_dedupe_hash_do_not_collide(
    session: AsyncSession,
) -> None:
    """Fixes plan-review C5: a JD whose text (and therefore dedupe_hash) changed between two polls
    of the same posting used to survive `DISTINCT ON (dedupe_hash)` as two rows, both sharing
    (source, external_id) -- violating uq_jobs_user_source_external the moment both were inserted
    for one new account and 500ing the request that was supposed to create it."""
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(
        session, owner.id, source="greenhouse", external_id="shared-ext",
        dedupe_hash=f"hash-old-{uuid.uuid4()}", discovered_at=datetime.now(UTC) - timedelta(days=2),
    )
    await _seed_job(
        session, owner.id, source="greenhouse", external_id="shared-ext",
        dedupe_hash=f"hash-new-{uuid.uuid4()}", discovered_at=datetime.now(UTC),
    )
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    assert count == 1  # never raises, and collapses to exactly one row for the shared external_id
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1


async def test_unscored_backfilled_rows_stay_in_the_default_fit_bucket(session: AsyncSession) -> None:
    """Pins the existing (pre-A5) behaviour this task relies on rather than reimplementing:
    best_fit IS NULL rows are not filtered out of the default grid view. Fixes plan-review I2:
    list_jobs returns list[tuple[Job, str | None]] (job, search name), verified against
    db/repositories/jobs.py:63 -- the earlier draft of this test indexed it as if it returned bare
    Job rows."""
    from rhapto.db.repositories.jobs import list_jobs

    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse")
    await session.commit()
    await backfill_public_jobs(session, newcomer.id, public_sources=PUBLIC_SOURCES)
    await session.commit()

    rows = await list_jobs(session, newcomer.id, bucket="fit")
    assert len(rows) == 1
    job, _search_name = rows[0]
    assert job.best_fit is None
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `pytest tests/db/test_backfill_public_jobs.py -v`
Expected: FAIL — `backfill_public_jobs` does not exist yet (import error).

- [ ] **Step 3: Implement `backfill_public_jobs` — fixing plan-review C5 and I10**

```python
# apps/api/src/rhapto/db/repositories/jobs.py — new function
from collections.abc import Sequence

PUBLIC_BACKFILL_MAX_AGE_DAYS = 90  # matches services.discovery.poller.INGEST_MAX_AGE_DAYS


async def backfill_public_jobs(
    session: AsyncSession, user_id: uuid.UUID, *, public_sources: Sequence[str]
) -> int:
    """Seed a brand-new account's first screen with every live public-source job already
    discovered on this instance, cached embedding included, at zero LLM/embedding cost.

    `public_sources` is supplied by the caller as `list(SOURCES.keys())` -- this module takes no
    import on `rhapto.services.discovery.sources`, whose `__init__.py` imports eleven concrete
    source modules purely for `@register` side effects (plan-review I10); the positive allowlist
    is still enforced, just constructed one layer up.

    Does not copy: extracted_json (another user's ungoverned LLM output), repost_of/search_id
    (foreign keys into another user's own rows), best_fit/best_track_id/location_tier/hidden_at/
    rescued (another user's opinions, meaningless for a new account).

    Idempotent three ways, none of them optional (plan-review C5 -- the reviewer's ruling was that
    these are not alternatives to each other):
    1. The inner `DISTINCT ON (source, COALESCE(external_id, dedupe_hash))` collapses by *source
       identity* first, not by text hash -- two rows for the same (source, external_id) whose JD
       text changed between polls (and therefore have different dedupe_hash values) collapse to
       one, rather than both surviving and violating `uq_jobs_user_source_external`
       (`(user_id, source, external_id) WHERE external_id IS NOT NULL`,
       `alembic/versions/0002_discovery.py:33-40`) the moment both are inserted for the new user.
    2. `NOT EXISTS` guards both `(user_id, dedupe_hash)` and `(user_id, source, external_id)`, so a
       retried call -- or a second call whose source data has since changed hash -- inserts nothing
       already present under either key.
    3. A bare `ON CONFLICT DO NOTHING` (no target needed) is the last-resort guard against two
       concurrent callers both passing the `NOT EXISTS` checks before either commits -- the
       classic idempotency race a `NOT EXISTS` clause alone cannot close.
    """
    if not public_sources:
        return 0
    cutoff = datetime.now(UTC) - timedelta(days=PUBLIC_BACKFILL_MAX_AGE_DAYS)
    result = await session.execute(
        text(
            """
            INSERT INTO jobs (
                id, user_id, source, external_id, url, company, title, location,
                posted_at, salary_text, jd_text, jd_embedding, dedupe_hash, identity_hash,
                discovered_at, miss_count, created_at, updated_at
            )
            SELECT gen_random_uuid(), :user_id, j.source, j.external_id, j.url, j.company,
                   j.title, j.location, j.posted_at, j.salary_text, j.jd_text, j.jd_embedding,
                   j.dedupe_hash, j.identity_hash, now(), 0, now(), now()
            FROM (
                SELECT DISTINCT ON (source, COALESCE(external_id, dedupe_hash)) *
                FROM jobs
                WHERE source = ANY(:public_sources)
                  AND unlisted_at IS NULL
                  AND (posted_at IS NULL OR posted_at > :cutoff)
                ORDER BY source, COALESCE(external_id, dedupe_hash), discovered_at ASC
            ) j
            WHERE NOT EXISTS (
                SELECT 1 FROM jobs existing
                WHERE existing.user_id = :user_id AND existing.dedupe_hash = j.dedupe_hash
            )
            AND NOT EXISTS (
                SELECT 1 FROM jobs existing2
                WHERE existing2.user_id = :user_id AND existing2.source = j.source
                  AND j.external_id IS NOT NULL AND existing2.external_id = j.external_id
            )
            ON CONFLICT DO NOTHING
            """
        ),
        {"user_id": str(user_id), "public_sources": list(public_sources), "cutoff": cutoff},
    )
    return result.rowcount or 0
```

Add `from sqlalchemy import text` and `from collections.abc import Sequence` to `jobs.py`'s imports
(verified `datetime`, `UTC`, `timedelta` are already imported at the top of the file; `text` is not —
add it to the existing `from sqlalchemy import CursorResult, and_, delete, func, not_, nulls_last,
or_, select` line).

- [ ] **Step 4: Run the backfill tests again**

Run: `pytest tests/db/test_backfill_public_jobs.py -v`
Expected: all eight PASS, including the new `uq_jobs_user_source_external` regression test.

- [ ] **Step 5: Add `POST /api/v1/me/bootstrap` — fixing plan-review C6**

`current_user` is not touched by this step at all; it stays exactly as Task 3 left it.

```python
# apps/api/src/rhapto/api/schemas.py — new response model
class BootstrapOut(BaseModel):
    seeded: bool
```

```python
# apps/api/src/rhapto/api/routers/meta.py — new endpoint
from sqlalchemy import text

from rhapto.db.repositories.jobs import backfill_public_jobs
from rhapto.services.discovery.sources import SOURCES


@router.post("/me/bootstrap", response_model=BootstrapOut)
async def bootstrap(
    user_id: Annotated[uuid.UUID, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BootstrapOut:
    """Idempotent, cheap on every call after the first: the web app calls this once per session
    (Step 7), and it only ever does real work the one time `users.seeded_at` is still NULL. Kept
    entirely out of `current_user` (plan-review C6) so no other endpoint's request pays for it and
    no failure here can present as an auth failure.

    The claim is a single atomic `UPDATE ... WHERE seeded_at IS NULL RETURNING id`, not a read-then-
    write (re-review's adopted recommendation, replacing this plan's earlier "no lock needed"
    argument): Postgres's row-level locking means at most one of two concurrent callers ever gets a
    row back, so the backfill runs exactly once per account even under a real race -- no advisory
    lock, no new engine-access plumbing, and no residual "cosmetic duplicate" risk for
    `external_id IS NULL` rows, which is what the check-then-write version could not close.
    """
    claim = await session.execute(
        text("UPDATE users SET seeded_at = now() WHERE id = :uid AND seeded_at IS NULL RETURNING id"),
        {"uid": str(user_id)},
    )
    if claim.first() is None:
        await session.rollback()
        return BootstrapOut(seeded=False)
    await backfill_public_jobs(session, user_id, public_sources=list(SOURCES.keys()))
    await session.commit()
    return BootstrapOut(seeded=True)
```

Add `import uuid` to `meta.py`'s imports if not already present (verified `meta.py` currently imports
`uuid` already for `current_user`'s return type).

- [ ] **Step 6: Write the endpoint test**

```python
# apps/api/tests/api/test_access_mode.py — append
async def test_bootstrap_seeds_a_new_accounts_first_screen_exactly_once(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch, session_factory
) -> None:
    from datetime import UTC, datetime

    from rhapto.db.models import Job
    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as session:
        owner = await get_or_create_user(session, "owner@example.com")
        session.add(
            Job(
                user_id=owner.id, source="greenhouse", external_id="e1", url="https://x/1",
                company="Acme", title="Engineer", location="Remote",
                jd_text="A real job description, long enough. " * 3,
                dedupe_hash="hash-e2e-1", discovered_at=datetime.now(UTC), miss_count=0,
            )
        )
        await session.commit()

    state: AppState = app.state.rhapto
    state.settings.rhapto_auth_mode = "access"
    state.settings.rhapto_access_team = "test-team"
    state.settings.rhapto_access_aud = "test-aud"
    state.settings.rhapto_allowed_emails = "newcomer@example.com"

    from rhapto.api import auth as auth_module

    _, public_key = rsa_keypair
    cache = auth_module.JwksCache("http://unused")
    cache._keys["test-kid"] = public_key
    cache._fetched_at = time.monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("newcomer@example.com")
    headers = {"Cf-Access-Jwt-Assertion": token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        me_response = await c.get("/api/v1/me", headers=headers)
        assert me_response.status_code == 200
        jobs_before = await c.get("/api/v1/jobs", headers=headers)
        assert jobs_before.json() == []  # not seeded yet -- current_user alone never seeds

        first = await c.post("/api/v1/me/bootstrap", headers=headers)
        assert first.status_code == 200 and first.json()["seeded"] is True

        jobs_after = await c.get("/api/v1/jobs", headers=headers)
        assert len(jobs_after.json()) == 1
        assert jobs_after.json()[0]["best_fit"] is None

        second = await c.post("/api/v1/me/bootstrap", headers=headers)
        assert second.status_code == 200 and second.json()["seeded"] is False
```

(`import httpx`, `from rhapto.api.deps import AppState`, and `import time` are already imported
earlier in this test file, per Task 3.)

Closes the remaining gap: nothing yet proves the claim itself is atomic under a real race, only that
sequential calls behave correctly. This test drives the exact `UPDATE ... RETURNING` statement from
two concurrent sessions on the same row and asserts exactly one of them claims it:

```python
# apps/api/tests/db/test_backfill_public_jobs.py — append (co-located with the other seed-related
# tests, since it exercises the same idempotency marker `backfill_public_jobs`'s caller relies on)
async def test_concurrent_seed_claims_result_in_exactly_one_claim(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """This is the statement Task 5 Step 5's POST /me/bootstrap runs to decide whether to seed.
    Proves it directly, at the SQL level, under a real race: two concurrent transactions racing on
    the same row's `seeded_at IS NULL` claim must not both succeed. Postgres's row lock makes the
    loser's UPDATE block until the winner commits, then re-evaluate WHERE against the now-non-NULL
    value and match zero rows -- this is what makes first sign-in race-safe rather than merely
    idempotent.
    """
    import asyncio

    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as setup:
        user = await get_or_create_user(setup, "racer@example.com")
        await setup.commit()
        user_id = user.id

    async def claim() -> bool:
        async with session_factory() as session:
            result = await session.execute(
                text(
                    "UPDATE users SET seeded_at = now() WHERE id = :uid AND seeded_at IS NULL "
                    "RETURNING id"
                ),
                {"uid": str(user_id)},
            )
            got = result.first() is not None
            await session.commit()
            return got

    results = await asyncio.gather(claim(), claim())
    assert sorted(results) == [False, True]
```

Add `from sqlalchemy import text` and `from sqlalchemy.ext.asyncio import async_sessionmaker` to
`test_backfill_public_jobs.py`'s imports if not already present. Run:
`pytest tests/db/test_backfill_public_jobs.py -k concurrent_seed -v` — expect PASS; run it a few
times locally if flaky-under-load is a concern, since it depends on Postgres actually serialising
the two `UPDATE`s rather than on any Python-side synchronisation.

- [ ] **Step 7: Wire the web app to call `/me/bootstrap` once per session**

```typescript
// apps/web/src/lib/api/queries.ts — new mutation
export function useBootstrap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => unwrap(apiClient().POST("/api/v1/me/bootstrap")),
    onSuccess: (data) => {
      if (data.seeded) {
        void queryClient.invalidateQueries({ queryKey: ["jobs"] });
      }
    },
  });
}
```

```typescript
// apps/web/src/app/providers.tsx (or the file the implementer confirms holds the top-level
// QueryClientProvider, by reading providers.tsx and layout.tsx first) — call it once per mount
// when /me has succeeded:
"use client";
import { useEffect } from "react";
import { useMe, useBootstrap } from "@/lib/api/queries";

function Bootstrapper() {
  const me = useMe();
  const bootstrap = useBootstrap();
  useEffect(() => {
    if (me.isSuccess && bootstrap.isIdle) {
      bootstrap.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fire once per successful /me, not on every render
  }, [me.isSuccess]);
  return null;
}
```

Mount `<Bootstrapper />` once, inside the existing top-level providers tree, alongside (not replacing)
whatever `QueryClientProvider` already wraps the app — the implementer locates the exact insertion
point by reading `apps/web/src/app/providers.tsx` before adding it, since this plan has not read that
file's current contents in full and must not guess its structure.

- [ ] **Step 8: Regenerate the OpenAPI document and the web client's types**

Run (from `apps/api`): `python scripts/export_openapi.py`.
Run (from `apps/web`): `pnpm gen:api`.

- [ ] **Step 9: Run the new tests, then the full suites**

Run: `pytest tests/db/test_backfill_public_jobs.py tests/api/test_access_mode.py -v` — expect PASS.
Run: `pytest` — expect green.
Run: `ruff check .` and `mypy src` — expect clean.
Run (apps/web): `pnpm test`, `pnpm lint`, `pnpm typecheck` — expect green.

- [ ] **Step 10: Commit**

```bash
git add apps/api/src/rhapto/db/repositories/jobs.py apps/api/src/rhapto/api/routers/meta.py \
  apps/api/src/rhapto/api/schemas.py packages/schemas/openapi.json \
  apps/web/src/lib/api/schema.d.ts apps/web/src/lib/api/queries.ts apps/web/src/app/providers.tsx \
  apps/api/tests/db/test_backfill_public_jobs.py apps/api/tests/api/test_access_mode.py
git commit -m "$(cat <<'EOF'
Seed a new account's first screen via an idempotent, dedicated bootstrap endpoint (A5)

backfill_public_jobs copies every live public-source job (positive SOURCES allowlist supplied by
the caller, never imported by the DB layer -- plan-review I10) into a new account in one
INSERT ... SELECT, cached jd_embedding included, at zero LLM/embedding cost -- deduping on source
identity rather than text hash so a JD that changed between polls can never violate
uq_jobs_user_source_external (plan-review C5), with NOT EXISTS plus a bare ON CONFLICT DO NOTHING
as defense in depth against concurrent callers. Triggered by a new POST /api/v1/me/bootstrap
endpoint the web app calls once per session, never from inside current_user (plan-review C6) --
so no other endpoint pays for it and no failure here can look like an auth failure. Does not call
derive_searches (plan-review I1): a brand-new account has zero tracks, so that call was
provably a no-op; Phase D's onboarding flow is the correct place for it once tracks exist.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 1, 3 (a full grid rather than an empty one — the setup-flow wizard
itself is Phase D), 6, 7 (no verified fact or block crosses accounts; only a source's own public JD
text is copied), 15 (the owner's own job rows are read-only source data for the copy, never mutated).

---

## Task 6 (B1a): `last_seen_at` throttling, `inactive_accounts`, prune dry-run

> **AMENDMENT 2026-09-25 — test isolation. Read before writing any test in this task.**
>
> Every test below takes `migrated_db`. That fixture (`apps/api/tests/conftest.py:127`) returns a
> migrated database URL and **does not clean it**; `session_factory`
> (`conftest.py:142-147`) truncates **on teardown only**. So a test that seeds rows through its own
> engine leaves them behind, and the *next* invocation starts dirty.
>
> This already bit Task 3: `tests/unit/test_accounts_set_email.py` was copied verbatim from this plan
> and collided across runs — it passed on run 1 and failed on run 2. Adding `session_factory` as a
> truncating parameter was not sufficient, because teardown cleanup cannot help the first run against
> an already-dirty database.
>
> **This task is more exposed than Task 3 was**, because the subject under test *is which accounts
> exist*: a leftover account makes `prune`/`inactive_accounts`/`delete` assert against rows it did not
> create, and the failure will look like a logic bug in the pruning code rather than a dirty database.
>
> Therefore, for every test in this task:
> 1. Depend on a fixture that **truncates before the test body runs**, not only after. Task 3's fix
>    round may already have added one while closing finding N2 — check `conftest.py` first and reuse it
>    rather than adding a second.
> 2. Seed **per-run unique** email addresses (`f"{uuid4().hex}@example.com"`), so two invocations cannot
>    collide even if cleanup is skipped or a run is interrupted.
> 3. Assert on rows **you** created — by the unique address — never on a total count of `users`.


Verified before writing: `users.last_seen_at`/`users.exempt_from_pruning` exist as of migration
`0011` (Task 1); no code reads or writes either column yet (grepped); `apps/api/src/rhapto/cli/main.py`
has no `accounts` sub-app before Task 3 adds `set-email` — this task adds `prune` to that same
sub-app.

This task also fixes two plan-review findings: **I5** (`mark_seen` must not add a `SELECT` to every
request — a single atomic `UPDATE` replaces the read-then-write) and part of **I6** (nothing set
`exempt_from_pruning`, and `MeOut` had no way for the web app to warn a returning user before their
account is pruned).

**Files:**
- Create: `apps/api/src/rhapto/services/accounts.py`
- Modify: `apps/api/src/rhapto/api/deps.py` (`current_user`: fire-and-forget `mark_seen` call)
- Modify: `apps/api/src/rhapto/config.py` (`rhapto_inactive_days`)
- Modify: `apps/api/src/rhapto/cli/main.py` (`accounts prune --dry-run`, `accounts exempt`)
- Modify: `apps/api/src/rhapto/api/schemas.py` (`MeOut.deletion_due_at`)
- Modify: `apps/api/src/rhapto/api/routers/meta.py` (`me()` computes it)
- Modify: `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts` (regenerated)
- Create: `apps/web/src/components/shell/DeletionBanner.tsx` (the day-60 warning)
- Modify: `apps/web/src/components/jobs/TailorButton.test.tsx` (its two `MeOut` literals gain
  `deletion_due_at`, alongside the `auth_mode` Task 1 already added — re-review finding 1)
- Test: `apps/api/tests/unit/test_accounts_lifecycle.py`
- Test: `apps/api/tests/unit/test_accounts_prune.py` (not `tests/cli/` — plan-review I11, same fix as
  Task 3)
- Test: `apps/web/src/components/shell/DeletionBanner.test.tsx`

**Interfaces:**
- Consumes: `User.last_seen_at`, `User.exempt_from_pruning` (Task 1).
- Produces:
  ```python
  # rhapto/services/accounts.py
  async def mark_seen(session: AsyncSession, user_id: uuid.UUID) -> None: ...
  async def inactive_accounts(session: AsyncSession, cutoff: datetime) -> list[User]: ...
  def would_delete_everyone(all_user_ids: Sequence[uuid.UUID], to_delete_ids: Sequence[uuid.UUID]) -> bool: ...
  ```
  Task 7 consumes all three, plus adds `delete_account`/`sweep_orphan_files` to this same module.
  `MeOut.deletion_due_at: datetime | None` (new field, `None` when exempt or not yet computable) is
  consumed by the new `DeletionBanner` component this task also adds.

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/unit/test_accounts_lifecycle.py
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.repositories.users import get_or_create_user
from rhapto.services.accounts import inactive_accounts, mark_seen


async def test_mark_seen_updates_a_stale_timestamp(session: AsyncSession) -> None:
    user = await get_or_create_user(session, "stale@example.com")
    user.last_seen_at = datetime.now(UTC) - timedelta(hours=2)
    await session.commit()

    await mark_seen(session, user.id)
    await session.commit()
    await session.refresh(user)
    assert datetime.now(UTC) - user.last_seen_at < timedelta(minutes=1)


async def test_mark_seen_is_throttled_within_an_hour(session: AsyncSession) -> None:
    user = await get_or_create_user(session, "recent@example.com")
    recent = datetime.now(UTC) - timedelta(minutes=5)
    user.last_seen_at = recent
    await session.commit()

    await mark_seen(session, user.id)
    await session.commit()
    await session.refresh(user)
    assert user.last_seen_at == recent


async def test_inactive_accounts_excludes_exempt_users(session: AsyncSession) -> None:
    stale = await get_or_create_user(session, "gone@example.com")
    stale.last_seen_at = datetime.now(UTC) - timedelta(days=100)
    exempt_stale = await get_or_create_user(session, "owner@example.com")
    exempt_stale.last_seen_at = datetime.now(UTC) - timedelta(days=100)
    exempt_stale.exempt_from_pruning = True
    fresh = await get_or_create_user(session, "active@example.com")
    fresh.last_seen_at = datetime.now(UTC)
    await session.commit()

    cutoff = datetime.now(UTC) - timedelta(days=90)
    result = await inactive_accounts(session, cutoff)
    assert {u.email for u in result} == {"gone@example.com"}
```

- [ ] **Step 2: Run to see it fail**

Run: `pytest tests/unit/test_accounts_lifecycle.py -v`
Expected: FAIL — `rhapto.services.accounts` does not exist.

- [ ] **Step 3: Implement `services/accounts.py` — `mark_seen` as one atomic `UPDATE` (plan-review I5)**

The earlier draft did `session.get` (a `SELECT`) then a conditional attribute write — an extra
`SELECT` on every authenticated request in both modes, and a read-then-write that is not atomic under
concurrent requests for the same user. Fixed with a single `UPDATE ... WHERE ... AND last_seen_at <
now() - interval '1 hour'`: the database itself decides whether the row needs touching, in one
round trip, and two concurrent requests for the same user race safely (whichever commits first wins;
the second's `WHERE` clause simply matches zero rows).

```python
# apps/api/src/rhapto/services/accounts.py
from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User

logger = logging.getLogger("rhapto.services.accounts")


async def mark_seen(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Move last_seen_at to now(), but only when it is already more than an hour stale -- one
    atomic UPDATE, no preceding SELECT (plan-review I5). Called from current_user on every
    authenticated request; a failure here must never fail the request it rides along with, so the
    caller wraps this in a try/except (architecture.md §4.1).
    """
    await session.execute(
        text(
            "UPDATE users SET last_seen_at = now() "
            "WHERE id = :uid AND last_seen_at < now() - interval '1 hour'"
        ),
        {"uid": str(user_id)},
    )


async def inactive_accounts(session: AsyncSession, cutoff: datetime) -> list[User]:
    """Every non-exempt account whose last_seen_at is older than `cutoff`."""
    return list(
        await session.scalars(
            select(User).where(User.last_seen_at < cutoff, User.exempt_from_pruning.is_(False))
        )
    )


def would_delete_everyone(
    all_user_ids: Sequence[uuid.UUID], to_delete_ids: Sequence[uuid.UUID]
) -> bool:
    """True iff pruning `to_delete_ids` would leave zero accounts on the instance -- the last-
    account guard plan-review I6 asked for. A misconfigured RHAPTO_INACTIVE_DAYS or a period of
    CLI-only use (which never calls mark_seen) must never be able to silently empty the instance;
    both the CLI's --yes path and the daily cron (Task 7) check this before deleting anything.
    """
    return bool(all_user_ids) and set(all_user_ids) <= set(to_delete_ids)
```

- [ ] **Step 4: Run the tests again**

Run: `pytest tests/unit/test_accounts_lifecycle.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `mark_seen` into `current_user`, fire-and-forget**

**Fixes a stale cross-reference from the last revision** (it pointed at "Task 5's version of
`current_user`" and a `return existing.id` that exist in no version of the function — Task 5
deliberately never touches `current_user`; that was the whole point of the C6 fix). The function this
step edits is exactly the one Task 3 Step 9 wrote: token branch returns `state.user_id`, access branch
ends `return user.id`, and there is no other return in it. **Also fixes re-review breakage item 6**:
the earlier `except` swallowed the error with no `rollback()`, which leaves the request-scoped session
in an aborted transaction after any failed `UPDATE` — the handler's *own* queries then fail too,
turning a should-be-invisible side-effect failure into a 500 on the path C6 exists to keep safe.

```python
# apps/api/src/rhapto/api/deps.py — current_user (Task 3 Step 9's version), both returns
from rhapto.services.accounts import mark_seen


async def current_user(
    request: Request,
    principal: Annotated[Principal, Depends(resolve_principal)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> uuid.UUID:
    state = get_state(request)
    if principal.mode == "token":
        if state.user_id is None:
            raise HTTPException(status_code=503, detail="server not ready")
        await _mark_seen_best_effort(session, state.user_id)
        return state.user_id
    settings = state.settings
    if not is_allowed_email(
        principal.email, settings.rhapto_allowed_emails, settings.rhapto_allowed_email_domains
    ):
        raise HTTPException(status_code=403, detail="this instance is invite-only")
    user = await get_or_create_user(session, principal.email)
    await session.commit()
    await _mark_seen_best_effort(session, user.id)
    return user.id


async def _mark_seen_best_effort(session: AsyncSession, user_id: uuid.UUID) -> None:
    """mark_seen must never fail the request it rides along with (architecture.md §4.1). On
    failure it must also roll back -- an uncommitted, unrolled-back UPDATE leaves the session in an
    aborted transaction, and every query the actual endpoint handler runs afterwards would then
    fail too (re-review item 6)."""
    try:
        await mark_seen(session, user_id)
        await session.commit()
    except Exception:
        logger.exception("mark_seen failed for user %s; continuing the request", user_id)
        await session.rollback()
```

(token mode's `current_user` did not previously take a `session` parameter — add
`session: Annotated[AsyncSession, Depends(get_session)]` to its signature; this is additive to the
signature Task 1 wrote, harmless since `Depends(current_user)` callers never see the parameter list.
The access branch's `mark_seen` call is a no-op the very first time — `last_seen_at` was just set by
`server_default=now()` on that row's creation, still within the throttle window — but calling it
unconditionally on this one return, rather than special-casing "except on first sign-in", keeps the
function to one code path.) Add `import logging` and a module `logger =
logging.getLogger("rhapto.api.deps")` to `deps.py` if it does not already have one (verified it does
not).

- [ ] **Step 6: Add `rhapto_inactive_days` and the CLI prune command**

```python
# apps/api/src/rhapto/config.py
    rhapto_inactive_days: int = 90
```

```python
# apps/api/src/rhapto/cli/main.py — new command on the accounts_app from Task 3
@accounts_app.command("prune")
def accounts_prune(dry_run: bool = typer.Option(True, "--dry-run/--yes")) -> None:
    """List (or, with --yes, delete) accounts inactive for RHAPTO_INACTIVE_DAYS. Dry-run by
    default: this prints emails, last_seen_at, and nothing else destructive until Task 7 adds the
    real deletion this flag calls."""
    settings = Settings()

    async def run() -> list[tuple[str, str]]:
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as session:
                from datetime import UTC, datetime, timedelta

                from rhapto.services.accounts import inactive_accounts

                cutoff = datetime.now(UTC) - timedelta(days=settings.rhapto_inactive_days)
                users = await inactive_accounts(session, cutoff)
                return [(u.email, u.last_seen_at.isoformat()) for u in users]
        finally:
            await engine.dispose()

    rows = asyncio.run(run())
    if not rows:
        typer.echo("no inactive accounts")
        return
    for email, last_seen in rows:
        typer.echo(f"{email}  last_seen_at={last_seen}")
    if dry_run:
        typer.echo(f"{len(rows)} account(s) would be deleted (dry run; pass --yes to delete)")
    else:
        typer.echo(
            "error: --yes deletion is not implemented until Task 7's delete_account ships", err=True
        )
        raise typer.Exit(1)


@accounts_app.command("exempt")
def accounts_exempt(
    email: str = typer.Argument(...),
    on: bool = typer.Option(True, "--on/--off", help="set or clear exempt_from_pruning"),
) -> None:
    """Fixes plan-review I6: nothing previously set exempt_from_pruning, so the column added in
    migration 0011 was unreachable. Lets the owner exempt his own account (or any account) from
    the 90-day prune -- an explicit, printed decision, never an implicit default."""
    settings = Settings()

    async def run() -> bool:
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as session:
                from sqlalchemy import select as sa_select

                from rhapto.db.models import User

                user = await session.scalar(sa_select(User).where(User.email == email.casefold()))
                if user is None:
                    return False
                user.exempt_from_pruning = on
                await session.commit()
                return True
        finally:
            await engine.dispose()

    if not asyncio.run(run()):
        typer.echo(f"error: no account found with email {email!r}", err=True)
        raise typer.Exit(1)
    typer.echo(f"{email}: exempt_from_pruning = {on}")
```

- [ ] **Step 7: Add `deletion_due_at` to `MeOut` and a day-60 web banner (plan-review I6)**

```python
# apps/api/src/rhapto/api/schemas.py — MeOut
class MeOut(BaseModel):
    email: str
    user_id: uuid.UUID
    llm_configured: bool
    auth_mode: Literal["token", "access"]
    deletion_due_at: datetime | None  # None when exempt; otherwise last_seen_at + RHAPTO_INACTIVE_DAYS
```

```python
# apps/api/src/rhapto/api/routers/meta.py — me()
from datetime import timedelta


@router.get("/me", response_model=MeOut)
async def me(
    user_id: Annotated[uuid.UUID, Depends(current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> MeOut:
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=503, detail="user not bootstrapped")
    due_at = (
        None
        if user.exempt_from_pruning
        else user.last_seen_at + timedelta(days=settings.rhapto_inactive_days)
    )
    return MeOut(
        email=user.email,
        user_id=user.id,
        llm_configured=await is_llm_configured(session, settings, user_id),
        auth_mode=settings.rhapto_auth_mode,
        deletion_due_at=due_at,
    )
```

**`MeOut` gaining a second required field breaks `apps/web`'s typecheck again** (the same class of
break as Task 1's `auth_mode` — re-review breakage item 1's other half). Task 1 already updated
`TailorButton.test.tsx`'s two `meData` literals to include `auth_mode`; extend both again here:

```typescript
// apps/web/src/components/jobs/TailorButton.test.tsx:72 and :245 — add deletion_due_at to both
meData = { user_id: "u1", email: "dev@example.com", llm_configured: true, auth_mode: "token", deletion_due_at: null };
// ...and, at line 245:
meData = { user_id: "u1", email: "dev@example.com", llm_configured: false, auth_mode: "token", deletion_due_at: null };
```

```typescript
// apps/web/src/components/shell/DeletionBanner.tsx
"use client";
import { useMe } from "@/lib/api/queries";

const WARN_WITHIN_DAYS = 30; // owner decision Q3: warn from day 60 of a 90-day window

export function DeletionBanner() {
  const me = useMe();
  if (!me.isSuccess || !me.data.deletion_due_at) return null;
  const dueAt = new Date(me.data.deletion_due_at);
  const daysLeft = Math.ceil((dueAt.getTime() - Date.now()) / 86_400_000);
  if (daysLeft > WARN_WITHIN_DAYS || daysLeft < 0) return null;
  return (
    <div className="w-full bg-amber-100 px-4 py-2 text-center text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">
      Your account has been inactive for a while. If you don't sign in again, it and everything in
      it will be deleted in {daysLeft} day{daysLeft === 1 ? "" : "s"}.
    </div>
  );
}
```

```typescript
// apps/web/src/components/shell/DeletionBanner.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DeletionBanner } from "./DeletionBanner";

vi.mock("@/lib/api/queries", () => ({ useMe: vi.fn() }));
import { useMe } from "@/lib/api/queries";

describe("DeletionBanner", () => {
  it("renders nothing when deletion_due_at is more than 30 days away", () => {
    const far = new Date(Date.now() + 60 * 86_400_000).toISOString();
    vi.mocked(useMe).mockReturnValue({ isSuccess: true, data: { deletion_due_at: far } } as ReturnType<typeof useMe>);
    render(<DeletionBanner />);
    expect(screen.queryByText(/deleted in/)).not.toBeInTheDocument();
  });

  it("warns when deletion is within 30 days", () => {
    const soon = new Date(Date.now() + 10 * 86_400_000).toISOString();
    vi.mocked(useMe).mockReturnValue({ isSuccess: true, data: { deletion_due_at: soon } } as ReturnType<typeof useMe>);
    render(<DeletionBanner />);
    expect(screen.getByText(/deleted in 10 days/)).toBeInTheDocument();
  });

  it("renders nothing when exempt (deletion_due_at is null)", () => {
    vi.mocked(useMe).mockReturnValue({ isSuccess: true, data: { deletion_due_at: null } } as ReturnType<typeof useMe>);
    render(<DeletionBanner />);
    expect(screen.queryByText(/deleted in/)).not.toBeInTheDocument();
  });
});
```

Mount `<DeletionBanner />` in the same top-level shell component that renders `TopBar`
(`apps/web/src/components/shell/Shell.tsx`, per the earlier directory listing) — the implementer
confirms the exact insertion point by reading that file first.

Regenerate the OpenAPI document and web types: `python scripts/export_openapi.py` (from `apps/api`),
`pnpm gen:api` (from `apps/web`).

- [ ] **Step 8: Write the CLI tests — in `tests/unit/`, not `tests/cli/` (plan-review I11)**

```python
# apps/api/tests/unit/test_accounts_prune.py
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from rhapto.cli.main import app
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

runner = CliRunner()


def test_prune_dry_run_lists_inactive_accounts(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            stale = await get_or_create_user(session, "stale@example.com")
            stale.last_seen_at = datetime.now(UTC) - timedelta(days=100)
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "prune"])
    assert result.exit_code == 0, result.output
    assert "stale@example.com" in result.output
    assert "dry run" in result.output


def test_prune_yes_is_not_yet_implemented(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            stale = await get_or_create_user(session, "stale2@example.com")
            stale.last_seen_at = datetime.now(UTC) - timedelta(days=100)
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "prune", "--yes"])
    assert result.exit_code == 1


def test_exempt_on_then_off(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            await get_or_create_user(session, "owner@example.com")
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    on_result = runner.invoke(app, ["accounts", "exempt", "owner@example.com", "--on"])
    assert on_result.exit_code == 0 and "True" in on_result.output
    off_result = runner.invoke(app, ["accounts", "exempt", "owner@example.com", "--off"])
    assert off_result.exit_code == 0 and "False" in off_result.output


def test_exempt_unknown_account_exits_1(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    result = runner.invoke(app, ["accounts", "exempt", "nobody@example.com"])
    assert result.exit_code == 1
```

- [ ] **Step 9: Run the new tests, then the full suites**

Run: `pytest tests/unit/test_accounts_lifecycle.py tests/unit/test_accounts_prune.py -v` — expect PASS.
Run: `pytest` — expect green.
Run: `ruff check .` and `mypy src` — expect clean.
Run (apps/web): `pnpm test DeletionBanner.test.tsx`, then `pnpm test`, `pnpm lint`, `pnpm typecheck`
— expect green.

- [ ] **Step 10: Commit**

```bash
git add apps/api/src/rhapto/services/accounts.py apps/api/src/rhapto/api/deps.py \
  apps/api/src/rhapto/config.py apps/api/src/rhapto/cli/main.py \
  apps/api/src/rhapto/api/schemas.py apps/api/src/rhapto/api/routers/meta.py \
  packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts \
  apps/web/src/components/shell/DeletionBanner.tsx apps/web/src/components/shell/DeletionBanner.test.tsx \
  apps/web/src/components/jobs/TailorButton.test.tsx \
  apps/api/tests/unit/test_accounts_lifecycle.py apps/api/tests/unit/test_accounts_prune.py
git commit -m "$(cat <<'EOF'
last_seen_at throttling, inactive_accounts query, prune --dry-run, exempt CLI, day-60 banner (B1a)

mark_seen is now a single atomic UPDATE with no preceding SELECT (plan-review I5), rolls back on
failure so a swallowed error can't poison the request's session (re-review item 6), throttled to
once per hour, and never fails the request it rides along with. inactive_accounts finds every
non-exempt account past RHAPTO_INACTIVE_DAYS (default 90). `rhapto accounts prune` lists them;
--yes is a defined, not-yet-wired error until Task 7 adds the real deletion path. `rhapto accounts
exempt` sets/clears exempt_from_pruning, which nothing could previously reach (plan-review I6).
MeOut.deletion_due_at and a new DeletionBanner give a returning user the day-60 warning the
architecture calls for, before Task 7's cron can ever delete anything unattended.
TailorButton.test.tsx's MeOut literals updated again so apps/web's typecheck stays green.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 15 (the day-60 banner and `exempt` command are the safety net
against the prune cron becoming a new threat to the owner's own data); AC 8/16 land fully in Task 7.

---

## Task 7 (B1b): `delete_account`, `sweep_orphan_files`, real `accounts prune --yes` / `accounts delete`

> **AMENDMENT 2026-09-25 — test isolation. Read before writing any test in this task.**
>
> Every test below takes `migrated_db`. That fixture (`apps/api/tests/conftest.py:127`) returns a
> migrated database URL and **does not clean it**; `session_factory`
> (`conftest.py:142-147`) truncates **on teardown only**. So a test that seeds rows through its own
> engine leaves them behind, and the *next* invocation starts dirty.
>
> This already bit Task 3: `tests/unit/test_accounts_set_email.py` was copied verbatim from this plan
> and collided across runs — it passed on run 1 and failed on run 2. Adding `session_factory` as a
> truncating parameter was not sufficient, because teardown cleanup cannot help the first run against
> an already-dirty database.
>
> **This task is more exposed than Task 3 was**, because the subject under test *is which accounts
> exist*: a leftover account makes `prune`/`inactive_accounts`/`delete` assert against rows it did not
> create, and the failure will look like a logic bug in the pruning code rather than a dirty database.
>
> Therefore, for every test in this task:
> 1. Depend on a fixture that **truncates before the test body runs**, not only after. Task 3's fix
>    round may already have added one while closing finding N2 — check `conftest.py` first and reuse it
>    rather than adding a second.
> 2. Seed **per-run unique** email addresses (`f"{uuid4().hex}@example.com"`), so two invocations cannot
>    collide even if cleanup is skipped or a run is interrupted.
> 3. Assert on rows **you** created — by the unique address — never on a total count of `users`.


Verified before writing: `apps/api/src/rhapto/services/storage.py` (`PackageStorage.delete(package_id)`,
`delete_document(user_id)` — both already exist and are exactly what this task needs, no new storage
method required); `apps/api/src/rhapto/db/base.py:27-30` (`UserScopedMixin.user_id` is
`ForeignKey("users.id", ondelete="CASCADE")` on every one of the 17 user-scoped tables listed in
`db/models.py`, so `DELETE FROM users WHERE id = :u` alone removes every row — `resume_blocks`,
`resume_bases`, `tracks`, `guardrails`, `answers`, `resume_documents`, `llm_settings`, `watchlist`,
`jobs`, `packages`, `applications`, `tasks`, `aggregators`, `job_scores`, `poll_runs`, `searches`,
`source_credentials`); `apps/api/src/rhapto/db/models.py:212-215,268-271`
(`Package.job_id`/`Application.job_id` are `ForeignKey("jobs.id", ondelete="CASCADE")`, so deleting a
user's `jobs` rows — itself cascaded from the `users` delete — cascades onward automatically). **There
is no `postings` table in this plan's scope**, so "deletion must not cascade into shared data" is
already true by construction: nothing in Phase A/B is shared across accounts. **Arq job cancellation
is out of reach without new job-id-tracking infrastructure** (verified: `ArqEnqueuer.enqueue` never
passes arq's `_job_id`, so no `Task` row can be correlated to a cancellable arq job today) — this task
does not build that infrastructure (it would be its own scoped project); instead it relies on the
files-before-rows ordering plus the fact that every task handler already wraps its work in a
try/except at the task boundary and writes only to rows that, after this deletion, no longer exist —
so an in-flight task for a just-deleted user can fail loudly but can never resurrect or corrupt
anything, which is the property the architecture actually requires.

This task also fixes **C7** (the deletion tests could not pass as originally written — see Step 1),
**minor 4** (`sweep_orphan_files` must skip a stray directory name rather than crash the whole sweep
on it), and wires Task 6's `would_delete_everyone` last-account guard into both destructive paths, plus
gives the orphan sweep its own try/except so a failed prune can never silently skip it (the plan
reviewer's accepted caveat on this task's own files-before-rows argument).

**Files:**
- Modify: `apps/api/src/rhapto/services/accounts.py` (`delete_account`, `sweep_orphan_files`)
- Modify: `apps/api/src/rhapto/cli/main.py` (`accounts prune --yes` calls `delete_account`, guarded by
  `would_delete_everyone`; `accounts delete <email> --yes`)
- Modify: `apps/api/src/rhapto/worker/main.py` (daily prune cron, same guard, sweep in its own
  try/except)
- Test: `apps/api/tests/unit/test_delete_account.py`
- Test: `apps/api/tests/unit/test_accounts_delete.py` (not `tests/cli/` — plan-review I11)

**Interfaces:**
- Consumes: `PackageStorage.delete`/`delete_document` (unchanged, `services/storage.py`),
  `inactive_accounts`/`mark_seen` (Task 6).
- Produces:
  ```python
  # rhapto/services/accounts.py
  @dataclass(frozen=True)
  class DeletionReport:
      user_id: uuid.UUID
      rows_deleted: bool
      package_files_deleted: int

  async def delete_account(
      session: AsyncSession, storage: PackageStorage, user_id: uuid.UUID
  ) -> DeletionReport: ...
  async def sweep_orphan_files(session: AsyncSession, storage: PackageStorage) -> int: ...
  ```

- [ ] **Step 1: Write the failing deletion tests**

**Fixes plan-review C7.** `make_session_factory` sets `expire_on_commit=False`
(`apps/api/src/rhapto/db/session.py:16`). `jobs`/`packages` rows are removed by a database-level
`ON DELETE CASCADE` the ORM never observes, so nothing expires the in-memory `Job`/`Package` objects
these tests already loaded — `await session.get(Job, job.id)` returns the still-cached instance, not
`None`, and the earlier draft's assertions failed (or worse, passed vacuously). Both affected tests
call `session.expunge_all()` after `delete_account`'s commit, forcing a fresh read from the database
for every subsequent `session.get`:

```python
# apps/api/tests/unit/test_delete_account.py
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application, Job, Package, User
from rhapto.db.repositories.jobs import create_job
from rhapto.db.repositories.users import get_or_create_user
from rhapto.services.accounts import delete_account, sweep_orphan_files
from rhapto.services.storage import PackageStorage


async def test_delete_account_removes_the_user_row_and_cascades(
    session: AsyncSession, tmp_path: Path
) -> None:
    storage = PackageStorage(tmp_path / "packages")
    user = await get_or_create_user(session, "leaving@example.com")
    job = await create_job(session, user.id, jd_text="A real job description. " * 10)
    package = Package(
        user_id=user.id, job_id=job.id, track_id="pm", version=1, status="draft",
        resume_json={}, cover_note="", change_log="", guardrail_report_json={}, jd_extract_json={},
        docx_path=str(storage.write_docx(str(uuid.uuid4()), b"fake docx bytes")),
    )
    session.add(package)
    await session.commit()

    package_id = package.id
    user_id = user.id
    job_id = job.id
    storage.write_docx(str(package_id), b"fake docx bytes")

    report = await delete_account(session, storage, user_id)
    await session.commit()
    # expire_on_commit=False (db/session.py:16) means the ORM never notices the DB-level CASCADE
    # that just removed `job`/`user` -- without this, session.get below returns the stale
    # in-memory object instead of re-querying, and these assertions would pass or fail for the
    # wrong reason (plan-review C7).
    session.expunge_all()

    assert report.package_files_deleted == 1
    assert await session.get(User, user_id) is None
    assert await session.get(Job, job_id) is None
    assert not storage.dir_for(str(package_id)).exists()


async def test_delete_account_never_touches_another_users_rows(session: AsyncSession, tmp_path: Path) -> None:
    storage = PackageStorage(tmp_path / "packages")
    staying = await get_or_create_user(session, "staying@example.com")
    leaving = await get_or_create_user(session, "leaving2@example.com")
    staying_job = await create_job(session, staying.id, jd_text="A real job description. " * 10)
    await create_job(session, leaving.id, jd_text="Another real job description. " * 10)
    await session.commit()
    staying_id = staying.id
    staying_job_id = staying_job.id

    await delete_account(session, storage, leaving.id)
    await session.commit()
    session.expunge_all()  # plan-review C7 -- see the note above

    assert await session.get(User, staying_id) is not None
    assert await session.get(Job, staying_job_id) is not None


async def test_sweep_orphan_files_removes_packages_with_no_row(tmp_path: Path, session: AsyncSession) -> None:
    storage = PackageStorage(tmp_path / "packages")
    orphan_id = str(uuid.uuid4())
    storage.write_docx(orphan_id, b"orphaned")
    assert storage.dir_for(orphan_id).exists()

    removed = await sweep_orphan_files(session, storage)

    assert removed >= 1
    assert not storage.dir_for(orphan_id).exists()


async def test_sweep_orphan_files_skips_a_directory_name_that_is_not_a_valid_package_id(
    tmp_path: Path, session: AsyncSession
) -> None:
    """Fixes plan-review minor 4: storage.delete() raises ValueError for any name that does not
    match SAFE_ID (services/storage.py:15,22-25); one stray directory must not abort the sweep."""
    storage = PackageStorage(tmp_path / "packages")
    storage.root.mkdir(parents=True, exist_ok=True)
    (storage.root / ".hidden-invalid-name").mkdir()  # fails SAFE_ID (services/storage.py:15): must
                                                       # start with an alphanumeric character
    valid_orphan = str(uuid.uuid4())
    storage.write_docx(valid_orphan, b"orphaned")

    removed = await sweep_orphan_files(session, storage)

    assert removed == 1
    assert not storage.dir_for(valid_orphan).exists()
```

- [ ] **Step 2: Run to see it fail**

Run: `pytest tests/unit/test_delete_account.py -v`
Expected: FAIL — `delete_account`/`sweep_orphan_files` do not exist.

- [ ] **Step 3: Implement `delete_account` and `sweep_orphan_files`**

```python
# apps/api/src/rhapto/services/accounts.py — additions
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select

from rhapto.db.models import Package, User
from rhapto.services.storage import PackageStorage


@dataclass(frozen=True)
class DeletionReport:
    user_id: uuid.UUID
    rows_deleted: bool
    package_files_deleted: int


async def delete_account(
    session: AsyncSession, storage: PackageStorage, user_id: uuid.UUID
) -> DeletionReport:
    """Delete one account: files before rows, per architecture.md §4.2.

    A crash between deleting files and deleting rows leaves recoverable orphan *rows*, cleaned up
    by sweep_orphan_files on the next cron run; the reverse order would leave an unrecoverable
    orphan *file* -- someone's resume on disk with no record of whose it was, the worst possible
    residue. Every row this deletes is scoped to `user_id` via ON DELETE CASCADE from `users`
    (verified: all 17 UserScopedMixin tables, plus `packages`/`applications` cascading onward from
    `jobs`) -- there is no shared table in this schema for the deletion to reach.
    """
    package_ids = list(
        await session.scalars(select(Package.id).where(Package.user_id == user_id))
    )
    for package_id in package_ids:
        storage.delete(str(package_id))
    storage.delete_document(user_id)

    result = await session.execute(delete(User).where(User.id == user_id))
    return DeletionReport(
        user_id=user_id, rows_deleted=result.rowcount > 0, package_files_deleted=len(package_ids)
    )


async def sweep_orphan_files(session: AsyncSession, storage: PackageStorage) -> int:
    """Delete any package directory or resume-document directory with no matching row.

    Self-heals the crash window in delete_account (files deleted, row-delete not yet committed --
    or vice versa if this ever ran between the two) and cleans up any pre-existing orphan. A
    directory whose name is not a valid package id (fails PackageStorage.SAFE_ID) is skipped, not
    raised on -- one stray directory (a `.DS_Store`-style artifact, a hand-created folder) must
    never abort the whole sweep (plan-review minor 4).
    """
    removed = 0
    if not storage.root.exists():
        return 0
    existing_package_ids = {str(pid) for pid in await session.scalars(select(Package.id))}
    for entry in storage.root.iterdir():
        if entry.name == "resume-document" or not entry.is_dir():
            continue
        if entry.name not in existing_package_ids:
            try:
                storage.delete(entry.name)
            except ValueError:
                logger.warning("skipping non-package-id directory in packages root: %r", entry.name)
                continue
            removed += 1
    doc_root = storage.root / "resume-document"
    if doc_root.exists():
        existing_user_ids = {str(uid) for uid in await session.scalars(select(User.id))}
        for entry in doc_root.iterdir():
            if entry.is_dir() and entry.name not in existing_user_ids:
                try:
                    storage.delete_document(uuid.UUID(entry.name))
                except ValueError:
                    logger.warning("skipping non-uuid directory under resume-document: %r", entry.name)
                    continue
                removed += 1
    return removed
```

- [ ] **Step 4: Run the tests again**

Run: `pytest tests/unit/test_delete_account.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `--yes` into the CLI, and add `accounts delete`**

```python
# apps/api/src/rhapto/cli/main.py — replace the accounts_prune body's `else` branch (Task 6 Step 6)
    else:
        async def run_deletions() -> int | None:
            engine = make_engine(settings.database_url)
            try:
                async with make_session_factory(engine)() as session:
                    from rhapto.db.repositories.users import list_user_ids
                    from rhapto.services.accounts import (
                        delete_account,
                        inactive_accounts,
                        would_delete_everyone,
                    )
                    from rhapto.services.storage import PackageStorage

                    storage = PackageStorage(settings.rhapto_packages_dir)
                    cutoff = datetime.now(UTC) - timedelta(days=settings.rhapto_inactive_days)
                    to_delete = await inactive_accounts(session, cutoff)
                    all_ids = await list_user_ids(session)
                    # plan-review I6: a misconfigured RHAPTO_INACTIVE_DAYS, or a period of CLI-only
                    # use that never touched last_seen_at, must never be able to empty the instance.
                    if would_delete_everyone(all_ids, [u.id for u in to_delete]):
                        return None
                    for u in to_delete:
                        await delete_account(session, storage, u.id)
                    await session.commit()
                    return len(to_delete)
            finally:
                await engine.dispose()

        deleted = asyncio.run(run_deletions())
        if deleted is None:
            typer.echo(
                "error: refusing to prune -- this would delete every remaining account. If that is "
                "really intended, use `rhapto accounts delete <email> --yes` one at a time.",
                err=True,
            )
            raise typer.Exit(1)
        typer.echo(f"deleted {deleted} account(s)")


@accounts_app.command("delete")
def accounts_delete(
    email: str = typer.Argument(...), yes: bool = typer.Option(False, "--yes")
) -> None:
    """Delete one account by email, regardless of last_seen_at (owner-initiated removal)."""
    if not yes:
        typer.echo("error: pass --yes to confirm deletion", err=True)
        raise typer.Exit(1)
    settings = Settings()

    async def run() -> bool:
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as session:
                from sqlalchemy import select as sa_select

                from rhapto.db.models import User
                from rhapto.services.accounts import delete_account
                from rhapto.services.storage import PackageStorage

                user = await session.scalar(sa_select(User).where(User.email == email))
                if user is None:
                    return False
                await delete_account(session, PackageStorage(settings.rhapto_packages_dir), user.id)
                await session.commit()
                return True
        finally:
            await engine.dispose()

    if not asyncio.run(run()):
        typer.echo(f"error: no account found with email {email!r}", err=True)
        raise typer.Exit(1)
    typer.echo(f"deleted {email}")
```

Move the earlier `accounts_prune`'s `else: typer.echo("error: --yes deletion is not implemented
...")` branch out entirely, replacing it with the real deletion above; `from datetime import UTC,
datetime, timedelta` must be imported at module scope in `cli/main.py` (it was previously imported
inline inside the dry-run closure in Task 6 — hoist it to the top-level imports now that both
branches need it).

- [ ] **Step 6: Add the daily prune cron**

```python
# apps/api/src/rhapto/worker/main.py — WorkerSettings.cron_jobs
from datetime import UTC, datetime, timedelta

from rhapto.db.repositories.users import list_user_ids
from rhapto.services.accounts import (
    delete_account,
    inactive_accounts,
    sweep_orphan_files,
    would_delete_everyone,
)
from rhapto.services.storage import PackageStorage


async def prune_inactive_accounts(ctx: dict[str, Any]) -> None:
    """The daily destructive cron. Two things the plan reviewer specifically required, both fixed
    here: (1) the same last-account guard as the CLI (I6) -- an unattended cron is exactly where a
    misconfiguration doing something catastrophic matters most; (2) the orphan sweep runs in its
    own try/except, separate from the prune loop, so a prune failure can never silently skip the
    sweep (the plan reviewer's accepted caveat on this task's files-before-rows argument).
    """
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    settings = get_settings()
    storage = PackageStorage(settings.rhapto_packages_dir)
    try:
        async with factory() as session:
            cutoff = datetime.now(UTC) - timedelta(days=settings.rhapto_inactive_days)
            to_delete = await inactive_accounts(session, cutoff)
            all_ids = await list_user_ids(session)
            if would_delete_everyone(all_ids, [u.id for u in to_delete]):
                logger.error(
                    "refusing scheduled prune: it would delete every remaining account "
                    "(%d candidate(s)). Check RHAPTO_INACTIVE_DAYS and whether last_seen_at is "
                    "being updated at all.",
                    len(to_delete),
                )
            else:
                # Logged before any deletion runs, per plan-review I6: an operator reading the
                # cron log sees exactly who was about to be pruned, not just a count afterwards.
                for user in to_delete:
                    logger.info(
                        "pruning inactive account %s (last seen %s)", user.email, user.last_seen_at
                    )
                for user in to_delete:
                    await delete_account(session, storage, user.id)
                await session.commit()
    except Exception:
        logger.exception("scheduled account prune failed")
    try:
        async with factory() as session:
            removed = await sweep_orphan_files(session, storage)
            if removed:
                logger.info("orphan sweep removed %d file(s)", removed)
    except Exception:
        logger.exception("scheduled orphan sweep failed")
```

```python
# apps/api/src/rhapto/worker/main.py — WorkerSettings.cron_jobs, add a daily entry
    cron_jobs = (
        (
            [cron(poll_all_sources, hour=_HOURS, minute=0, run_at_startup=False)] if _HOURS else []
        )
        + [cron(prune_inactive_accounts, hour={3}, minute=0, run_at_startup=False)]
    )
```

- [ ] **Step 7: Write the CLI test — in `tests/unit/`, not `tests/cli/` (plan-review I11)**

```python
# apps/api/tests/unit/test_accounts_delete.py
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from typer.testing import CliRunner

from rhapto.cli.main import app
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory

runner = CliRunner()


def test_delete_requires_yes(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    result = runner.invoke(app, ["accounts", "delete", "someone@example.com"])
    assert result.exit_code == 1


def test_delete_removes_the_account(migrated_db, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    monkeypatch.setenv("RHAPTO_PACKAGES_DIR", str(tmp_path / "packages"))

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            await get_or_create_user(session, "gone-for-good@example.com")
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "delete", "gone-for-good@example.com", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted" in result.output


def test_prune_yes_deletes_inactive_accounts(migrated_db, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    monkeypatch.setenv("RHAPTO_PACKAGES_DIR", str(tmp_path / "packages"))

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            stale = await get_or_create_user(session, "long-gone@example.com")
            stale.last_seen_at = datetime.now(UTC) - timedelta(days=200)
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "prune", "--yes"])
    assert result.exit_code == 0, result.output
    assert "deleted 1 account" in result.output


def test_prune_refuses_to_delete_the_last_remaining_account(migrated_db, monkeypatch, tmp_path) -> None:
    """Fixes plan-review I6: a misconfigured RHAPTO_INACTIVE_DAYS, or CLI-only use that never
    updates last_seen_at, must never be able to silently empty the instance."""
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    monkeypatch.setenv("RHAPTO_PACKAGES_DIR", str(tmp_path / "packages"))

    async def seed() -> None:
        engine = make_engine(migrated_db)
        async with make_session_factory(engine)() as session:
            only = await get_or_create_user(session, "only-account@example.com")
            only.last_seen_at = datetime.now(UTC) - timedelta(days=200)
            await session.commit()
        await engine.dispose()

    asyncio.run(seed())
    result = runner.invoke(app, ["accounts", "prune", "--yes"])
    assert result.exit_code == 1
    assert "every remaining account" in result.output

    async def still_exists() -> bool:
        engine = make_engine(migrated_db)
        try:
            async with make_session_factory(engine)() as session:
                from sqlalchemy import select as sa_select

                from rhapto.db.models import User

                return (
                    await session.scalar(
                        sa_select(User).where(User.email == "only-account@example.com")
                    )
                ) is not None
        finally:
            await engine.dispose()

    assert asyncio.run(still_exists())
```

- [ ] **Step 8: Run the new tests, then the full suite**

Run: `pytest tests/unit/test_delete_account.py tests/unit/test_accounts_delete.py -v` — expect PASS.
Run: `pytest` — expect green.
Run: `ruff check .` and `mypy src` — expect clean.

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/rhapto/services/accounts.py apps/api/src/rhapto/cli/main.py \
  apps/api/src/rhapto/worker/main.py \
  apps/api/tests/unit/test_delete_account.py apps/api/tests/unit/test_accounts_delete.py
git commit -m "$(cat <<'EOF'
delete_account (files before rows), orphan sweep, real prune/delete CLI, daily cron (B1b)

delete_account deletes a user's package files and resume document from disk before deleting the
users row, which cascades through all 17 UserScopedMixin tables plus packages/applications
cascading from jobs -- no other account's rows are ever touched, because nothing is shared in this
schema before Phase C. sweep_orphan_files self-heals a crash between the file and row deletes, and
now skips (rather than aborts on) a directory whose name isn't a valid package id (plan-review
minor 4). `rhapto accounts prune --yes` and the daily cron both refuse to run if every remaining
account would be deleted (plan-review I6) and log the full list before deleting anything; the
cron's orphan sweep runs in its own try/except so a prune failure can never silently skip it
(plan-review's accepted caveat). `rhapto accounts delete <email> --yes` deletes one account
unconditionally. Arq job cancellation for in-flight tasks was scoped out: no job-id tracking exists
to correlate a Task row to a cancellable arq job, and building that is its own project -- the
existing per-task try/except plus files-before-rows ordering already guarantees no resurrection and
no cross-account harm.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 8, 16.

---

## Task 8 (B2): Backup cron, ad-hoc dump cleanup, post-restore prune, the published promise

Verified before writing: `scripts/backup-db.sh` (already does `pg_dump -Fc`, `RETENTION_DAYS` default
14, pruned by `find -mtime`; its own header states "This script does not schedule itself" and its
restore procedure has no post-restore prune step); the SDD ledger reference to ad-hoc
`/root/rhapto-pre-0010-*.sql` dumps is an operational fact about the production host, not something
in this checkout — this task's code changes are the runbook/script changes; the actual deletion of
those specific files is a Phase 7 (Delivery) action, not a code change, and is called out as such
below rather than invented as a test.

This task also fixes **I7** (the retention promise was published with nothing checking that the cron
actually runs) and **minor 7** (the backup-script test used `which`, which is not on the owner's
Windows dev box, causing a collection-time crash rather than a clean skip). It also corrects a claim
the earlier draft made without checking: **minor 8** — Task 2's `TokenGate` (as rewritten in this
revision) never renders `Landing` in access mode at all; a not-yet-authenticated visitor there is
handled entirely by Cloudflare's own hosted login page, before any Rhapto code runs. "Stated to the
user before they sign up" therefore cannot be satisfied by anything in this repository for access
mode — the correct owner of that copy is the Cloudflare Access application's own login-page
customisation, a dashboard setting, not code. This task drops the incorrect `Landing.tsx` edit and
says explicitly where the promise is actually shown.

**Files:**
- Modify: `scripts/backup-db.sh` (add the mandatory post-restore prune step to the documented
  procedure; add a `--pre-migration` mode that writes into `$BACKUP_DIR` with the standard name)
- Modify: `apps/web/src/app/settings/page.tsx` or a new `apps/web/src/components/settings/DataRetentionNotice.tsx`
  (publish the true-bound promise text)
- Modify: `apps/api/src/rhapto/cli/main.py` (`rhapto backups check`)
- Test: `apps/api/tests/unit/test_backup_script.py`
- Test: `apps/api/tests/unit/test_backups_check.py`
- Test: `apps/web/src/components/settings/DataRetentionNotice.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks (this task is deploy-ops plus one static piece of UI copy).
- Produces:
  ```python
  # rhapto/cli/main.py
  # `rhapto backups check` -- exit 0 if $BACKUP_DIR has a backup-*.dump newer than 48h, else exit 1
  # with an actionable message. Meant to be wired into the same cron/monitoring the nightly backup
  # itself runs under, or a `rhapto doctor`-style health check, by Delivery.
  ```
  No other task in this plan consumes it. The deploy runbook (documented in this task's steps, not a
  file this plan creates, since no runbook file exists in this checkout to extend — the implementer
  should check for `docs/runbook.md` or similar before assuming one must be created new) gains three
  mandatory steps: install the backup cron, wire `rhapto backups check` into a daily monitoring check,
  and run `rhapto accounts prune --yes` immediately after any restore.

- [ ] **Step 1: Check for an existing runbook file**

Run: `find . -iname "*runbook*" -not -path "*/node_modules/*"` (from the repo root). If a runbook
file exists, the promise text and the post-restore step are added there; if none exists, they are
added as comments in `scripts/backup-db.sh` (which already documents its own restore procedure in
its header, verified) and the implementer notes in the task-N report which choice was made.

- [ ] **Step 2: Add the pre-migration dump mode to `backup-db.sh`**

```bash
# scripts/backup-db.sh — after the existing dump block (replaces the fixed `$timestamp`/`$dest`
# derivation so a pre-migration dump lands in $BACKUP_DIR under the same naming convention the
# pruner already recognises, rather than as an ad-hoc file outside its reach)
LABEL="${LABEL:-}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
suffix="${LABEL:+-${LABEL}}"
dest="$BACKUP_DIR/backup-${PGDATABASE}${suffix}-${timestamp}.dump"
```

Update the header comment block to document the new usage:

```bash
# PRE-MIGRATION DUMPS
#   Before any migration that changes schema in a way you might need to undo, run:
#     LABEL=pre-0011 BACKUP_DIR=/var/backups/rhapto /path/to/scripts/backup-db.sh
#   This writes into the same $BACKUP_DIR as the nightly cron, named
#   backup-<db>-pre-0011-<timestamp>.dump, so the standard ${RETENTION_DAYS}-day prune reaches it
#   too. Do not write pre-migration dumps anywhere the pruner does not look -- an ad-hoc dump
#   outside $BACKUP_DIR is a standing violation of the deletion promise the moment a second
#   person's data is in the database.
```

Add to the existing "RESTORE" section in the header:

```bash
#   4. MANDATORY, after restoring onto a database the app will actually run against: run
#        rhapto accounts prune --yes
#      immediately, before pointing the app at the restored database. A restored dump can contain
#      rows for an account pruned after the dump was taken; without this step the deletion promise
#      has a hole that opens on the worst day of the year.
```

- [ ] **Step 3: Write the backup script test**

**Fixes plan-review minor 7:** the earlier draft shelled out to `which`, which does not exist on the
owner's Windows dev box — a bare `FileNotFoundError` at collection time, not the clean skip this test
intends. `shutil.which` is the portable stdlib equivalent.

```python
# apps/api/tests/unit/test_backup_script.py
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3].parent / "scripts" / "backup-db.sh"


def _pg_dump_available() -> bool:
    return shutil.which("pg_dump") is not None


@pytest.mark.skipif(not _pg_dump_available(), reason="pg_dump not on PATH in this environment")
def test_pre_migration_label_lands_in_backup_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path))
    monkeypatch.setenv("LABEL", "pre-0011")
    monkeypatch.setenv("PGDATABASE", "rhapto_test")
    result = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    dumps = list(tmp_path.glob("backup-rhapto_test-pre-0011-*.dump"))
    assert len(dumps) == 1
```

`SCRIPT`'s path arithmetic (`parents[3].parent`) must be verified against the actual location of
`apps/api/tests/unit/test_backup_script.py` relative to the repo-root `scripts/` directory before
this test is written — confirm with `python -c "from pathlib import Path; print(Path('apps/api/tests/unit/test_backup_script.py').resolve())"`
and count the right number of `.parent` calls, rather than trusting the count above blindly. This
test requires a reachable Postgres with a `rhapto_test` database and the `PGUSER`/`PGPASSWORD`
environment the CI or local dev environment already provides for `test_db_url`; skip cleanly if
`pg_dump` is not installed, matching this repo's existing pattern of skipping (not failing) when an
external dependency is unavailable (`test_db_url`/`test_redis_url` in `apps/api/tests/conftest.py`).

- [ ] **Step 4: Run it to see it fail, then pass**

Run: `pytest tests/unit/test_backup_script.py -v` (from `apps/api`)
Expected: FAIL before Step 2 (no `LABEL` handling, so the dump name never contains `pre-0011`); PASS
after.

- [ ] **Step 5: Add `rhapto backups check` — fixing plan-review I7**

**The promise text (Step 6) is only true if the cron that keeps it true is actually running and
recent enough.** Verified: `scripts/backup-db.sh` correctly implements `RETENTION_DAYS`-bounded
retention, but nothing checks that it is actually being invoked. This command gives Delivery (or any
external monitoring) something to wire in that fails loudly rather than the retention promise quietly
becoming false.

```python
# apps/api/src/rhapto/cli/main.py — new command, its own small Typer group or on accounts_app's
# sibling; a new `backups_app` keeps it independent of account lifecycle commands
backups_app = typer.Typer(no_args_is_help=True, help="Backup maintenance.")
app.add_typer(backups_app, name="backups")


@backups_app.command("check")
def backups_check(
    backup_dir: Path = typer.Option(
        Path("./backups"), "--backup-dir", envvar="BACKUP_DIR", help="Same as backup-db.sh's BACKUP_DIR"
    ),
    max_age_hours: int = typer.Option(48, "--max-age-hours"),
) -> None:
    """Exit 0 if a backup-*.dump newer than --max-age-hours exists in --backup-dir, else exit 1
    with an actionable message. Wire this into the same cron/monitoring the nightly backup runs
    under -- a retention promise nobody checks is a promise that can go silently false."""
    import time

    if not backup_dir.is_dir():
        typer.echo(f"error: backup directory {backup_dir} does not exist", err=True)
        raise typer.Exit(1)
    cutoff = time.time() - max_age_hours * 3600
    dumps = sorted(backup_dir.glob("backup-*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not dumps or dumps[0].stat().st_mtime < cutoff:
        newest = f"{dumps[0].name} ({dumps[0].stat().st_mtime})" if dumps else "none found"
        typer.echo(
            f"error: no backup newer than {max_age_hours}h in {backup_dir} (newest: {newest}). "
            "The nightly cron may not be running -- check `crontab -l` and the backup log.",
            err=True,
        )
        raise typer.Exit(1)
    typer.echo(f"ok: {dumps[0].name} is newer than {max_age_hours}h")
```

```python
# apps/api/tests/unit/test_backups_check.py
from __future__ import annotations

import time
from pathlib import Path

from typer.testing import CliRunner

from rhapto.cli.main import app

runner = CliRunner()


def test_check_passes_with_a_fresh_dump(tmp_path: Path) -> None:
    (tmp_path / "backup-rhapto-20260101T000000Z.dump").touch()
    result = runner.invoke(app, ["backups", "check", "--backup-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output


def test_check_fails_with_no_dumps(tmp_path: Path) -> None:
    result = runner.invoke(app, ["backups", "check", "--backup-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "no backup newer than" in result.output


def test_check_fails_with_only_a_stale_dump(tmp_path: Path) -> None:
    stale = tmp_path / "backup-rhapto-20200101T000000Z.dump"
    stale.touch()
    old_time = time.time() - 72 * 3600
    import os

    os.utime(stale, (old_time, old_time))
    result = runner.invoke(app, ["backups", "check", "--backup-dir", str(tmp_path), "--max-age-hours", "48"])
    assert result.exit_code == 1
```

Run: `pytest tests/unit/test_backups_check.py -v` — expect PASS.

- [ ] **Step 6: Publish the true-bound promise on the settings screen**

```typescript
// apps/web/src/components/settings/DataRetentionNotice.tsx
export function DataRetentionNotice() {
  return (
    <p className="text-sm text-muted-foreground">
      If this account is inactive for 90 days, it and everything in it — blocks, tracks, job
      matches, resume packages, and your provider key — is deleted. It is fully gone from backups
      within a further 14 days (worst case: 104 days after your last visit).
    </p>
  );
}
```

```typescript
// apps/web/src/components/settings/DataRetentionNotice.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataRetentionNotice } from "./DataRetentionNotice";

describe("DataRetentionNotice", () => {
  it("states the true worst-case bound, not a flat 90 days", () => {
    render(<DataRetentionNotice />);
    expect(screen.getByText(/90 days/)).toBeInTheDocument();
    expect(screen.getByText(/104 days/)).toBeInTheDocument();
  });
});
```

Render `<DataRetentionNotice />` on `apps/web/src/app/settings/page.tsx`, at the point (verified by
reading that file) where connection/account information is already shown — the exact insertion point
is a one-line JSX addition the implementer places after reading the current file, since this plan
does not reproduce that file's full contents.

**Where the promise is actually shown, stated precisely (fixes plan-review minor 8):** the earlier
draft of this task said the promise must also render on `Landing.tsx` "so it's visible pre-sign-in in
access mode" — checked against Task 2's rewritten `TokenGate` and that is not true. In access mode,
`TokenGate` never renders `Landing`; an unauthenticated visitor is either shown Cloudflare's own
hosted login page (before any Rhapto code runs at all) or, after a valid-but-non-allowlisted sign-in,
the "Access refused" card. There is no code-rendered screen in this repository that appears *before*
sign-in in access mode. So:
- The settings-screen `DataRetentionNotice` (this step) is the first-authenticated-screen disclosure,
  satisfying the letter of Owner decision Q3 for `token` mode (the single-owner case, where "before
  they sign up" and "immediately after" are the same moment, since there is no separate signup step).
- For `access` mode, the genuinely pre-signup disclosure surface is the **Cloudflare Access
  application's own login-page customisation** — a setting in the Cloudflare dashboard, not code.
  This is an operational action, handed to Delivery below, the same way the cron install and the
  ad-hoc dump cleanup are.
- `Landing.tsx` is left unmodified by this task: it renders only in `token` mode, where there is one
  account (the owner's) and no one else's 90-day clock is running yet.

- [ ] **Step 7: Run the new tests, then the full suites**

Run (apps/web): `pnpm test DataRetentionNotice.test.tsx` — expect PASS; then `pnpm test`, `pnpm lint`,
`pnpm typecheck` — expect green.
Run (apps/api): `pytest tests/unit/test_backup_script.py tests/unit/test_backups_check.py -v`, then
the full `pytest`, `ruff check .`, `mypy src` — expect green.

- [ ] **Step 8: Commit**

```bash
git add scripts/backup-db.sh apps/api/src/rhapto/cli/main.py \
  apps/api/tests/unit/test_backup_script.py apps/api/tests/unit/test_backups_check.py \
  apps/web/src/components/settings/DataRetentionNotice.tsx \
  apps/web/src/components/settings/DataRetentionNotice.test.tsx \
  apps/web/src/app/settings/page.tsx
git commit -m "$(cat <<'EOF'
Pre-migration dumps land inside BACKUP_DIR, mandatory post-restore prune, backup freshness check,
published promise (B2)

backup-db.sh gains a LABEL mode so a pre-migration dump uses the same backup-<db>-<label>-<ts>.dump
naming the nightly RETENTION_DAYS=14 prune already recognises -- a dump outside $BACKUP_DIR is a
standing violation of the deletion promise the moment a second account exists. The restore
procedure documented in the script's header now has a mandatory `rhapto accounts prune --yes` step
immediately after any restore, before the app is pointed at it. `rhapto backups check` fails loudly
if no dump newer than 48h exists, so the retention promise has something checking it actually holds
(plan-review I7) instead of just tooling that would make it true if run. The settings screen states
the promise with its true worst-case bound -- 90 days plus up to 14 for backups, 104 days worst case
-- never a flat 90; the pre-signup surface in access mode is the Cloudflare Access application's own
login page, not Rhapto code (plan-review minor 8 -- the earlier claim that Landing.tsx renders
pre-sign-in in access mode was checked against Task 2's TokenGate and found false).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Note for Delivery (role 7), not a step in this plan:** the cron install (`0 3 * * *
BACKUP_DIR=/var/backups/rhapto scripts/backup-db.sh >> /var/log/rhapto-backup.log 2>&1`, already
documented in the script's header), wiring `rhapto backups check` into daily monitoring, adding the
90+14-day promise to the Cloudflare Access application's login-page customisation, and the deletion
of the ad-hoc `/root/rhapto-pre-0010-*.sql` dumps are all operational actions against the production
host/Cloudflare dashboard, not code changes — they belong to role 7 ("Delivery never runs unprompted
for anything irreversible"), and this task's job is only to make the tooling and the promise correct,
which it now is.

**Acceptance criteria advanced:** 15 (backup retention does not touch the owner's live data; it
bounds how long deleted data survives), and the Owner-decision-Q3 backup requirement generally
(no single numbered AC maps directly to backups — Q3's four bullets are the requirement, and all four
are now met: cron documented for installation, ad-hoc dumps identified for cleanup by Delivery,
pre-migration dumps reach the pruner, and post-restore prune is mandatory).

---

## Self-review

### Plan-review resolution log

An independent plan review of the previous version of this document returned NOT SAFE TO EXECUTE (7
Critical, 11 Important, 8 Minor). Every finding was either fixed in place or answered explicitly
below; none was silently dropped.

**A scoped re-review of that fix pass then found: I9's claimed fix was absent from the actual code
(the lifespan body never contained the non-empty check the resolution log described — now added for
real, Task 3 Step 10); and the fixes themselves introduced six new blockers, all now fixed:**
`MeOut` gaining two required fields broke `apps/web`'s typecheck at `TailorButton.test.tsx:72,245`
(fixed in Task 1 and Task 6, each extending both literals); Task 4's dead-code deletion reds
`test_scoring_service.py` and two `test_worker_discovery.py` tests because "the only caller was
`worker/main.py`" was asserted rather than grepped (fixed — Task 4 Step 9 now deletes the tests too);
`test_pdf_concurrency_gate.py` requested the `worker_ctx` fixture from a directory it isn't defined in
(fixed — moved to `tests/api/`); `route.test.ts` indexed `calls[0][1]` under
`noUncheckedIndexedAccess` (fixed with `calls[0]?.[1]`); `mark_seen`'s `except` had no `rollback()`
(fixed); and migration `0011` left the owner's `seeded_at` NULL, so the bootstrap endpoint would have
run a backfill over the owner's live account the first time he signed in post-migration (fixed —
`0011` now backfills `seeded_at = now()` for every pre-existing row). Four stale cross-references left
by the first renumbering pass were also corrected, and the A5 seed's idempotency marker was upgraded
from a check-then-write to an atomic `UPDATE ... RETURNING`, per the re-review's recommendation.

**Critical — all fixed:**

| # | Finding | Fix | Where |
|---|---|---|---|
| C1 | Circular import between `auth.py` and `deps.py` | `auth.py` reads `request.app.state.rhapto` directly (a `TYPE_CHECKING`-only import of `AppState`); it no longer imports anything from `deps.py` at runtime | Task 1 Step 7 |
| C2 | `NEXT_PUBLIC_API_URL=""` fell back to `localhost:8000` (`\|\|` treats `""` as falsy) | `DEFAULT_API_URL`/`getSettings()` distinguish `undefined` from `""` explicitly; `SAME_ORIGIN_DEPLOYMENT` sentinel added | Task 2 Steps 1-4 |
| C3 | `TokenGate` gated every route on a `localStorage` token access-mode users never have | `TokenGate` unlocks on `useMe()` succeeding when `SAME_ORIGIN_DEPLOYMENT`; `MeOut.auth_mode` added for good measure (Task 1) though `TokenGate` ends up not needing to read it directly | Task 1 Step 10, Task 2 Step 12-13 |
| C4 | New `ctx["engine"]`/`ctx["redis"]` reads broke `worker_ctx`, `ctx_for`, and `test_registry` | Both fixtures gain the keys; the two `poll_all_sources`-level tests that asserted the deleted inline loop move to `poll_user`; `test_registry`'s expected set gains `"poll_user"` | Task 4 Step 7 |
| C5 | Backfill could violate `uq_jobs_user_source_external`, bricking sign-in | `DISTINCT ON (source, COALESCE(external_id, dedupe_hash))` replaces `DISTINCT ON (dedupe_hash)`; `NOT EXISTS` extended to `(user_id, source, external_id)`; bare `ON CONFLICT DO NOTHING` added — all three, not alternatives, per the review's own ruling | Task 5 Step 3 |
| C6 | Seeding inside `current_user` raced and made every endpoint pay for it | `get_or_create_user` gets `ON CONFLICT (email) DO NOTHING`; seeding moved entirely out of `current_user` into a dedicated, idempotent `POST /api/v1/me/bootstrap` | Task 3 Step 8, Task 5 Step 5 |
| C7 | `session.get` after a DB-level cascade returned the stale identity-mapped row (`expire_on_commit=False`) | Both affected tests call `session.expunge_all()` after the commit, forcing a fresh read | Task 7 Step 1 |

**Important — all fixed:**

| # | Finding | Fix | Where |
|---|---|---|---|
| I1 | `derive_searches` at first sign-in was a guaranteed no-op (zero tracks) | Dropped from A5 entirely; explicitly left to Phase D | Task 5 (scope note) |
| I2 | Test indexed `list_jobs`'s return as bare `Job` rows; it returns `list[tuple[Job, str \| None]]` | Test corrected to `rows[0][0].best_fit` | Task 5 (backfill test file) |
| I3 | PDF concurrency test was vacuous (no `Package` rows, passed with or without the lock) | Real `Job`/`Package` rows inserted; assertion tightened to `== 1` | Task 4 Step 10 |
| I4 | Planned `localStorage` namespacing targeted `lib/skipped.ts`, which has no live callers | Dropped entirely; verified `apply-prompt.ts`'s job-id keys cannot collide across accounts (job ids are per-row UUIDs); AC 11 re-justified on the stronger, verified basis that no identity-bearing state is stored at all | Task 2 (rewritten) |
| I5 | `mark_seen` added a `SELECT` to every request | Single atomic `UPDATE ... WHERE ... AND last_seen_at < now() - interval '1 hour'`, no read | Task 6 Step 3 |
| I6 | Prune cron had no exemption path, no last-account guard, no user-facing notice | `rhapto accounts exempt`, `would_delete_everyone` guard (CLI and cron), `MeOut.deletion_due_at` + `DeletionBanner` | Task 6 Steps 6-7, Task 7 Steps 5-6 |
| I7 | Nothing checked that the backup cron actually ran | `rhapto backups check`, exit 1 if no dump newer than 48h | Task 8 Step 5 |
| I8 | JWKS cache reset its TTL on a failed fetch and never evicted a rotated key | `_last_attempt_at` separated from `_fetched_at`; key set replaced (not merged) on success, previous set retained as fallback; dead `PyJWKClient` removed | Task 3 Step 5 |
| I9 | No startup check that `RHAPTO_ACCESS_TEAM`/`_AUD` are non-empty (a prior fix pass claimed this in prose without the code containing it — caught by re-review) | A real `if not settings.rhapto_access_team or not settings.rhapto_access_aud: raise RuntimeError(...)` in the lifespan body, plus `test_startup_refuses_empty_access_team_or_aud`; the list-valued-`aud` regression test added separately | Task 3 Step 10, Step 12 |
| I10 | `db/repositories/jobs.py` imported the whole discovery stack via `SOURCES` | `backfill_public_jobs` takes `public_sources: Sequence[str]`; caller supplies `list(SOURCES.keys())` | Task 5 Step 3 |
| I11 | Tests planned for a non-existent `tests/cli/` directory | Moved to `tests/unit/`, alongside the existing `test_cli.py` | Tasks 3, 6, 7 |

**Minor — all fixed:** dead `object.__setattr__` prose removed and replaced with a verified plain
assignment (Task 1 Step 9); settings-mutation-without-restore now stated as safe rather than left
unexplained (Task 3, test file preamble); `accounts set-email` casefolds its lookup and checks the
target email is free (Task 3 Step 11); `sweep_orphan_files` skips a non-`SAFE_ID` directory name
instead of raising (Task 7 Step 3); the proxy route's `duplex` option is typed via an intersection
type instead of a brittle `@ts-expect-error`, `..` path segments are rejected, and `range`/
`accept-encoding` are forwarded (Task 2 Step 9); stale `0010_shared_job_pool.cpython-312.pyc` flagged
for deletion (Task 1 Step 3); `shutil.which` replaces `which` in the backup-script test so it skips
cleanly on Windows (Task 8 Step 3); the pre-signup promise's real placement is corrected — it is the
Cloudflare Access login page in `access` mode, not `Landing.tsx`, which never renders there (Task 8).

**The reviewer's ruling on this plan's three self-flagged calls, and how each landed:**

1. **A5's trigger point** — the reviewer agreed identity-first-without-Phase-D was right, but ruled
   putting the seed inside `current_user` was wrong on three counts (turns a data bug into "cannot
   sign in", races, and orphans `derive_searches`). **Adopted in full**: the seed is now
   `POST /api/v1/me/bootstrap`. On the no-advisory-lock departure specifically, the re-review
   accepted the plumbing argument (`AppState.engine` really is `None` whenever `session_factory` is
   injected, which every test does) but corrected the "never a duplicate" claim: a `check-then-write`
   version could still double-insert rows with `external_id IS NULL`, which fall outside the partial
   unique index. **Adopted the re-review's cheaper alternative**: the marker is now claimed
   atomically, `UPDATE users SET seeded_at = now() WHERE id = :u AND seeded_at IS NULL RETURNING id`,
   and the backfill runs only if a row comes back. This closes the race completely — Postgres's
   row-level lock on the `UPDATE` means at most one of two concurrent callers ever gets the row —
   with no new engine-access plumbing and no lock. Nothing to accept as residual risk here anymore.
2. **`NOT EXISTS` vs `ON CONFLICT`** — the reviewer ruled the premise correct but the conclusion
   incomplete: both are needed, plus the `DISTINCT ON` grouping fix. **Adopted in full**, Task 5 Step 3.
3. **Files-before-rows over arq cancellation** — accepted as right, with one caveat: the orphan sweep
   must not share the prune's try-less cron. **Adopted in full**: the sweep now runs in its own
   `try/except`, Task 7 Step 6.

### Spec coverage

| AC | Task(s) | Status |
|---|---|---|
| 1 | 3, 5 | Met — allowlisted sign-in creates an account; no owner action after the invite; `TokenGate` (Task 2) is what actually lets the person reach the app |
| 2 | 2, 3 | Met — IdP login only, refused at the edge/API for non-members, no account shell created |
| 3 | 5 | Partially met — the grid is full, not empty; the setup-*flow* itself (Phase D wizard) is out of scope, unbuilt by a separate spec |
| 4 | — | Deferred — pre-existing (`LlmTestOut`/`is_llm_configured` already gate this for a single user); untouched by multi-tenancy, no task needed |
| 5 | — | Deferred to Phase D (location-preference collection during setup) |
| 6 | 1, 2 | Met — identity resolution plus the pre-existing `UserScopedMixin` cascade on every table |
| 7 | 5 | Met — A5 copies only public JD text, never a block/verified fact/extract |
| 8 | 7 | Met — `delete_account` cascades only within the deleted user's own FK graph, proven by a test that now actually observes it (C7) |
| 9 | — | Deferred to Phase C, explicitly. `check_visibility`'s empty-`context_tags` no-op (architecture §3.5 rule 6) is a real bug, but the risk it closes — a *shared* cached extract — cannot exist until `posting_extracts` exists; in Phase A/B, `extracted_json` stays per-user and A5 explicitly never copies it. Flagged for Phase C's plan. |
| 10 | 4 | Met (mostly pre-existing) — per-task LLM key resolution already isolates cost; Task 4's fan-out prevents one user's poll from starving another's CPU budget |
| 11 | 1, 2 | Met — per-request identity, and no identity-bearing `localStorage` state exists at all in access mode (a stronger property than the namespacing originally claimed, per I4) |
| 12 | — | Deferred — pre-existing single-user behaviour, unaffected |
| 13 | — | Deferred — pre-existing (`is_llm_configured`), unaffected |
| 14 | — | Deferred to Phase D / pre-existing empty-state copy, unaffected by tenancy |
| 15 | 1, 3, 5, 6, 8 | Met — additive migration, startup assertion + `set-email` CLI, A5 reads the owner's rows without mutating them, `exempt`/`deletion_due_at`/`DeletionBanner` keep the prune cron from becoming a new threat to the owner's own data, backup retention doesn't touch live data |
| 16 | 7 | Met — deletion never rotates or breaks another account's stored key, because nothing is shared |

AC 4/5/12/13/14 are correctly out of this plan's scope: pre-existing single-user behaviours the
functional spec asks multi-tenancy not to break, untouched by any task above.

### Placeholder scan

Reviewed every code block above for "TBD", "implement later", "add appropriate handling", or a step
that names behaviour without showing it. Two spots are **not** placeholders but are worth
distinguishing from the failure mode the prompt warns against:

- Task 1 Step 7's `access` mode branch raises a real, tested `HTTPException(501, ...)` — a defined
  behaviour for an unreachable code path, replaced by real logic in Task 3, not a stub left unfilled.
- Task 8 Step 1 asks the implementer to check for a runbook file before deciding where the
  post-restore step lives, because no such file was found in this checkout during this plan's
  research; this is a real decision point stated as one, not a deferred implementation.

No step describes a test without a body, references a function or type not defined by an earlier
task's Interfaces block, or says "similar to Task N" in place of code.

### Type-consistency check

- `Principal` (Task 1: `mode: AuthMode, subject: str, email: str`) is used identically in Task 3's
  rewrite of `resolve_principal` and nowhere renamed or reshaped.
- `current_user`'s return type (`uuid.UUID`) and its being resolvable via bare `Depends(current_user)`
  is preserved across Tasks 1, 3, 6 despite the function's internal parameter list growing (adding
  `session`, then reusing it) — every call site in the routers uses `Annotated[uuid.UUID,
  Depends(current_user)]`, which never enumerates `current_user`'s own parameters. Task 5 does **not**
  touch `current_user` at all (this was the whole point of the C6 fix).
- `backfill_public_jobs(session, user_id, *, public_sources: Sequence[str]) -> int` (Task 5) matches
  its only call site (the new `POST /me/bootstrap` handler) and its test suite exactly — no other task
  calls or renames it, and no task imports `SOURCES` into the DB layer (I10).
- `mark_seen`/`inactive_accounts`/`would_delete_everyone` (Task 6) keep the exact signatures Task 7's
  CLI and cron consume: `mark_seen(session, user_id) -> None`, `inactive_accounts(session, cutoff) ->
  list[User]`, `would_delete_everyone(all_ids, to_delete_ids) -> bool`.
- `delete_account(session, storage, user_id) -> DeletionReport` (Task 7) is used with the same three
  positional arguments in the CLI's `prune --yes`, `accounts delete`, and the worker's
  `prune_inactive_accounts` — no task calls it with a different argument order.
- `poll_user(ctx, user_id: str) -> None` (Task 4) is registered in both `TASKS` and
  `WorkerSettings.functions` with the same name string `"poll_user"` used by `poll_all_sources`'s
  `enqueue_job` call, and by the updated `ctx_for`/`worker_ctx` fixtures that now also carry `engine`/
  `redis` — verified these spellings match exactly across all four files C4 touches.
- `BootstrapOut.seeded: bool` (Task 5) and `MeOut.auth_mode`/`MeOut.deletion_due_at` (Tasks 1, 6) are
  each produced by exactly one endpoint and consumed by exactly one web-side caller
  (`useBootstrap`/`TokenGate` is not one of them — it reads `SAME_ORIGIN_DEPLOYMENT` and `useMe().isSuccess`,
  not `auth_mode`, a deliberate simplification noted in Task 2).
