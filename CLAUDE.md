# CLAUDE.md — Rhapto

Rhapto (Greek ῥάπτω, "I stitch" — the root of rhapsody) is an open-source, human-in-the-loop AI job application
copilot. It discovers jobs, classifies them against the user's career tracks,
generates a tailored resume + application package with an LLM, and queues
everything for one-click human review. **It never submits applications itself.**

Read `docs/requirements-architecture.md` in full before writing code. It is the
source of truth for requirements (FR-1..6), architecture, data model, and roadmap.

## Non-negotiable product rules
1. **Human-in-the-loop.** No code path may submit an application. Submission is
   always a human action. Do not add auto-submit "for convenience."
2. **Provenance.** Every bullet in a generated resume must carry a
   `source_block_id` that exists in the user's block library. The renderer must
   reject orphan bullets.
3. **Verified metrics only.** Any number/metric in output must trace to a block
   with `verified: true`. This is enforced by the guardrail validator, with tests.
4. **Engine/identity separation.** Nothing personal in the repo. `profile/` is
   gitignored (real user data); `profile.example/` is fictional demo data. Never
   copy content from `profile/` into code, tests, fixtures, or docs.

## Build order (do 0.1 completely before touching 0.2)
- **0.1 — CLI pipeline (build this first):**
  `rhapto tailor --jd path/to/jd.txt --profile ./profile` →
  extract → select → compose → validate → render → `out/<company>-<role>/`
  containing `resume.docx`, `resume.pdf`, `cover-note.md`, `package.json`
  (structured package incl. guardrail report + change log).
  Python 3.12, `uv` for deps, Pydantic models generated from
  `packages/schemas`, Anthropic API behind an `LLMProvider` interface,
  `python-docx` for DOCX, ATS-safe single-column template.
- **0.2 —** Postgres + FastAPI + review-queue UI (Next.js + shadcn/ui).
- **0.3 —** ATS pollers (Greenhouse/Lever/Ashby) + track classification.
See the roadmap table in the requirements doc for full scope per phase.

## Conventions
- Monorepo: `apps/api`, `apps/web`, `packages/schemas`; Docker Compose at root.
- Python: ruff + mypy strict; TypeScript: strict mode. Small modules, typed
  boundaries, no clever metaprogramming.
- Every guardrail rule ships with unit tests, including adversarial cases
  (e.g., LLM output containing an invented metric must be caught).
- Golden tests: `tests/golden/` holds sample JDs + expected track
  classification and guardrail outcomes. Use `profile.example/` only.
- LLM calls: max 3 per tailoring run; static context (blocks + rules) goes in
  the prompt-cached system block; deterministic steps stay deterministic (block
  selection is embeddings + rules, not an LLM call).
- Secrets via `.env` (gitignored); `ANTHROPIC_API_KEY` required, model
  configurable, default to the latest Sonnet.
- License: AGPL-3.0-only. README must state the human-in-the-loop non-goal.

## Working with the profile data
- `profile/` (real, gitignored) and `profile.example/` (fictional) share the
  same schema: `blocks.yaml`, `tracks.yaml`, `guardrails.yaml`, `answers.yaml`,
  `watchlist.yaml`. Validate both against `packages/schemas` on load.
- When testing locally you may READ `profile/` to run the pipeline, but all
  committed artifacts (fixtures, snapshots, docs, examples) must come from
  `profile.example/`.
- Add a CI secret-scan step and a check that no string from
  `profile/blocks.yaml` orgs appears in committed files.

## Working agreement (set by the owner, 2026-09-24)

**Nothing ships unreviewed.** Every unit of work — a design, a plan, a code change — is checked by an
independent agent before it reaches the owner, not after. A plan gets a plan review before execution
begins; code gets a task review against its diff; anything architectural gets an architect's explicit
APPROVED / APPROVED WITH CONDITIONS / NOT APPROVED before the owner is asked to look at it. Self-review
is not review. This rule exists because a plan the owner approved turned out to carry 8 Critical
defects, and an architecture audit then reversed its central design decision.

**Verify, never assert.** Claims about the schema, a signature or a constraint are checked against the
code or the database in the same breath they are made. The failure that produced this rule was writing
"job_scores already keys on (user_id, job_id, track_id)" minutes after printing the constraint that
said `UNIQUE (job_id, track_id)`.

**Guardrails are unconditional, not preferences.** Provenance and `no-unverified-metrics` are both
non-negotiable; neither is a user-toggleable rule. A package whose guardrail report fails must not
persist a DOCX, in any mode. The truthfulness guarantee is the product — an off-switch makes it a
claim the code does not keep.

**Spend tokens and time like they are the owner's, because they are.**
- Agent reports go to files under `.superpowers/sdd/<plan>/`; only status, findings and decisions
  come back into the conversation.
- Hand reviewers a generated diff file, never a pasted diff.
- Batch same-shape work into one dispatch; never one agent per one-line change.
- Use the cheapest model that can do the job, and always name it explicitly.
- Do not re-run an 11-minute suite per commit when the change is scoped; run it once before the work
  is handed over, and say which suites did and did not run.
- No progress narration. The ledger is the record.
