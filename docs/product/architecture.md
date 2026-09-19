# Architecture

This page is deliberately short — it orients you, then points at the documents that carry the
actual decisions.

## Shape

Rhapto is a monorepo: `apps/api` (FastAPI plus an `arq` worker), `apps/web` (the Next.js portal
this user guide documents), and `packages/schemas` (the Pydantic/TypeScript contract shared
between them, generated from one source of truth). State lives in Postgres, with `pgvector` for
embeddings used in scoring; Redis backs the task queue the worker consumes.

## Where the decisions live

- [`../requirements-architecture.md`](../requirements-architecture.md) is the source of truth for
  functional requirements (FR-1 through FR-6), the data model, and the roadmap.
- [`../superpowers/specs/2026-09-14-portal-design.md`](../superpowers/specs/2026-09-14-portal-design.md)
  is the design spec for this portal UI — navigation, screens, the flow and stage actions, and the
  visual system.

## Engine purity

The tailoring engine that builds a resume package has no web or database imports: it is a pure
function of a job description and a profile, callable from the CLI (`rhapto tailor`) exactly as it
is from the API. Block selection is deterministic — embeddings and rules, not an LLM call — and a
tailoring run makes at most three LLM calls total, with the static context (your blocks and the
guardrail rules) marked for prompt caching.
