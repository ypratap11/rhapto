# JobPilot (working name) — Requirements & Architecture
**Open-source, human-in-the-loop AI job application copilot**
Version 0.1 — Sep 2026

---

## 1. Vision

An open-source tool that watches job boards, classifies each role against the user's career tracks, generates a tailored resume + application answers using an LLM, and queues everything for one-click human review and submission. The human does the last leg (submit); the agent does everything before it.

**Design principle #1 — Engine and identity are separate.** The repo contains the engine only. All personal data (resume blocks, guardrails, tracks, API keys) lives in a user-owned `profile/` directory (gitignored) or local database. This is what makes it safely open-sourceable and useful to anyone, not just the original author.

**Design principle #2 — Human-in-the-loop by default.** The system never submits an application on its own. It discovers, scores, tailors, and drafts. Submission is always a human action.

**Design principle #3 — Verified facts only.** The tailoring engine can only draw from facts in the user's resume blocks. It rephrases and reorders; it never invents metrics, titles, or experience. Guardrail rules are enforced at generation time and checked at review time.

---

## 2. Personas

| Persona | Need |
|---|---|
| **Multi-track senior professional** (primary) | Runs 2–3 parallel career tracks (e.g., ERP PM, TPM, AI PM/Builder); needs per-track resume bases and JD-to-track routing |
| **Career switcher** | One legacy track + one aspirational track; needs the engine to reframe transferable experience |
| **High-volume applicant** | Wants 10–30 quality applications/week without 20 hrs of manual tailoring |

---

## 3. Functional Requirements

### FR-1 Job Discovery
- FR-1.1 Poll public ATS endpoints: **Greenhouse** (`boards-api.greenhouse.io`), **Lever** (`api.lever.co/v0/postings`), **Ashby** (`api.ashbyhq.com/posting-api`), **SmartRecruiters**, **Workable** — all have public JSON job feeds per company.
- FR-1.2 User maintains a **watchlist of companies** per board + **keyword track filters** (title/description regex or semantic match).
- FR-1.3 Optional RSS/JSON ingestion from aggregators (Hacker News "Who's Hiring", WorkAtAStartup, RemoteOK API).
- FR-1.4 Manual JD paste/URL import — a JD pasted into the UI enters the same pipeline (this is also the v0.1 MVP path).
- FR-1.5 Deduplication by company + normalized title + location; re-posts flagged, not re-queued.
- FR-1.6 **No scraping of LinkedIn/Indeed** in core. Document why (ToS, account bans). Extension point exists but ships empty.

### FR-2 Track Classification & Fit Scoring
- FR-2.1 User defines N **tracks**, each with: name, keyword sets, semantic description, mapped resume base, minimum fit threshold.
- FR-2.2 Each incoming JD is scored per track (embedding similarity + keyword hits + LLM judgment call) → best track + fit score 0–100.
- FR-2.3 JDs below threshold on all tracks go to a "low fit" bucket, not deleted (user can rescue).
- FR-2.4 Extracted from every JD: must-have skills, nice-to-haves, location/onsite policy, seniority, comp if listed, knockout questions likely to appear.

### FR-3 Resume Tailoring Engine
- FR-3.1 Input: JD + matched track's resume base + resume-block library + guardrails config. Output: tailored resume (structured JSON → rendered to DOCX and PDF) + 120–180-word cover note + change log ("what I emphasized and why").
- FR-3.2 **Block-level provenance**: every bullet in the output traces to a source block ID. The renderer refuses bullets with no provenance.
- FR-3.3 Guardrail engine (see §6) runs post-generation as a validation pass; violations block the draft and surface in UI.
- FR-3.4 Regeneration with user feedback ("lean harder on supply chain", "drop the AI section") without losing the original.
- FR-3.5 ATS-safe formatting: single column, standard section headers, no tables/graphics in the DOCX output.

### FR-4 Application Package & Knockout Answers
- FR-4.1 Draft answers to standard questions from the user's `answers.yaml`: work authorization, relocation, onsite preference, salary range, notice period, "why this company" (LLM-drafted from JD + company blurb).
- FR-4.2 Per-application package = resume + cover note + answers + JD snapshot + fit rationale, all versioned.

### FR-5 Review Queue & Tracking (the UI core)
- FR-5.1 Queue view: cards sorted by fit score with company, role, track badge, location, deadline.
- FR-5.2 Detail view: side-by-side JD ↔ tailored resume with highlighted matches; inline edit of any bullet; guardrail status panel.
- FR-5.3 One-click: download package / open application URL / mark applied.
- FR-5.4 Pipeline tracker (kanban): Discovered → Queued → Applied → Screen → Interview → Offer/Closed, with notes and dates per application.
- FR-5.5 Analytics: applications per track per week, response rate per track, which resume base converts best.

