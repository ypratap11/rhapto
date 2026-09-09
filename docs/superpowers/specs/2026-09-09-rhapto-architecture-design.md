# Rhapto 0.2 Architecture Design

**Date:** 2026-09-09
**Status:** Approved
**Scope:** Roadmap phases 0.1 and 0.2 of `docs/requirements-architecture.md`
(manual JD intake, tailoring engine, guardrails, DOCX/PDF rendering, Postgres,
API, worker, review queue UI, application tracker, profile UI).

Out of scope for this spec (later phases): ATS pollers and dedupe (0.3),
automatic track classification and fit scoring (0.3), analytics (0.4), resume
import/decomposition onboarding (0.4), non-Anthropic LLM providers (0.4).

## 1. Decisions

| Decision | Choice | Why |
|---|---|---|
| First build scope | Full 0.2 | User wants a real frontend/backend application from the start |
| Backend layout | Modular monolith: one Python package with `engine`, `profile`, `db`, `api`, `worker`, `cli` layers | Clean boundaries without multi-package overhead |
| Frontend | Separate Next.js app under `apps/web`, talks to the API only over REST | True frontend/backend separation, standard OSS stack |
| Embeddings | Local `fastembed` (BAAI/bge-small-en-v1.5, 384 dims) behind `EmbeddingProvider` | No extra API key, local-first |
| LLM | Anthropic behind `LLMProvider`, default latest Sonnet, prompt caching on | Per CLAUDE.md |
| PDF | Convert the rendered DOCX with headless LibreOffice in the worker image | DOCX and PDF cannot drift; ATS-safe |
| Profile source of truth | Postgres in 0.2; YAML import/export via CLI and API | FR-6.1 |
| Dev runtime | Docker Compose for db, redis, api, worker, web | Matches the install story; avoids Windows-specific setup |
| Auth | Single bearer token from `.env`; single user created at startup; every table keyed by `user_id` | NFR-3 row-level tenancy from day one |
| Queue | arq on Redis | Lightweight; needed for 0.3 polling anyway |

## 2. Repository layout

```
rhapto/
├── apps/
│   ├── api/                          # Python 3.12 backend, one uv project
│   │   ├── pyproject.toml
│   │   ├── Dockerfile                # targets: api, worker
│   │   ├── alembic/                  # migrations
│   │   ├── src/rhapto/
│   │   │   ├── config.py             # pydantic-settings, reads .env
│   │   │   ├── models/               # GENERATED Pydantic models from packages/schemas
│   │   │   ├── engine/               # pure pipeline, no db/api imports
│   │   │   │   ├── providers/        # llm.py (protocol, Anthropic, Fake), embeddings.py (protocol, fastembed, Fake)
│   │   │   │   ├── extract.py
│   │   │   │   ├── select.py
│   │   │   │   ├── compose.py
│   │   │   │   ├── repair.py
│   │   │   │   ├── guardrails/       # registry.py + one module per rule
│   │   │   │   ├── render/           # docx.py (python-docx), pdf.py (LibreOffice)
│   │   │   │   ├── prompts/          # system/user prompt templates
│   │   │   │   └── pipeline.py       # tailor(): orchestration + call budget
│   │   │   ├── profile/              # YAML loader, validation, export
│   │   │   ├── db/                   # SQLAlchemy 2 async models, session, repositories
│   │   │   ├── api/                  # FastAPI app factory, routers, auth, sse
│   │   │   ├── worker/               # arq WorkerSettings + tasks
│   │   │   └── cli/                  # Typer app
│   │   └── tests/
│   │       ├── unit/                 # engine with fake providers
│   │       ├── guardrails/           # one file per rule, adversarial cases
│   │       ├── golden/               # fictional JDs + expected outcomes
│   │       └── api/                  # httpx against a real Postgres
│   └── web/                          # Next.js 15 app router, TS strict
│       ├── src/app/                  # routes
│       ├── src/components/           # shadcn/ui + feature components
│       ├── src/lib/api/              # GENERATED OpenAPI client (openapi-typescript + openapi-fetch)
│       └── src/lib/schemas/          # GENERATED TS types from packages/schemas
├── packages/schemas/                 # JSON Schema files (source of truth) + codegen script
├── profile.example/                  # fictional demo profile (committed)
├── profile/                          # real profile (gitignored)
├── docs/
├── scripts/                          # check-no-personal-data.py, codegen.sh
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
├── LICENSE                           # AGPL-3.0-only
└── README.md
```

Layering rule, enforced by an import-linter contract in CI:
`engine` imports `models` only. `profile` imports `models`. `db` imports `models`.
`api`, `worker`, and `cli` may import anything.

## 3. Shared schemas (`packages/schemas`)

JSON Schema (draft 2020-12) files, one per document type:

| File | Describes |
|---|---|
| `profile/blocks.schema.json` | `blocks.yaml`: id, type (achievement, role, project, skill, credential), org, role, period, verified, metric, content, tags, attribution, concurrent, visibility.exclude_when |
| `profile/tracks.schema.json` | `tracks.yaml`: id, name, description, keywords, resume_base, min_fit |
| `profile/bases.schema.json` | `bases.yaml`: id, name, block_ids, section_order, style (new file; optional, a default base of all blocks is synthesized when absent) |
| `profile/guardrails.schema.json` | `guardrails.yaml`: rule, active, config |
| `profile/answers.schema.json` | `answers.yaml`: string map of standard answers |
| `profile/watchlist.schema.json` | `watchlist.yaml`: company, source, board |
| `jd_extract.schema.json` | Output of Extract: company, title, must_have, nice_to_have, location_policy, seniority, keywords, likely_knockouts, context_tags |
| `resume_document.schema.json` | Tailored resume: header, summary, sections[] of entries[] of bullets[]; every bullet has `text` and `source_block_id` |
| `guardrail_report.schema.json` | rules_run[], violations[] (rule, severity, message, bullet_path, block_id), passed |
| `package.schema.json` | Application package: job snapshot, track_id, jd_extract, resume_document, cover_note, change_log, answers, guardrail_report, version, status (draft, blocked), llm_calls, created_at |

Codegen (`scripts/codegen.sh`):
- `datamodel-codegen` produces `apps/api/src/rhapto/models/*.py` (Pydantic v2).
- `json-schema-to-typescript` produces `apps/web/src/lib/schemas/*.ts`.
- Generated files are committed. CI regenerates and fails on diff.

## 4. Engine

### 4.1 Providers

```python
class LLMProvider(Protocol):
    async def complete_structured(
        self, *, system: list[SystemBlock], messages: list[Message],
        output_schema: type[BaseModel], max_tokens: int,
    ) -> StructuredResult  # .value: BaseModel, .usage: TokenUsage

class EmbeddingProvider(Protocol):
    dimensions: int
    async def embed(self, texts: list[str]) -> list[list[float]]
```

- `AnthropicProvider`: uses tool-use forced to a single tool whose input schema is
  `output_schema`, so structured output is guaranteed. Static system blocks are
  marked `cache_control: ephemeral`. Model from `RHAPTO_LLM_MODEL`, default the
  latest Sonnet id at implementation time.
- `FastEmbedProvider`: `BAAI/bge-small-en-v1.5`, model cached under a volume.
- `FakeLLMProvider` and `FakeEmbeddingProvider` for tests: scripted responses and
  deterministic hash-based vectors. Every engine test uses fakes.

### 4.2 Pipeline

`tailor(request: TailorRequest, profile: Profile, llm, embedder) -> TailorResult`

`TailorRequest`: jd_text, track_id, feedback (optional), previous_package (optional).
`Profile`: in-memory blocks, tracks, bases, guardrails, answers (loaded from YAML
in the CLI or from Postgres in the worker; the engine does not care).

Steps, each an async function with typed input and output:

1. **extract** (LLM call 1): `jd_text -> JDExtract`.
2. **select** (deterministic): apply `visibility.exclude_when` against
   `JDExtract.context_tags` (hard exclude); restrict to the track's base block
   ids; score each block as `0.6 * cosine(block_embedding, requirements_embedding)
   + 0.3 * keyword_hit_ratio + 0.1 * tag_overlap`; take top-K per block type
   (K configurable per type, defaults role 4, achievement 8, project 3, skill 1,
   credential 3). Returns `Selection` with per-block scores for the change log.
3. **compose** (LLM call 2): system block = selected blocks as JSON + style rules
   + guardrail summary (cached); user message = JD extract + answers + feedback
   + previous resume when regenerating. Output schema = `ComposeOutput`
   (resume_document, cover_note 120-180 words, change_log, drafted_answers).
4. **validate** (deterministic): runs the guardrail registry; returns
   `GuardrailReport`.
5. **repair** (LLM call 3, only when violations exist): same cached system block,
   user message = previous output + violations; re-validate. If still failing,
   result status is `blocked` and the report is returned.
6. **render** (deterministic): `ResumeDocument -> docx bytes`; PDF conversion is
   a separate function so the CLI can skip it when LibreOffice is absent
   (`--no-pdf`).

The orchestrator holds a call counter and raises `LLMBudgetExceeded` if any path
would make a fourth call.

### 4.3 Guardrail rules

Each rule is `def check(ctx: GuardrailContext) -> list[Violation]` registered by
name. `GuardrailContext` holds the resume document, the block library, the
selection, the JD extract, and the rule config.

