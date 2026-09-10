# Rhapto

*Rhapto — every application, stitched to fit.*

Rhapto (from Greek ῥάπτω, "I stitch" — the root of *rhapsody*: a rhapsode was a "song-stitcher" who wove stories for each audience) is an open-source, human-in-the-loop AI job application copilot. It
discovers roles, classifies them against your career tracks, tailors your
resume from a provenance-checked block library, and queues everything for
your review. **Rhapto never submits an application for you — that last click
is always yours.**

Why another job tool? Most auto-apply bots spray fabricated resumes at
hundreds of jobs. Rhapto does the opposite: every bullet traces to a verified
fact you own, guardrails block invented metrics, and quality beats volume.

- Docs: `docs/requirements-architecture.md`
- Build guide for AI agents: `CLAUDE.md`
- Demo profile: `profile.example/` (your real data lives in gitignored `profile/`)

License: AGPL-3.0-only

## Quick start (CLI, phase 0.1)

```bash
cp .env.example .env            # add your ANTHROPIC_API_KEY
cp -r profile.example profile   # then replace the fictional data with yours (profile/ is gitignored)
cd apps/api && uv sync
uv run rhapto profile validate ../../profile
uv run rhapto tailor --jd path/to/jd.txt --profile ../../profile --out ../../out
```

`tailor` writes `out/<company>-<role>/resume.docx`, `resume.pdf` (when LibreOffice is installed, otherwise skipped),
`cover-note.md`, and `package.json` with the guardrail report and change log. Exit code 3 means the guardrails
blocked the draft; the files are still written so you can see why. Exit code 1 is an error; 2 is a usage error from
the command-line parser.

Without LibreOffice locally, use the container:

```bash
docker build -f apps/api/Dockerfile --target cli -t rhapto-cli .
docker run --rm --env-file .env -v "$PWD:/work" rhapto-cli tailor --jd jd.txt --profile profile --out out
```

Development: `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `uv run lint-imports` from `apps/api`;
`bash scripts/codegen.sh` after editing `packages/schemas`.

## Backend (phase 0.2)

```bash
cp .env.example .env          # set ANTHROPIC_API_KEY and generate RHAPTO_API_TOKEN
docker compose up -d          # db, redis, api (http://localhost:8000), worker

# upload a profile (swap profile.example for your own gitignored profile/ when you have one)
TOKEN=$(grep RHAPTO_API_TOKEN .env | cut -d= -f2-)
curl -fsS -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8000/api/v1/profile/import \
  -F files=@profile.example/blocks.yaml -F files=@profile.example/tracks.yaml \
  -F files=@profile.example/guardrails.yaml -F files=@profile.example/answers.yaml \
  -F files=@profile.example/watchlist.yaml

open http://localhost:8000/api/v1/docs
```

Every request except `/api/v1/health`, `/api/v1/openapi.json` and `/api/v1/docs` needs
`Authorization: Bearer <RHAPTO_API_TOKEN>`. Paste a job description with
`POST /api/v1/jobs`, start tailoring with `POST /api/v1/jobs/{id}/tailor`, follow progress on
`GET /api/v1/tasks/{id}/events` (Server-Sent Events), then fetch, edit, or download the package under `/api/v1/packages`.
Editing a package re-runs the guardrails and creates a new version; a `blocked` status means a guardrail failed and the
report says why. Downloads of a blocked package carry `X-Rhapto-Guardrails: blocked` and a `GUARDRAILS-BLOCKED.md` in
the zip, so a blocked draft cannot be mistaken for a clean one. PDFs for edited versions are rendered by the worker a few seconds after the edit; the DOCX is
immediate. The tracker lives under `/api/v1/applications`. Nothing here submits an application anywhere.

Development without Docker for the app itself: `docker compose up -d db redis`, then from `apps/api`:
`uv run rhapto db upgrade`, `uv run uvicorn rhapto.api.app:app --reload`, and in another shell
`uv run arq rhapto.worker.main.WorkerSettings`. Tests: `uv run pytest` (API tests need the compose `db`).
`bash scripts/smoke-api.sh` exercises a running stack end to end (needs `curl` and `jq`).