### FR-6 Profile Management
- FR-6.1 CRUD UI for resume blocks, tracks, guardrails, answers — no editing raw YAML required (but YAML import/export supported).
- FR-6.2 **Resume import**: upload an existing resume (PDF/DOCX) → LLM decomposes it into candidate blocks → user approves each block into the library (first-run onboarding).

---

## 4. Non-Functional Requirements

- **NFR-1 Privacy/local-first**: runs fully on the user's machine via Docker Compose; no telemetry; personal data never leaves the machine except LLM API calls (documented clearly). Optional "redact employer names in API calls" mode.
- **NFR-2 BYO LLM key**: Anthropic API as reference implementation behind a provider interface (`LLMProvider`) so OpenAI/local models (Ollama) can be contributed.
- **NFR-3 Scalability**: poller and tailoring run as async workers off a queue; a single user needs one worker, but architecture supports multi-user hosted deployment later (row-level tenancy from day one: every table keyed by `user_id`).
- **NFR-4 Cost control**: tailoring only on user request or above fit threshold; token budget per day configurable; prompt caching for the static resume-block context.
- **NFR-5 Testability**: golden-set tests — 20 sample JDs with expected track classification; guardrail unit tests (inject a fabricated metric → must be caught).
- **NFR-6 License**: AGPL-3.0-only (copyleft, network clause). Chosen so that anyone who offers
  Rhapto to others over a network must publish their modifications under the same terms — the
  truthfulness guarantee is the product, and a closed fork could quietly remove it. Using or
  self-hosting it for yourself carries no obligation.

---

## 5. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     Web UI (Next.js)                    │
│   Queue · JD↔Resume diff · Kanban · Profile · Analytics │
└───────────────▲─────────────────────────────────────────┘
                │ REST/JSON (OpenAPI)
┌───────────────┴─────────────────────────────────────────┐
│                  API (FastAPI, Python)                  │
│  auth (single-user token / multi-user later) · CRUD ·   │
│  pipeline orchestration · SSE for job status            │
└───────▲──────────────────▲──────────────────────────────┘
        │                  │
┌───────┴────────┐  ┌──────┴───────────────────────────────┐
│  Postgres      │  │  Worker (arq/Celery on Redis)        │
│  + pgvector    │  │  · Poller (cron: ATS feeds)          │
│  jobs, blocks, │  │  · Classifier (embed + score)        │
│  packages,     │  │  · Tailor (LLM pipeline + guardrail  │
│  applications  │  │    validator)                        │
└────────────────┘  │  · Renderer (JSON→DOCX/PDF)          │
                    └──────▲───────────────────────────────┘
                           │ LLMProvider interface
                    ┌──────┴────────┐
                    │ Anthropic API │  (pluggable: OpenAI, Ollama)
                    └───────────────┘
```

**Stack rationale**
- **Backend: Python/FastAPI** — the LLM + document ecosystem (python-docx, WeasyPrint/reportlab, embeddings) is strongest in Python; FastAPI gives OpenAPI schema for free, which auto-generates the TS client for the UI.
- **DB: Postgres + pgvector** — one database for relational data and JD/track embeddings; no separate vector store to operate.
- **Queue: Redis + arq** (lightweight) — polling and tailoring are background jobs; arq keeps the dependency surface small vs Celery.
- **Frontend: Next.js + TypeScript + Tailwind + shadcn/ui** — the de-facto OSS stack; contributors know it; shadcn gives a polished UI fast.
- **Packaging: Docker Compose** (`db`, `redis`, `api`, `worker`, `web`) — `git clone && docker compose up` is the entire install story.
- **Monorepo**: `/apps/web`, `/apps/api`, `/packages/schemas` (shared JSON Schemas → generated TS + Pydantic types).

---

## 6. Data Model (core entities)

```
users(id, email, settings_json)
tracks(id, user_id, name, description, keywords[], resume_base_id, min_fit)
resume_blocks(id, user_id, type, org, role, period, content_json,
              verified bool, tags[], embedding vector)
resume_bases(id, user_id, name, block_ids[], section_order, style)
jobs(id, user_id, source, company, title, location, url, jd_text,
     jd_embedding, extracted_json, dedupe_hash, discovered_at)
scores(job_id, track_id, fit_score, rationale_json)
packages(id, job_id, track_id, resume_json, cover_note, answers_json,
         guardrail_report_json, version, created_at)
applications(id, job_id, package_id, status, applied_at, notes,
             status_history_json)