| Rule | Configurable | Logic |
|---|---|---|
| `provenance` | No, always on | Every bullet's `source_block_id` exists in the library and was in the selection |
| `no-unverified-metrics` | Yes | Regex for numbers, percentages, currency, multipliers, and spelled-out quantities in bullet text. Each numeric token must appear in the source block's `metric` or `content`, and the block must be `verified: true`. Years matching the block's `period` are exempt |
| `no-invented-entities` | Yes | Every org, role title, and period in entry headers must exactly or fuzzily (rapidfuzz ratio >= 90) match a library block |
| `date-consistency` | Yes | Periods parse as `YYYY`, `YYYY-YYYY`, or `YYYY-Present`; end >= start; no overlapping `role` entries unless both blocks carry `concurrent: true` |
| `attribution` | Yes | Blocks with an `attribution` string must have that string present in any bullet derived from them |
| `visibility-context` | Yes | No bullet derives from a block whose `exclude_when` intersects `context_tags` |

Every rule ships with a test file containing at least one passing case, one
failing case, and one adversarial case (for example an LLM output that rewrites
"18%" as "nearly a fifth" is still caught by the spelled-number pattern).

### 4.4 Renderer

Single column, standard headers (Summary, Experience, Projects, Skills,
Credentials), no tables or images, Calibri 11, ATS-safe. Raises
`OrphanBulletError` if any bullet lacks a `source_block_id` present in the
library. PDF via `soffice --headless --convert-to pdf`.

## 5. Profile loading and CLI

`rhapto.profile.load(path) -> Profile` reads the five YAML files (plus optional
`bases.yaml`), validates each against the generated models, and synthesizes a
default base per track when `bases.yaml` is absent. `rhapto.profile.dump(profile,
path)` writes them back.

CLI (Typer, entrypoint `rhapto`):

```
rhapto tailor --jd path/to/jd.txt --profile ./profile [--track id] [--out out/] [--no-pdf] [--feedback "..."]
rhapto profile validate ./profile
rhapto profile import ./profile          # YAML to Postgres (stage 2)
rhapto profile export ./profile          # Postgres to YAML (stage 2)
rhapto db upgrade                        # alembic (stage 2)
```

`tailor` writes `out/<company>-<role>/resume.docx`, `resume.pdf`,
`cover-note.md`, `package.json`.

## 6. Database

Postgres 16 with pgvector. SQLAlchemy 2 async with asyncpg. Alembic migrations.
All tables have `user_id`, `created_at`, and `updated_at`.

```
users(id, email, settings_json)
resume_blocks(id, user_id, block_id (profile-level id, unique per user), type, org, role,
              period, verified, metric, content, tags[], attribution, concurrent,
              exclude_when[], embedding vector(384))
resume_bases(id, user_id, base_id, name, block_ids[], section_order[], style_json)
tracks(id, user_id, track_id, name, description, keywords[], resume_base_id, min_fit)
guardrails(id, user_id, rule, active, config_json)
answers(id, user_id, answers_json)
watchlist(id, user_id, company, source, board)
jobs(id, user_id, source ('manual'), company, title, location, url, jd_text,
     jd_embedding vector(384), extracted_json, dedupe_hash, discovered_at)
packages(id, user_id, job_id, track_id, version, status, resume_json, cover_note,
         change_log, answers_json, guardrail_report_json, llm_calls, docx_path, pdf_path,
         parent_package_id)
applications(id, user_id, job_id, package_id, status, applied_at, notes,
             status_history_json)
tasks(id, user_id, type, status (queued, running, succeeded, failed), progress_json,
      error, result_ref, created_at, finished_at)
```

`scores` from the requirements doc is deferred to 0.3 with classification.
Rendered files are stored under a shared volume `/data/packages/<package_id>/`.

## 7. API

FastAPI, prefix `/api/v1`, OpenAPI served at `/api/v1/openapi.json`.
Auth: `Authorization: Bearer <RHAPTO_API_TOKEN>`; a dependency resolves the
single user. CORS allows the web origin from config.

| Area | Endpoints |
|---|---|
| Profile | CRUD for `/profile/blocks`, `/profile/bases`, `/profile/tracks`, `/profile/guardrails`, `/profile/watchlist`; `GET/PUT /profile/answers`; `POST /profile/import` (multipart of YAML files); `GET /profile/export` (zip) |
| Jobs | `POST /jobs` (body: jd_text or url, optional company/title/location; URL is fetched and reduced to text with trafilatura); `GET /jobs` with filters (track, status, search); `GET /jobs/{id}`; `DELETE /jobs/{id}` |
| Tailoring | `POST /jobs/{id}/tailor` (track_id, feedback?, parent_package_id?) returns `{task_id}`; `GET /tasks/{id}`; `GET /tasks/{id}/events` (SSE: progress, done, error) |
| Packages | `GET /jobs/{id}/packages`; `GET /packages/{id}`; `PATCH /packages/{id}` (edited resume_document) re-validates, re-renders, and creates a new version; `GET /packages/{id}/download` (zip); `GET /packages/{id}/files/{name}` for resume.docx or resume.pdf |
| Applications | `POST /applications` (job_id, package_id); `GET /applications` (grouped by status for the kanban); `PATCH /applications/{id}` (status, notes) appends to status history; `DELETE /applications/{id}` |
| Meta | `GET /health`, `GET /me` |

