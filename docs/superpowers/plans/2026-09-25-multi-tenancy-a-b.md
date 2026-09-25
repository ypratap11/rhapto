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

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine


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
```

- [ ] **Step 2: Run it to see it fail**

Run (from `apps/api`): `pytest tests/db/test_migrations_0011.py -v`
Expected: FAIL — `migrated_db` fixture upgrades to `head`, which is still `0010`; the new columns
don't exist, so the `assert` fails (or `command.upgrade` errors if the file is entirely absent —
either way, not a pass).

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
Expected: PASS.

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

- [ ] **Step 14: Commit**

```bash
git add apps/api/src/rhapto/api/auth.py apps/api/src/rhapto/api/deps.py \
  apps/api/src/rhapto/config.py apps/api/src/rhapto/db/models.py \
  apps/api/src/rhapto/api/schemas.py apps/api/src/rhapto/api/routers/meta.py \
  apps/api/alembic/versions/0011_user_lifecycle_columns.py \
  packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts \
  apps/api/tests/api/test_auth_principal.py apps/api/tests/api/test_meta.py \
  apps/api/tests/db/test_migrations_0011.py
git commit -m "$(cat <<'EOF'
Introduce Principal/resolve_principal under current_user (A1)

current_user's external contract (Depends(current_user) -> uuid.UUID) is unchanged, so no router
is touched. token mode is re-expressed on top of the new Principal type with byte-identical
behaviour (same compare_digest check, same 401/503 bodies). access mode is a defined 501 stub,
replaced by Task 3. auth.py reads request.app.state.rhapto directly instead of importing deps.get_state,
so the two modules do not import each other (plan-review C1). Migration 0011 adds users.idp_subject,
users.last_seen_at, users.exempt_from_pruning and users.seeded_at -- additive, no reader changes yet.
MeOut gains auth_mode so the web app (Task 2) can tell modes apart.

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
  the "Connect to your Rhapto API" card forever. Fixed in Step 6-8 by making `TokenGate` unlock on
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
    const forwardedHeaders = fetchSpy.mock.calls[0][1]?.headers as Headers;
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

```typescript
// apps/web/src/components/shell/TokenGate.test.tsx — additions at the top of the file
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { vi } from "vitest";

vi.mock("@/lib/api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/client")>()),
  SAME_ORIGIN_DEPLOYMENT: false,
}));
vi.mock("@/lib/api/queries", () => ({ useMe: vi.fn(() => ({ isPending: true, isSuccess: false })) }));

function renderGate(children: React.ReactNode) {
  const client = new QueryClient();
  return render(<QueryClientProvider client={client}>{children}</QueryClientProvider>);
}
```

Every existing `render(<TokenGate>...)` call in this file becomes `renderGate(<TokenGate>...)`; their
assertions are otherwise unchanged, since `vi.mock("@/lib/api/client", ...)` pins
`SAME_ORIGIN_DEPLOYMENT` to `false` for all of them, exercising the same token-mode branch they always
did. Add a new `describe` block for the access-mode branch, overriding both mocks per test:

```typescript
// apps/web/src/components/shell/TokenGate.test.tsx — new describe block
import { useMe } from "@/lib/api/queries";
import * as clientModule from "@/lib/api/client";

describe("TokenGate in access mode", () => {
  beforeEach(() => {
    vi.mocked(clientModule).SAME_ORIGIN_DEPLOYMENT = true;
  });
  afterEach(() => {
    vi.mocked(clientModule).SAME_ORIGIN_DEPLOYMENT = false;
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
- Modify: `apps/api/pyproject.toml` (add `pyjwt[crypto]>=2.9`)
- Test: `apps/api/tests/api/test_access_mode.py`
- Test: `apps/api/tests/cli/test_accounts_set_email.py`

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

```python
# apps/api/src/rhapto/api/app.py — replace the lifespan body's bootstrap block (lines 74-78)
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        warn_if_fake_llm(settings)
        if settings.rhapto_auth_mode == "access":
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

- [ ] **Step 10: Add `rhapto accounts set-email`**

```python
# apps/api/src/rhapto/cli/main.py — new sub-app, following the existing db_app/profile_app pattern
accounts_app = typer.Typer(no_args_is_help=True, help="Account maintenance.")
app.add_typer(accounts_app, name="accounts")


@accounts_app.command("set-email")
def accounts_set_email(old_email: str = typer.Argument(...), new_email: str = typer.Argument(...)) -> None:
    """Rename an account's email -- run before flipping RHAPTO_AUTH_MODE to access, so the owner's
    bootstrapped account matches his Cloudflare Access email exactly."""
    settings = Settings()

    async def rename() -> bool:
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as session:
                from sqlalchemy import select as sa_select

                from rhapto.db.models import User

                user = await session.scalar(sa_select(User).where(User.email == old_email))
                if user is None:
                    return False
                user.email = new_email.casefold()
                await session.commit()
                return True
        finally:
            await engine.dispose()

    if not asyncio.run(rename()):
        typer.echo(f"error: no account found with email {old_email!r}", err=True)
        raise typer.Exit(1)
    typer.echo(f"renamed {old_email} -> {new_email}")
```

- [ ] **Step 11: Write the access-mode integration tests**

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
        count = await session.scalar(select(User).where(User.email == "stranger@gmail.com"))
    assert count is None


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
```

```python
# apps/api/tests/cli/test_accounts_set_email.py
from __future__ import annotations

from typer.testing import CliRunner

from rhapto.cli.main import app

runner = CliRunner()


