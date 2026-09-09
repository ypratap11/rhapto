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
