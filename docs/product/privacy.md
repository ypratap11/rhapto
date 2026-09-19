# Privacy

## What is stored

Rhapto stores, in your own Postgres database: every job it has discovered along with its job
description text, every generated resume package and its files, your applications and their
history, your profile (contact answers, blocks, tracks, guardrails, resume bases, watchlist), and
your saved searches. All of it lives on the machine (or server) running your own Docker Compose
stack — Rhapto has no hosted service of its own.

## What leaves the machine

Two kinds of outbound request leave your machine, and nothing else does: requests to whichever job
sources you've enabled (see [`sources.md`](sources.md)), and the prompts sent to whichever LLM
provider you've configured, when you tailor a resume. Rhapto sends no telemetry or analytics to
anyone.

## Keys

Provider credentials (your LLM API key) and source credentials (Adzuna, Jooble, JSearch) are
encrypted at rest with a Fernet secret (`RHAPTO_SECRET_KEY`, or one derived from
`RHAPTO_API_TOKEN` if that's unset) and are never returned by the API once saved — Settings only
ever shows a masked placeholder or, for the LLM provider, the last four characters of the stored
key.

## Your data in this repo

`profile/` — your real profile — is gitignored and never committed. `profile.example/` is
fictional demo data ("Maya Chen", an invented employer called ExampleCo) used throughout this
documentation and the screenshot walkthrough; nothing under `profile.example/` describes a real
person or company. This repo has no CI workflow (no `.github/`) to enforce that automatically —
`scripts/check-no-personal-data.py` is a script you run by hand (`python
scripts/check-no-personal-data.py` from the repo root) that fails if any organisation name from a
real, local `profile/blocks.yaml` shows up in a git-tracked file; it is a no-op if you have no
`profile/` at all. It checks organisation names only — it is not a general secret scanner, and it
cannot catch, for example, a real credential fragment rendered into a screenshot (see the
screenshot walkthrough's own guards in `apps/web/scripts/screenshots.mjs` for that class of leak).

## Deleting

To remove everything Rhapto has stored, stop the stack and drop its Compose volumes (for example
`docker compose down -v`). There is nothing to delete anywhere else — nothing about your profile,
jobs, or applications lives outside your own Postgres volume.
