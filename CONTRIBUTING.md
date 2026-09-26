# Contributing to Rhapto

Rhapto writes résumés that people send to employers. A bug here does not corrupt a database — it puts
a false claim in front of a hiring manager, under someone's real name, while they are out of work.
That is the standard everything in this repo is held to.

## Before your first pull request

1. Read [`CLA.md`](CLA.md) and accept it in your PR description. One line, once, covers everything you
   ever contribute. Section 2 is the part that matters and the reasoning is stated up front.
2. Sign your commits off: `git commit -s`.
3. Read [`CLAUDE.md`](CLAUDE.md). It is written for AI agents but it is the shortest accurate
   description of the rules, and `docs/requirements-architecture.md` is the source of truth.

## Licence

AGPL-3.0-only. Your contribution ships under it. The CLA additionally lets Augaster Technologies Inc.
offer Rhapto under a separate commercial licence — that is what funds the work, and it is only
possible while one party can license the whole codebase.

## Four rules that are not up for discussion

These are product guarantees, not preferences. A PR that weakens one will be declined however good
the code is.

1. **Nothing submits an application.** No code path, no flag, no "convenience" setting. Submission is
   a human action, always. This is the promise the product is built on.
2. **Provenance.** Every bullet in a generated résumé carries a `source_block_id` that exists in the
   user's block library. The renderer rejects orphan bullets. There is no bypass and no debug mode
   that skips it.
3. **Verified metrics only.** Any number in output traces to a block with `verified: true`. Imported
   blocks are always `verified: false` — the import path never sets it true, and never invents a date.
4. **No personal data, ever.** `profile/` is real user data and is gitignored. Nothing from it —
   names, employers, metrics, dates — may reach code, tests, fixtures, docs, or screenshots. Use
   `profile.example/`, which is fictional. `scripts/check-no-personal-data.py` enforces this; run it
   before you push.

## Known gap, if you are looking for something worth doing

The guardrails verify that **what is present is sourced**. They do not yet verify that **what is
sourced is present**. A model can silently omit an entire employment entry and produce zero
violations — a clean pass on a document with a hole in it. This has been reproduced. Closing it is the
most valuable open work in the project.

## Working on it

Every rule ships with tests, including the adversarial case. A guardrail PR without a test that feeds
it fabricated output and proves the rejection is not finished.

From `apps/api`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
`uv run mypy src`, `uv run lint-imports`. API tests need the compose `db`.

From `apps/web`: `pnpm test`, `pnpm typecheck`, `pnpm lint`.

Generated files are never hand-edited — `packages/schemas` models, `openapi.json`, `schema.d.ts` come
from `scripts/codegen.sh`.

Keep modules small and typed. Python is ruff + mypy strict; TypeScript is strict mode.

## Reporting a bug

Open an issue with what you did, what you expected, and what happened. Screenshots help.

**Do not paste a real résumé, a job description containing your name, or an API key into an issue.**
Redact first. If you have already pasted a key somewhere, rotate it rather than deleting the message.

## Security

For anything that could expose another user's data or stored credentials, do not open a public issue.
Use GitHub's private vulnerability reporting on the repository.