def test_set_email_renames_an_existing_account(migrated_db, monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("RHAPTO_SECRET_KEY", "irrelevant-for-this-command")
    # seed the owner account this command will rename
    import asyncio

    from rhapto.db.repositories.users import get_or_create_user
    from rhapto.db.session import make_engine, make_session_factory

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
```

- [ ] **Step 12: Run the new tests, then the full suite**

Run: `pytest tests/api/test_access_mode.py tests/cli/test_accounts_set_email.py -v` — expect PASS.
Run: `pytest` — expect green, including the four A1-listed token-mode tests unmodified.
Run: `ruff check .` and `mypy src` — expect clean (add `pyjwt` to the mypy override list in
`pyproject.toml` only if `mypy src` reports missing stubs for it; PyJWT ships inline types, so this
is likely unnecessary — verify against the actual `mypy src` output rather than pre-emptively adding
an override).

- [ ] **Step 13: Commit**

```bash
git add apps/api/src/rhapto/api/auth.py apps/api/src/rhapto/api/deps.py apps/api/src/rhapto/api/app.py \
  apps/api/src/rhapto/config.py apps/api/src/rhapto/cli/main.py apps/api/pyproject.toml \
  apps/api/tests/api/test_access_mode.py apps/api/tests/cli/test_accounts_set_email.py
git commit -m "$(cat <<'EOF'
Implement Cloudflare Access mode: JWKS verification, invite allowlist, bootstrap suppression (A3)

Access mode verifies the Cf-Access-Jwt-Assertion RS256 against a last-good-cached JWKS, rejects a
duplicated assertion header with 400, and enforces RHAPTO_ALLOWED_EMAILS/_DOMAINS a second time in
the API (403, no users row created, if the email is not on the list -- non-membership must not
create an account shell). The token-mode bootstrap that would otherwise create a second, empty
owner account is suppressed in access mode, replaced by a startup assertion that refuses to start
unless an allowed users row already exists. `rhapto accounts set-email` lets the owner correct
RHAPTO_USER_EMAIL before the mode flip.

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

**Files:**
- Modify: `apps/api/src/rhapto/worker/tasks.py` (new `poll_user` task; `poll_all_sources` becomes a
  thin dispatcher; advisory lock in `poll_user` and `poll_now`; concurrency-1 gate in
  `render_package_pdf`)
- Modify: `apps/api/src/rhapto/worker/main.py` (register `poll_user`; delete
  `enqueue_location_backfill`/`_location_backfill_done`/the `on_startup` call to it)
- Modify: `apps/api/src/rhapto/services/scoring.py` (delete `users_needing_location_backfill`, now
  unused)
- Test: `apps/api/tests/unit/test_poll_fan_out.py`
- Test: `apps/api/tests/unit/test_pdf_concurrency_gate.py`

**Interfaces:**
- Consumes: `ctx["session_factory"]`, `ctx["engine"]` (set in `on_startup`, `worker/main.py:75-76`,
  already present on every task's `ctx: dict[str, Any]`), `list_user_ids` (unchanged,
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

- [ ] **Step 7: Add the PDF concurrency-1 gate**

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

- [ ] **Step 8: Delete the dead location-backfill code**

```python
# apps/api/src/rhapto/worker/main.py — delete enqueue_location_backfill,
# _location_backfill_done, the `await enqueue_location_backfill(ctx)` call inside on_startup,
# and the `from rhapto.services.scoring import users_needing_location_backfill` import.
```

```python
# apps/api/src/rhapto/services/scoring.py — delete users_needing_location_backfill entirely
# (verify with `grep -rn users_needing_location_backfill apps/api/src apps/api/tests` that no
# other caller remains before deleting; the only caller was worker/main.py, just removed).
```

- [ ] **Step 9: Write the concurrency-gate test**

```python
# apps/api/tests/unit/test_pdf_concurrency_gate.py
from __future__ import annotations

import asyncio
from typing import Any

from rhapto.worker import tasks as tasks_module
from rhapto.worker.tasks import render_package_pdf


async def test_two_concurrent_renders_never_overlap(worker_ctx: dict[str, Any], monkeypatch) -> None:
    concurrent = 0
    max_concurrent = 0

    def fake_render_pdf(package_id: str, soffice_binary: str) -> None:
        nonlocal concurrent, max_concurrent
        concurrent += 1
        max_concurrent = max(max_concurrent, concurrent)
        import time

        time.sleep(0.05)
        concurrent -= 1
        return None

    monkeypatch.setattr(tasks_module.PackageStorage, "render_pdf", staticmethod(fake_render_pdf))
    await asyncio.gather(
        render_package_pdf(worker_ctx, "00000000-0000-0000-0000-000000000000"),
        render_package_pdf(worker_ctx, "00000000-0000-0000-0000-000000000001"),
    )
    assert max_concurrent <= 1
```

This test needs two real `Package` rows with `docx_path` set to exercise the lock past the early
`return`; the implementer adds a small fixture inserting two packages via the existing
`persist_package`/`package_repo` helpers used elsewhere in the suite (e.g. mirroring the setup in
`apps/api/tests/unit/test_worker_tasks.py`, if that file exists — confirm the exact existing helper
by grepping `apps/api/tests` for `docx_path=` before duplicating one).

- [ ] **Step 10: Run the new tests, then the full suite**

Run: `pytest tests/unit/test_poll_fan_out.py tests/unit/test_pdf_concurrency_gate.py -v` — expect PASS.
Run: `pytest` — expect green. Existing `poll_now`/`poll_all_sources` tests (search
`apps/api/tests` for `poll_now\|poll_all_sources` to find and update any test that asserted the old
inline-loop behaviour of `poll_all_sources`, since it now only enqueues rather than polling).
Run: `ruff check .` and `mypy src` — expect clean.

- [ ] **Step 11: Commit**

```bash
git add apps/api/src/rhapto/worker/tasks.py apps/api/src/rhapto/worker/main.py \
  apps/api/src/rhapto/services/scoring.py \
  apps/api/tests/unit/test_poll_fan_out.py apps/api/tests/unit/test_pdf_concurrency_gate.py
git commit -m "$(cat <<'EOF'
Per-user poll fan-out, advisory lock, PDF concurrency-1 gate (A4)

poll_all_sources now enqueues one poll_user arq job per user and returns immediately, instead of
polling every user inline inside one 600s task -- two users used to exceed job_timeout and the
second user's poll was killed mid-run. poll_user and poll_now both take a per-user Postgres
advisory lock so a cron poll and a hand-triggered poll can never interleave for the same account.
render_package_pdf and tailor_job's PDF step share a process-wide asyncio.Lock, since two
concurrent LibreOffice renders can exceed the worker's 2GB cap. Deleted the location-tier backfill
one-shot, five migrations past its usefulness.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** 6 (a fan-out is what makes account #2's poll not corrupt/kill
account #1's), 10 (contained cost per user is meaningless if one user's poll starves another's).

---

## Task 5 (A5): The full first screen — synchronous backfill on first sign-in

**Scope decision, stated explicitly:** the architecture's §2.4 describes the backfill running
"inside the onboarding request that completes setup" — but the onboarding wizard is Phase D, owned by
a separate, unbuilt spec, and is out of scope here. Wiring A5 to a not-yet-built endpoint would leave
Phase A incomplete on its own, contradicting the architecture's own "Ships" criterion for Phase A
("an invited account reaches a full, live job list in under a second"). This task instead wires the
backfill into the exact moment functional-spec §3 calls "signup" — **the first successful sign-in**,
i.e. Task 3's `current_user` access-mode branch, at the point a `users` row is newly created. This
keeps Phase A fully self-contained; Phase D's onboarding wizard (when built) simply lands on an
already-full grid rather than triggering the fill itself.

Verified before writing: `apps/api/src/rhapto/db/models.py:164-205` (`Job` has 27 columns total,
counting `UserScopedMixin.user_id` and `TimestampMixin`'s two columns; no unique constraint on
`(user_id, dedupe_hash)` exists, so idempotency in Step 3's SQL is via `NOT EXISTS`, not `ON CONFLICT`);
`apps/api/src/rhapto/services/discovery/sources/__init__.py:16` (`SOURCES: dict[str, SourceClass] =
{}`, the positive-allowlist registry); `apps/api/src/rhapto/services/discovery/poller.py:45`
(`INGEST_MAX_AGE_DAYS = 90`); `apps/api/src/rhapto/db/repositories/jobs.py:16-40` (`create_job`
defaults `source="manual"`, confirming `"manual"` is never in `SOURCES`); `apps/api/src/rhapto/services/discovery/search.py:62-89`
(`derive_searches(session, user_id) -> list[SearchRow]`, already idempotent — returns `[]` if the
user already has searches); `apps/api/src/rhapto/db/repositories/jobs.py:146-148,180`
(`list_jobs`'s default `bucket == "fit"` **already** includes `Job.best_fit.is_(None)` rows and
orders them `nulls_last` rather than hiding them); `apps/api/src/rhapto/components` — verified
`apps/web/src/components/ui/fit-ring.tsx:42-56` **already** renders a `null` fit as a dashed ring with
`title="Not scored yet"` rather than hiding the card. **Both of the architecture's "must not
silently no-op" first-screen requirements are already satisfied by existing code** — this task adds
a regression test pinning that behaviour for newly backfilled rows, rather than new product code.

**Files:**
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py` (new `backfill_public_jobs`)
- Modify: `apps/api/src/rhapto/api/deps.py` (`current_user`'s access-mode branch: seed a newly
  created account)
- Test: `apps/api/tests/db/test_backfill_public_jobs.py`
- Test: `apps/api/tests/api/test_access_mode.py` (extend: new-account seeding, end-to-end)

**Interfaces:**
- Consumes: `SOURCES` (`services/discovery/sources`, unchanged), `derive_searches` (unchanged,
  `services/discovery/search.py`), `is_allowed_email`/`get_or_create_user` (Task 3).
- Produces:
  ```python
  # rhapto/db/repositories/jobs.py
  async def backfill_public_jobs(session: AsyncSession, user_id: uuid.UUID) -> int:
      """Row count inserted. Idempotent: safe to call more than once for the same user."""
  ```
  No other task in this plan calls `backfill_public_jobs`; Phase D (out of scope) is free to call it
  again from its own onboarding-completion step with no behaviour change, since it is idempotent.

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


async def test_copies_a_public_job_into_the_new_account(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id)
    await session.commit()

    count = await backfill_public_jobs(session, newcomer.id)
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

    count = await backfill_public_jobs(session, newcomer.id)
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

    await backfill_public_jobs(session, newcomer.id)
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

    count = await backfill_public_jobs(session, newcomer.id)
    await session.commit()
    assert count == 0


async def test_is_idempotent(session: AsyncSession) -> None:
    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse")
    await session.commit()

    first = await backfill_public_jobs(session, newcomer.id)
    await session.commit()
    second = await backfill_public_jobs(session, newcomer.id)
    await session.commit()

    assert first == 1
    assert second == 0
    rows = list(await session.scalars(select(Job).where(Job.user_id == newcomer.id)))
    assert len(rows) == 1


async def test_unscored_backfilled_rows_stay_in_the_default_fit_bucket(session: AsyncSession) -> None:
    """Pins the existing (pre-A5) behaviour this task relies on rather than reimplementing:
    best_fit IS NULL rows are not filtered out of the default grid view."""
    from rhapto.db.repositories.jobs import list_jobs

    owner = await get_or_create_user(session, "owner@example.com")
    newcomer = await get_or_create_user(session, "newcomer@example.com")
    await _seed_job(session, owner.id, source="greenhouse")
    await session.commit()
    await backfill_public_jobs(session, newcomer.id)
    await session.commit()

    rows = await list_jobs(session, newcomer.id, bucket="fit")
    assert len(rows) == 1
    assert rows[0].best_fit is None
```

(`list_jobs`'s exact return type/signature must be confirmed against
`apps/api/src/rhapto/db/repositories/jobs.py` by the implementer before writing this last test —
verified in this session that `list_jobs(session, user_id, *, search=None, track=None, bucket=None,
...)` exists at line 63 and returns rows filtered by the `bucket` logic at lines 144-151; adjust the
call/assertion to match its actual return shape (a list of `Job` ORM rows or a mapped result) as read
directly from the function body.)

- [ ] **Step 2: Run the tests to see them fail**

Run: `pytest tests/db/test_backfill_public_jobs.py -v`
Expected: FAIL — `backfill_public_jobs` does not exist yet (import error).

- [ ] **Step 3: Implement `backfill_public_jobs`**

```python
# apps/api/src/rhapto/db/repositories/jobs.py — new function
from rhapto.services.discovery.sources import SOURCES

PUBLIC_BACKFILL_MAX_AGE_DAYS = 90  # matches services.discovery.poller.INGEST_MAX_AGE_DAYS


async def backfill_public_jobs(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Seed a brand-new account's first screen with every live public-source job already
    discovered on this instance, cached embedding included, at zero LLM/embedding cost.

    Positive allowlist only (`SOURCES.keys()`) -- never a denylist -- so `manual` (never
    registered in SOURCES) and any future private-ingest source are excluded structurally, not by
    name. Does not copy: extracted_json (another user's ungoverned LLM output), repost_of/
    search_id (foreign keys into another user's own rows -- copying them would violate the FK or
    leak another user's job id), best_fit/best_track_id/location_tier/hidden_at/rescued (another
    user's opinions, meaningless for a new account). Idempotent via NOT EXISTS on
    (user_id, dedupe_hash): there is no unique constraint enforcing that pair today (verified
    against db/models.py), so a retried call is made safe here rather than by a migration this
    task deliberately does not need.
    """
    public_sources = list(SOURCES.keys())
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
                SELECT DISTINCT ON (dedupe_hash) *
                FROM jobs
                WHERE source = ANY(:public_sources)
                  AND unlisted_at IS NULL
                  AND (posted_at IS NULL OR posted_at > :cutoff)
                ORDER BY dedupe_hash, discovered_at ASC
            ) j
            WHERE NOT EXISTS (
                SELECT 1 FROM jobs existing
                WHERE existing.user_id = :user_id AND existing.dedupe_hash = j.dedupe_hash
            )
            """
        ),
        {"user_id": str(user_id), "public_sources": public_sources, "cutoff": cutoff},
    )
    return result.rowcount or 0
```

Add `from sqlalchemy import text` and `from datetime import UTC, datetime, timedelta` to
`jobs.py`'s imports if not already present (verified `datetime`, `UTC`, `timedelta` are already
imported at the top of the file; `text` is not — add it to the existing `from sqlalchemy import
CursorResult, and_, delete, func, not_, nulls_last, or_, select` line).

- [ ] **Step 4: Run the backfill tests again**

Run: `pytest tests/db/test_backfill_public_jobs.py -v`
Expected: all six PASS.

- [ ] **Step 5: Wire the seed into new-account creation**

```python
# apps/api/src/rhapto/api/deps.py — current_user's access-mode branch (from Task 3 Step 8)
from rhapto.db.repositories.jobs import backfill_public_jobs
from rhapto.services.discovery.search import derive_searches


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
    existing = await session.scalar(select(User).where(User.email == principal.email))
    if existing is not None:
        await session.commit()
        return existing.id
    user = await get_or_create_user(session, principal.email)
    # First sign-in for this email: this *is* signup (functional-spec.md §3). Fill the screen
    # synchronously, in this same request/transaction -- sub-second, zero LLM calls, zero new
    # embeddings (architecture.md §2.4) -- rather than waiting on the cron's first poll.
    await backfill_public_jobs(session, user.id)
    await derive_searches(session, user.id)
    await session.commit()
    return user.id
```

Add `from sqlalchemy import select` and `from rhapto.db.models import User` to `deps.py`'s imports.

- [ ] **Step 6: Write the end-to-end seeding test**

```python
# apps/api/tests/api/test_access_mode.py — append
async def test_first_sign_in_backfills_the_new_accounts_first_screen(
    app: FastAPI, rsa_keypair, signed_assertion, monkeypatch, session_factory
) -> None:
    from rhapto.db.repositories.jobs import backfill_public_jobs
    from rhapto.db.repositories.users import get_or_create_user

    async with session_factory() as session:
        owner = await get_or_create_user(session, "owner@example.com")
        from rhapto.db.models import Job
        from datetime import UTC, datetime

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
    cache._fetched_at = __import__("time").monotonic()
    monkeypatch.setitem(auth_module._jwks_caches, "test-team", cache)

    token = signed_assertion("newcomer@example.com")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        me_response = await c.get("/api/v1/me", headers={"Cf-Access-Jwt-Assertion": token})
        assert me_response.status_code == 200
        new_user_id = me_response.json()["user_id"]
        jobs_response = await c.get(
            "/api/v1/jobs", headers={"Cf-Access-Jwt-Assertion": token}
        )
    assert jobs_response.status_code == 200
    jobs = jobs_response.json()
    assert len(jobs) == 1
    assert jobs[0]["best_fit"] is None
```

(`import httpx` and `from rhapto.api.deps import AppState` are already imported earlier in this test
file, per Task 3 Step 11.)

- [ ] **Step 7: Run it, then the full suite**

Run: `pytest tests/api/test_access_mode.py -v` — expect PASS including the new test.
Run: `pytest` — expect green.
Run: `ruff check .` and `mypy src` — expect clean.

- [ ] **Step 8: Commit**

```bash
git add apps/api/src/rhapto/db/repositories/jobs.py apps/api/src/rhapto/api/deps.py \
  apps/api/tests/db/test_backfill_public_jobs.py apps/api/tests/api/test_access_mode.py
git commit -m "$(cat <<'EOF'
Seed a new account's first screen synchronously on first sign-in (A5)

backfill_public_jobs copies every live public-source job (positive SOURCES allowlist, never a
denylist) into a newly created account in one INSERT ... SELECT, cached jd_embedding included, at
zero LLM/embedding cost -- and never copies extracted_json, repost_of, search_id, or another
user's fit/track/hidden/rescued opinions. Wired into current_user's access-mode branch at the
moment a users row is first created, which is what functional-spec.md calls signup, rather than
into the not-yet-built onboarding wizard (Phase D, out of scope) -- keeping Phase A a complete,
self-contained ship. Confirmed (with a regression test) that list_jobs and FitRing already surface
best_fit IS NULL rows rather than hiding them; no product change was needed there.

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

Verified before writing: `users.last_seen_at`/`users.exempt_from_pruning` exist as of migration
`0011` (Task 1); no code reads or writes either column yet (grepped); `apps/api/src/rhapto/cli/main.py`
has no `accounts` sub-app before Task 3 adds `set-email` — this task adds `prune` to that same
sub-app.

**Files:**
- Create: `apps/api/src/rhapto/services/accounts.py`
- Modify: `apps/api/src/rhapto/api/deps.py` (`current_user`: fire-and-forget `mark_seen` call)
- Modify: `apps/api/src/rhapto/config.py` (`rhapto_inactive_days`)
- Modify: `apps/api/src/rhapto/cli/main.py` (`accounts prune --dry-run`)
- Test: `apps/api/tests/unit/test_accounts_lifecycle.py`
- Test: `apps/api/tests/cli/test_accounts_prune.py`

**Interfaces:**
- Consumes: `User.last_seen_at`, `User.exempt_from_pruning` (Task 1).
- Produces:
  ```python
  # rhapto/services/accounts.py
  async def mark_seen(session: AsyncSession, user_id: uuid.UUID) -> None: ...
  async def inactive_accounts(session: AsyncSession, cutoff: datetime) -> list[User]: ...
  ```
  Task 7 consumes both, plus adds `delete_account`/`sweep_orphan_files` to this same module.

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

- [ ] **Step 3: Implement `services/accounts.py`**

```python
# apps/api/src/rhapto/services/accounts.py
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User

logger = logging.getLogger("rhapto.services.accounts")

MARK_SEEN_THROTTLE = timedelta(hours=1)


async def mark_seen(session: AsyncSession, user_id: uuid.UUID) -> None:
    """Update last_seen_at, throttled to at most once per hour per user.

    Called from current_user on every authenticated request; a failure here must never fail the
    request it rides along with, so the caller wraps this in a try/except (architecture.md §4.1).
    """
    user = await session.get(User, user_id)
    if user is None:
        return
    if datetime.now(UTC) - user.last_seen_at < MARK_SEEN_THROTTLE:
        return
    user.last_seen_at = datetime.now(UTC)


async def inactive_accounts(session: AsyncSession, cutoff: datetime) -> list[User]:
    """Every non-exempt account whose last_seen_at is older than `cutoff`."""
    return list(
        await session.scalars(
            select(User).where(User.last_seen_at < cutoff, User.exempt_from_pruning.is_(False))
        )
    )
```

- [ ] **Step 4: Run the tests again**

Run: `pytest tests/unit/test_accounts_lifecycle.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `mark_seen` into `current_user`, fire-and-forget**

```python
# apps/api/src/rhapto/api/deps.py — current_user, both branches, right before each `return`
from rhapto.services.accounts import mark_seen
...
    if principal.mode == "token":
        if state.user_id is None:
            raise HTTPException(status_code=503, detail="server not ready")
        try:
            await mark_seen(session, state.user_id)
            await session.commit()
        except Exception:
            logger.exception("mark_seen failed for user %s; continuing the request", state.user_id)
        return state.user_id
```

(token mode's `current_user` did not previously take a `session` parameter — add
`session: Annotated[AsyncSession, Depends(get_session)]` to its signature; this is additive to the
signature Task 1 wrote, harmless since `Depends(current_user)` callers never see the parameter list.
Apply the same try/except-wrapped `mark_seen` + commit immediately before the access-mode branch's
final `return existing.id` and `return user.id` in Task 5's version of the function; the "new
account" path already commits after seeding, so `mark_seen` there is a no-op against a `last_seen_at`
that `server_default=now()` just set — call it anyway, before that commit, for one code path rather
than two.) Add `import logging` and a module `logger = logging.getLogger("rhapto.api.deps")` to
`deps.py` if it does not already have one (verified it does not).

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
```

- [ ] **Step 7: Write the CLI test**

```python
# apps/api/tests/cli/test_accounts_prune.py
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
```

- [ ] **Step 8: Run the new tests, then the full suite**

Run: `pytest tests/unit/test_accounts_lifecycle.py tests/cli/test_accounts_prune.py -v` — expect PASS.
Run: `pytest` — expect green.
Run: `ruff check .` and `mypy src` — expect clean.

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/rhapto/services/accounts.py apps/api/src/rhapto/api/deps.py \
  apps/api/src/rhapto/config.py apps/api/src/rhapto/cli/main.py \
  apps/api/tests/unit/test_accounts_lifecycle.py apps/api/tests/cli/test_accounts_prune.py
git commit -m "$(cat <<'EOF'
last_seen_at throttling, inactive_accounts query, prune --dry-run (B1a)

mark_seen updates users.last_seen_at on any authenticated request, throttled to once per hour, and
never fails the request it rides along with. inactive_accounts finds every non-exempt account past
RHAPTO_INACTIVE_DAYS (default 90). `rhapto accounts prune` lists them; --yes is a defined,
not-yet-wired error until Task 7 adds the real deletion path, so this command never destroys data
before that path exists.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Acceptance criteria advanced:** none new directly satisfied yet (AC 8/16 land in Task 7); this task
lays the read path Task 7's deletion trigger and Task 8's day-60 banner both need.

---

## Task 7 (B1b): `delete_account`, `sweep_orphan_files`, real `accounts prune --yes` / `accounts delete`

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

**Files:**
- Modify: `apps/api/src/rhapto/services/accounts.py` (`delete_account`, `sweep_orphan_files`)
- Modify: `apps/api/src/rhapto/cli/main.py` (`accounts prune --yes` calls `delete_account`;
  `accounts delete <email> --yes`)
- Modify: `apps/api/src/rhapto/worker/main.py` (daily prune cron)
- Test: `apps/api/tests/unit/test_delete_account.py`
- Test: `apps/api/tests/cli/test_accounts_delete.py`

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
    storage.write_docx(str(package_id), b"fake docx bytes")

    report = await delete_account(session, storage, user.id)
    await session.commit()

    assert report.package_files_deleted == 1
    assert await session.get(User, user.id) is None
    assert await session.get(Job, job.id) is None
    assert not storage.dir_for(str(package_id)).exists()


async def test_delete_account_never_touches_another_users_rows(session: AsyncSession, tmp_path: Path) -> None:
    storage = PackageStorage(tmp_path / "packages")
    staying = await get_or_create_user(session, "staying@example.com")
    leaving = await get_or_create_user(session, "leaving2@example.com")
    staying_job = await create_job(session, staying.id, jd_text="A real job description. " * 10)
    await create_job(session, leaving.id, jd_text="Another real job description. " * 10)
    await session.commit()

    await delete_account(session, storage, leaving.id)
    await session.commit()

    assert await session.get(User, staying.id) is not None
    assert await session.get(Job, staying_job.id) is not None


async def test_sweep_orphan_files_removes_packages_with_no_row(tmp_path: Path, session: AsyncSession) -> None:
    storage = PackageStorage(tmp_path / "packages")
    orphan_id = str(uuid.uuid4())
    storage.write_docx(orphan_id, b"orphaned")
    assert storage.dir_for(orphan_id).exists()

    removed = await sweep_orphan_files(session, storage)

    assert removed >= 1
    assert not storage.dir_for(orphan_id).exists()
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
    or vice versa if this ever ran between the two) and cleans up any pre-existing orphan.
    """
    removed = 0
    if not storage.root.exists():
        return 0
    existing_package_ids = {str(pid) for pid in await session.scalars(select(Package.id))}
    for entry in storage.root.iterdir():
        if entry.name == "resume-document" or not entry.is_dir():
            continue
        if entry.name not in existing_package_ids:
            storage.delete(entry.name)
            removed += 1
    doc_root = storage.root / "resume-document"
    if doc_root.exists():
        existing_user_ids = {str(uid) for uid in await session.scalars(select(User.id))}
        for entry in doc_root.iterdir():
            if entry.is_dir() and entry.name not in existing_user_ids:
                storage.delete_document(uuid.UUID(entry.name))
                removed += 1
    return removed
```

- [ ] **Step 4: Run the tests again**

Run: `pytest tests/unit/test_delete_account.py -v`
Expected: PASS.

- [ ] **Step 5: Wire `--yes` into the CLI, and add `accounts delete`**

```python
# apps/api/src/rhapto/cli/main.py — replace the accounts_prune body's `else` branch (Step 6 above)
    else:
        async def run_deletions() -> int:
            engine = make_engine(settings.database_url)
            try:
                async with make_session_factory(engine)() as session:
                    from rhapto.services.accounts import delete_account, inactive_accounts
                    from rhapto.services.storage import PackageStorage

                    storage = PackageStorage(settings.rhapto_packages_dir)
                    cutoff = datetime.now(UTC) - timedelta(days=settings.rhapto_inactive_days)
                    to_delete = await inactive_accounts(session, cutoff)
                    for u in to_delete:
                        await delete_account(session, storage, u.id)
                    await session.commit()
                    return len(to_delete)
            finally:
                await engine.dispose()

        deleted = asyncio.run(run_deletions())
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

from rhapto.services.accounts import delete_account, inactive_accounts, sweep_orphan_files
from rhapto.services.storage import PackageStorage


async def prune_inactive_accounts(ctx: dict[str, Any]) -> None:
    factory: async_sessionmaker[AsyncSession] = ctx["session_factory"]
    settings = get_settings()
    storage = PackageStorage(settings.rhapto_packages_dir)
    async with factory() as session:
        cutoff = datetime.now(UTC) - timedelta(days=settings.rhapto_inactive_days)
        for user in await inactive_accounts(session, cutoff):
            logger.info("pruning inactive account %s (last seen %s)", user.email, user.last_seen_at)
            await delete_account(session, storage, user.id)
        await session.commit()
        removed = await sweep_orphan_files(session, storage)
        if removed:
            logger.info("orphan sweep removed %d file(s)", removed)
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

- [ ] **Step 7: Write the CLI test**

```python
# apps/api/tests/cli/test_accounts_delete.py
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
```

- [ ] **Step 8: Run the new tests, then the full suite**

Run: `pytest tests/unit/test_delete_account.py tests/cli/test_accounts_delete.py -v` — expect PASS.
Run: `pytest` — expect green.
Run: `ruff check .` and `mypy src` — expect clean.

- [ ] **Step 9: Commit**

```bash
git add apps/api/src/rhapto/services/accounts.py apps/api/src/rhapto/cli/main.py \
  apps/api/src/rhapto/worker/main.py \
  apps/api/tests/unit/test_delete_account.py apps/api/tests/cli/test_accounts_delete.py
git commit -m "$(cat <<'EOF'
delete_account (files before rows), orphan sweep, real prune/delete CLI, daily cron (B1b)

delete_account deletes a user's package files and resume document from disk before deleting the
users row, which cascades through all 17 UserScopedMixin tables plus packages/applications
cascading from jobs -- no other account's rows are ever touched, because nothing is shared in this
schema before Phase C. sweep_orphan_files self-heals a crash between the file and row deletes.
`rhapto accounts prune --yes` and `rhapto accounts delete <email> --yes` both go through
delete_account; a daily 03:00 cron runs the real prune. Arq job cancellation for in-flight tasks
was scoped out: no job-id tracking exists to correlate a Task row to a cancellable arq job, and
building that is its own project -- the existing per-task try/except plus files-before-rows
ordering already guarantees no resurrection and no cross-account harm.

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

**Files:**
- Modify: `scripts/backup-db.sh` (add the mandatory post-restore prune step to the documented
  procedure; add a `--pre-migration` mode that writes into `$BACKUP_DIR` with the standard name)
- Modify: `apps/web/src/app/settings/page.tsx` or a new `apps/web/src/components/settings/DataRetentionNotice.tsx`
  (publish the true-bound promise text)
- Test: `scripts/test-backup-db.sh` (a bash test script, following this repo's convention of
  testing shell scripts by invoking them against a scratch directory — verify this convention exists
  before writing it; if `scripts/` has no existing test pattern, this becomes a `pytest` test that
  shells out to `backup-db.sh` via `subprocess`, placed at `apps/api/tests/unit/test_backup_script.py`)
- Test: `apps/web/src/components/settings/DataRetentionNotice.test.tsx`

**Interfaces:**
- Consumes: nothing from earlier tasks (this task is deploy-ops plus one static piece of UI copy).
- Produces: no new Python/TypeScript interface; the deploy runbook (documented in this task's steps,
  not a file this plan creates, since no runbook file exists in this checkout to extend — the
  implementer should check for `docs/runbook.md` or similar before assuming one must be created new)
  gains two mandatory steps: install the cron, and run `rhapto accounts prune --yes` immediately
  after any restore.

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

```python
# apps/api/tests/unit/test_backup_script.py
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[3].parent / "scripts" / "backup-db.sh"


def _pg_dump_available() -> bool:
    return subprocess.run(["which", "pg_dump"], capture_output=True).returncode == 0


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

- [ ] **Step 5: Publish the true-bound promise on the settings screen**

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
does not reproduce that file's full contents; the requirement it must satisfy is "stated to the user
before they sign up, not buried" (Owner decision Q3), so in `access` mode this component must also
render on whatever unauthenticated landing state a not-yet-invited or newly-redirected visitor sees
— cross-check against `apps/web/src/components/landing/Landing.tsx` (already read in Task 2's
research: `TokenGate` renders `<Landing />` for an unauthenticated visitor at `/`) and add it there
too, so the promise is visible pre-sign-in as the owner decision requires, not only after.

- [ ] **Step 6: Run the new tests, then the full suites**

Run (apps/web): `pnpm test DataRetentionNotice.test.tsx` — expect PASS; then `pnpm test`, `pnpm lint`,
`pnpm typecheck` — expect green.
Run (apps/api): `pytest tests/unit/test_backup_script.py -v`, then the full `pytest`, `ruff check .`,
`mypy src` — expect green (this task's Python change is test-only plus a shell script; nothing in
`apps/api/src` changes, so no mypy/ruff surface is added).

- [ ] **Step 7: Commit**

```bash
git add scripts/backup-db.sh apps/api/tests/unit/test_backup_script.py \
  apps/web/src/components/settings/DataRetentionNotice.tsx \
  apps/web/src/components/settings/DataRetentionNotice.test.tsx \
  apps/web/src/app/settings/page.tsx apps/web/src/components/landing/Landing.tsx
git commit -m "$(cat <<'EOF'
Pre-migration dumps land inside BACKUP_DIR, mandatory post-restore prune, published promise (B2)

backup-db.sh gains a LABEL mode so a pre-migration dump uses the same backup-<db>-<label>-<ts>.dump
naming the nightly RETENTION_DAYS=14 prune already recognises -- a dump outside $BACKUP_DIR is a
standing violation of the deletion promise the moment a second account exists. The restore
procedure documented in the script's header now has a mandatory `rhapto accounts prune --yes` step
immediately after any restore, before the app is pointed at it. The settings screen and the
pre-sign-in landing page both state the promise with its true worst-case bound -- 90 days plus up
to 14 for backups, 104 days worst case -- never a flat 90.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_013CTBNZrgo9dpYW6vRs2TC2
EOF
)"
```

**Note for Delivery (role 7), not a step in this plan:** the cron install (`0 3 * * *
BACKUP_DIR=/var/backups/rhapto scripts/backup-db.sh >> /var/log/rhapto-backup.log 2>&1`, already
documented in the script's header) and the deletion of the ad-hoc `/root/rhapto-pre-0010-*.sql`
dumps are operational actions against the production host, not code changes — they belong to role 7
("Delivery never runs unprompted for anything irreversible"), and this task's job is only to make the
tooling and the promise correct, which it now is.

**Acceptance criteria advanced:** 15 (backup retention does not touch the owner's live data; it
bounds how long deleted data survives), and the Owner-decision-Q3 backup requirement generally
(no single numbered AC maps directly to backups — Q3's four bullets are the requirement, and all four
are now met: cron documented for installation, ad-hoc dumps identified for cleanup by Delivery,
pre-migration dumps reach the pruner, and post-restore prune is mandatory).

---

## Self-review

### Spec coverage

| AC | Task(s) | Status |
|---|---|---|
| 1 | 3, 5 | Met — allowlisted sign-in creates an account; no owner action after the invite |
| 2 | 3 | Met — IdP login only, refused at the edge/API for non-members, no account shell created |
| 3 | 5 | Partially met — the grid is full, not empty; the setup-*flow* itself (Phase D wizard) is out of scope, unbuilt by a separate spec |
| 4 | — | Deferred — pre-existing (`LlmTestOut`/`is_llm_configured` already gate this for a single user); untouched by multi-tenancy, no task needed |
| 5 | — | Deferred to Phase D (location-preference collection during setup); `derive_searches` (Task 5) reads whatever `answers.location_preferred` already holds, unchanged |
| 6 | 1, 2 | Met — identity resolution plus the pre-existing `UserScopedMixin` cascade on every table |
| 7 | 5 | Met — A5 copies only public JD text, never a block/verified fact/extract |
| 8 | 7 | Met — `delete_account` cascades only within the deleted user's own FK graph |
| 9 | — | Deferred to Phase C, explicitly. `check_visibility`'s empty-`context_tags` no-op (architecture §3.5 rule 6) is a real bug, but the risk it closes — a *shared* cached extract — cannot exist until `posting_extracts` exists; in Phase A/B, `extracted_json` stays per-user and A5 explicitly never copies it. Forcing this fix into A/B would be inventing a Phase C task under a different name. Flagged for Phase C's plan. |
| 10 | 4 | Met (mostly pre-existing) — per-task LLM key resolution already isolates cost; Task 4's fan-out prevents one user's poll from starving another's CPU budget |
| 11 | 1, 2 | Met — per-request identity plus per-user `localStorage` namespacing |
| 12 | — | Deferred — pre-existing single-user behaviour, unaffected |
| 13 | — | Deferred — pre-existing (`is_llm_configured`), unaffected |
| 14 | — | Deferred to Phase D / pre-existing empty-state copy, unaffected by tenancy |
| 15 | 1, 3, 5, 8 | Met — additive migration, startup assertion + `set-email` CLI, A5 reads the owner's rows without mutating them, backup retention doesn't touch live data |
| 16 | 7 | Met — deletion never rotates or breaks another account's stored key, because nothing is shared |

AC 4/5/12/13/14 are correctly out of this plan's scope: they are pre-existing single-user behaviours
the functional spec asks multi-tenancy not to break, and none of the eight tasks above touches the
code paths that implement them (`LlmSettingsIn`/`LlmTestOut`, `is_llm_configured`,
`resolve_llm_config`, `ChecklistOut`, the empty-state copy in `apps/web/src/components/jobs`) — so
there is nothing to regress and nothing to add here.

### Placeholder scan

Reviewed every code block above for "TBD", "implement later", "add appropriate handling", or a step
that names behaviour without showing it. Two spots were **not** placeholders but are worth
distinguishing from the failure mode the prompt warns against, since they look similar at a glance:

- Task 1 Step 7's `access` mode branch raises a real, tested `HTTPException(501, ...)` — a defined
  behaviour for an unreachable code path, replaced by real logic in Task 3, not a stub left unfilled.
- Task 8 Step 1 asks the implementer to check for a runbook file before deciding where the
  post-restore step lives, because no such file was found in this checkout during this plan's
  research and inventing one unprompted would risk duplicating an operational doc role 7 already
  maintains elsewhere; this is a real decision point stated as one, not a deferred implementation.

No step describes a test without a body, references a function or type not defined by an earlier
task's Interfaces block, or says "similar to Task N" in place of code.

### Type-consistency check

- `Principal` (Task 1: `mode: AuthMode, subject: str, email: str`) is used identically in Task 3's
  rewrite of `resolve_principal` and nowhere renamed or reshaped.
- `current_user`'s return type (`uuid.UUID`) and its being resolvable via bare `Depends(current_user)`
  is preserved across Tasks 1, 3, 5, 6 despite the function's internal parameter list growing (adding
  `session`, then reusing it) — verified this is safe because every call site in the routers uses
  `Annotated[uuid.UUID, Depends(current_user)]`, which never enumerates `current_user`'s own
  parameters.
- `backfill_public_jobs(session, user_id) -> int` (Task 5) matches its only call site (Task 5 Step 5,
  inside `current_user`) and its test suite (Task 5 Step 1) exactly — no other task calls or renames
  it.
- `mark_seen`/`inactive_accounts` (Task 6) keep the exact signatures Task 7 and Task 8's cron
  (`prune_inactive_accounts`) consume: `mark_seen(session, user_id) -> None`,
  `inactive_accounts(session, cutoff) -> list[User]`.
- `delete_account(session, storage, user_id) -> DeletionReport` (Task 7) is used with the same
  three positional arguments in the CLI's `prune --yes`, `accounts delete`, and the worker's
  `prune_inactive_accounts` — no task calls it with a different argument order or a keyword that
  another task's definition doesn't accept.
- `poll_user(ctx, user_id: str) -> None` (Task 4) is registered in both `TASKS` and
  `WorkerSettings.functions` with the same name string `"poll_user"` used by `poll_all_sources`'s
  `enqueue_job` call — verified these three spellings match exactly.

### Where the architecture left a genuine decision to Role 3 (this plan)

1. **A5's trigger point.** The architecture assumed an onboarding-completion request (Phase D, not
   built) runs the backfill. Since Phase D is out of scope here, Task 5 wires it into Task 3's
   first-sign-in account creation instead, so Phase A ships as a complete unit per the architecture's
   own criterion. Stated explicitly at the top of Task 5.
2. **Idempotency of the backfill's `INSERT ... SELECT`.** The architecture's literal SQL used `ON
   CONFLICT DO NOTHING` with no target — but `jobs` has no unique constraint on `(user_id,
   dedupe_hash)` today (verified against `db/models.py`), and adding one would be a schema change A5
   is explicitly scoped not to need. Task 5 uses a `NOT EXISTS` predicate instead, which is
   semantically identical and needs no migration; noted as a deliberate, verified deviation from the
   architecture's exact SQL, not an invention.
3. **Arq job cancellation on deletion.** The architecture calls for aborting a departing user's queued
   jobs before deleting rows. No job-id tracking exists to make a `Task` row's arq job cancellable
   today, and building that is a real, separate piece of infrastructure. Task 7 states this
   explicitly and relies on the existing per-task try/except plus files-before-rows ordering, which
   satisfies the actual requirement (no resurrection, no cross-account harm) without the missing
   infrastructure.