Errors follow RFC 7807 problem details. Validation errors from Pydantic map to
422 with field paths.

Editing a bullet through `PATCH /packages/{id}` never bypasses guardrails: the
edited document is re-validated and the new version carries its own report and
may be `blocked`.

## 8. Worker

arq on Redis. Tasks:

- `tailor_job(task_id, job_id, track_id, feedback, parent_package_id)`: loads the
  profile from Postgres into the engine's `Profile`, runs `tailor`, writes files
  to the packages volume, inserts the package row, updates the task row, and
  publishes progress events to Redis channel `task:{task_id}` at each pipeline
  step.
- `embed_blocks(user_id, block_ids)`: computes and stores block embeddings;
  triggered on block create, update, and import.

The API SSE endpoint subscribes to the task's channel and replays the current
task state first so late subscribers see the latest step.

## 9. Web app

Next.js 15 (app router), TypeScript strict, Tailwind, shadcn/ui, TanStack Query,
`openapi-fetch` client generated from the API's OpenAPI document, `dnd-kit` for
the kanban. On first visit the app asks for the API token and stores it in
`localStorage`; a sign-out clears it.

Routes:

| Route | Screen |
|---|---|
| `/` | Queue: job cards (company, role, location, discovered date, latest package status), filter by track and text, "Add job" dialog (paste JD or URL), "Tailor" button per card with track picker, live progress via SSE |
| `/jobs/[id]/packages/[packageId]` | Package review: split view JD (requirements highlighted from extract) and resume (bullets clickable to show source block), guardrail panel with violations, inline bullet edit that creates a new version, regenerate with feedback, version switcher, download zip, open posting, mark applied |
| `/pipeline` | Kanban: Discovered, Queued, Applied, Screen, Interview, Offer, Closed; drag to change status; notes and status history in a side sheet |
| `/profile` | Tabs: Blocks, Bases, Tracks, Guardrails, Answers, Watchlist; table plus edit sheet per entity; import and export buttons |
| `/settings` | API token, API URL |

## 10. Packaging and configuration

`docker-compose.yml` services: `db` (pgvector/pgvector:pg16, volume), `redis`,
`api` (uvicorn, port 8000), `worker` (arq), `web` (next start, port 3000).
Volumes: `pgdata`, `packages`, `models` (fastembed cache).

`apps/api/Dockerfile` targets: `api` (python plus uv deps) and `worker` (adds
LibreOffice and pre-downloads the embedding model).

`.env.example` keys: `ANTHROPIC_API_KEY`, `RHAPTO_LLM_MODEL`,
`RHAPTO_API_TOKEN`, `RHAPTO_USER_EMAIL`, `DATABASE_URL`, `REDIS_URL`,
`RHAPTO_PACKAGES_DIR`, `RHAPTO_WEB_ORIGIN`, `NEXT_PUBLIC_API_URL`.

## 11. Testing and CI

- Engine unit tests with fake providers cover every pipeline step and the call
  budget.
- Guardrail tests: one file per rule with passing, failing, and adversarial cases.
- Golden tests: `tests/golden/<case>/jd.txt` plus `expected.json` (guardrail
  outcome and selected block ids) using `profile.example` and scripted fake LLM
  responses stored alongside.
- API tests: httpx `AsyncClient` against a Postgres service, arq tasks run
  inline with fakes.
- Web: `tsc --noEmit`, eslint, `next build`.
- CI (`ci.yml`): ruff, mypy strict, import-linter, pytest, codegen freshness,
  pnpm typecheck, lint, and build, gitleaks, `scripts/check-no-personal-data.py`
  (fails if any `org` from `profile/blocks.yaml` appears in tracked files;
  no-op when `profile/` is absent). The same script runs as a pre-commit hook.

## 12. Implementation stages

Each stage gets its own implementation plan.

1. **Engine and CLI**: repo scaffold, schemas and codegen, providers, pipeline,
   guardrails, renderer, profile loader, `rhapto tailor`, unit, guardrail, and
   golden tests, Dockerfile targets. Outcome: usable from the CLI against
   `profile/`.
2. **Backend**: database models and migrations, profile import and export, API
   routers, worker, SSE, Docker Compose, API tests.
3. **Frontend**: Next.js app, generated client, the five routes.
4. **Release polish**: README, `.env.example`, CONTRIBUTING, CI workflow,
   pre-commit, demo walkthrough.