guardrails(id, user_id, rule_type, config_json, active)
```

### Resume block schema (the heart of it)
```yaml
- id: acme-migration
  type: achievement            # achievement | role | project | skill | credential
  org: Acme Analytics
  role: Senior Data Program Manager
  period: "2019-2025"
  verified: true               # only verified:true blocks may carry metrics
  metric: "Migrated 12 pipelines with zero downtime, cutting warehouse cost 18%"
  content: "Owned the Snowflake migration program end to end."
  tags: [migration, cost]
  visibility:                  # guardrail hook
    exclude_when: [agency]   # e.g. hide client work when applying to that client's competitor
```

### Guardrail rule types (shipped defaults, user-configurable)
1. `no-unverified-metrics` — any number in output must trace to a `verified: true` block.
2. `attribution` — named projects must carry their configured attribution string (e.g., "built at <studio>", never "deployed at client").
3. `visibility-context` — blocks with `exclude_when` matching the JD's context tag are hard-excluded.
4. `no-invented-entities` — employers, titles, dates in output must exist in the block library (string + fuzzy check).
5. `date-consistency` — no overlapping/impossible date ranges.

---

## 7. Tailoring pipeline (LLM design)

1. **Extract** (1 call): JD → structured requirements (must/nice/location/seniority/keywords/likely knockouts).
2. **Select** (deterministic + embeddings): rank resume blocks against extracted requirements; take top-K per section within the track's base.
3. **Compose** (1 call, cached system context): selected blocks + JD extract + style rules → resume JSON (sections, bullets each with `source_block_id`), cover note, change log.
4. **Validate** (deterministic): guardrail engine checks provenance, metrics, completeness (every selected role, project and credential appears), attribution, dates. Fail → auto-repair call (1 retry) → else surface violations in UI.
5. **Render** (deterministic): resume JSON → DOCX (python-docx, ATS-safe template) + PDF.

~2–3 LLM calls per application; static context (blocks + rules) is prompt-cached.

---

## 8. UI screens (v1)

1. **Onboarding** — upload resume → approve extracted blocks → define tracks → set guardrails/answers.
2. **Queue** — scored job cards, filter by track/score/location; "Tailor" button per card.
3. **Package review** — split view: JD (requirements highlighted) ↔ resume (matched bullets highlighted); guardrail panel; inline edit; regenerate-with-feedback; Download / Open posting / Mark applied.
4. **Pipeline** — kanban of applications with status history and notes.
5. **Profile** — blocks, bases, tracks, guardrails, answers, watchlist, LLM settings.
6. **Analytics** — response rate per track/base, volume per week.

---

## 9. Roadmap

| Phase | Scope | Outcome |
|---|---|---|
| **0.1 MVP** (weekend-buildable) | Manual JD paste → extract → tailor → guardrails → DOCX/PDF download. CLI or minimal single-page UI. Profile as YAML files. | Immediately useful daily; validates the tailoring quality |
| **0.2** | Postgres + full profile UI + review queue + application tracker | Replaces spreadsheets |
| **0.3** | ATS pollers (Greenhouse/Lever/Ashby) + track auto-classification + dedupe | "Wake up to a scored queue" |
| **0.4** | Analytics, resume import/decomposition onboarding, prompt caching, provider abstraction (OpenAI/Ollama) | OSS-launch quality |
| **1.0** | Docs site, golden-test suite, contributor guide, demo profile, Product Hunt / HN launch | Community |
| **Post-1.0 (explicitly out of core)** | Browser-assist extension that pre-fills ATS forms from the package (user watches and clicks submit). Never unattended submission. | The "last leg" stays human |

---

## 10. Risks & mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates experience | Block provenance + guardrail validator; renderer rejects orphan bullets |
| ATS boards change/rate-limit feeds | Per-source adapter pattern; polite polling (hours, not minutes); caching |
| Personal data leaks into OSS repo | `profile/` gitignored; demo profile is fictional; secret-scan CI hook |
| Scope creep toward auto-submit | Stated non-goal in README; browser-assist only, post-1.0 |
| LLM cost | Threshold-gated tailoring, prompt caching, per-day token budget |

---

## 11. Repo layout

```
jobpilot/
├── apps/
│   ├── api/            # FastAPI + workers
│   │   ├── pipeline/   # extract, select, compose, validate, render
│   │   ├── sources/    # greenhouse.py, lever.py, ashby.py, ...
│   │   └── guardrails/
│   └── web/            # Next.js UI
├── packages/schemas/   # JSON Schemas → Pydantic + TS types
├── profile.example/    # fictional demo: blocks.yaml, tracks.yaml,
│                       # guardrails.yaml, answers.yaml, watchlist.yaml
├── docker-compose.yml
├── docs/
└── LICENSE (AGPL-3.0-only)
```
