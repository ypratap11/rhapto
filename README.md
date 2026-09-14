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
cp .env.example .env            # add your LLM provider key (see AI provider setup below)
cp -r profile.example profile   # then replace the fictional data with yours (profile/ is gitignored)
cd apps/api && uv sync
uv run rhapto profile validate ../../profile
uv run rhapto tailor --jd path/to/jd.txt --profile ../../profile --out ../../out
```

`tailor` writes `out/<company>-<role>/resume.docx`, `resume.pdf` (when LibreOffice is installed, otherwise skipped),
`cover-note.md`, and `package.json` with the guardrail report and change log. Exit code 3 means the guardrails
blocked the draft; the files are still written so you can see why. Exit code 1 is an error; 2 is a usage error from
the command-line parser.

Pass `--document your-resume.docx` to tailor your own resume instead of the block library: `tailor` then edits your
document's paragraphs in place (tune mode) rather than composing a new one, and `package.json` carries the list of
edits alongside the guardrail report — for example
`uv run rhapto tailor --jd path/to/jd.txt --profile ../../profile --document your-resume.docx --out ../../out`.

Without LibreOffice locally, use the container:

```bash
docker build -f apps/api/Dockerfile --target cli -t rhapto-cli .
docker run --rm --env-file .env -v "$PWD:/work" rhapto-cli tailor --jd jd.txt --profile profile --out out
```

Development: `uv run pytest`, `uv run ruff check .`, `uv run mypy`, `uv run lint-imports` from `apps/api`;
`bash scripts/codegen.sh` after editing `packages/schemas`.

## Backend (phase 0.2)

```bash
cp .env.example .env          # generate RHAPTO_API_TOKEN; add your AI provider key in Settings once the web app is up, or set ANTHROPIC_API_KEY here as a fallback
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
`bash scripts/smoke-api.sh` exercises a running stack end to end (needs `curl` and `jq`). It is destructive:
its import step replaces the target instance's profile with `profile.example`, so never run it against an
instance that holds your real profile.

## Web app (phase 0.2)

```bash
docker compose up -d        # db, redis, api, worker, web
open http://localhost:3000
```

On first visit the app asks for the API URL (`http://localhost:8000`) and the bearer token from your `.env`
(`RHAPTO_API_TOKEN`). Then:

1. **Profile**: import your five YAML files (or the demo `profile.example` to try it) and edit blocks, tracks, and rules.
2. **Jobs** shows *Apply to these first*; press the action on the top row (Tailor, then Review, then Mark applied).
   Progress streams live, and the review step highlights the exact block behind each bullet and lists anything
   the guardrails blocked.
3. **Packages** lists what needs review (switch the filter for blocked, applied, or all).
4. **Pipeline** tracks what you submitted: drag applications across the board and keep notes and history.

Downloads are named after you, not the job.

Rhapto never submits anything. The last click is yours.

### AI provider setup

Open **Settings → AI provider**, pick a provider card, paste your key, choose a model (or "Other"), then
**Test connection** and **Save**. Keys are stored encrypted; the UI only ever shows the last four characters.
The Jobs page shows "Set up your AI provider" until one is configured.

| Provider | Env key | Models | Default |
| --- | --- | --- | --- |
| Anthropic | `ANTHROPIC_API_KEY` | claude-opus-5, claude-sonnet-5 | claude-sonnet-5 |
| OpenAI | `OPENAI_API_KEY` | gpt-5, gpt-5-mini | gpt-5 |
| Google Gemini | `GEMINI_API_KEY` | gemini-2.5-pro, gemini-2.5-flash | gemini-2.5-pro |

`.env` still works as a fallback: set `RHAPTO_LLM_PROVIDER` (default `anthropic`) and the matching key above,
plus `RHAPTO_LLM_MODEL` if you want a non-default model (change both together). The CLI
(`rhapto tailor --provider openai --model gpt-5`) always reads from `.env`, since it has no Settings UI.

Prompt caching: Rhapto marks the static prompt (rules and your document) for caching. Anthropic honours that
mark explicitly; OpenAI and Gemini cache prompt prefixes automatically, so their cache-creation token counts
always read 0 while cache reads still show up.

Development: from `apps/web`, `pnpm install`, `pnpm dev` (http://localhost:3000), `pnpm test`, `pnpm typecheck`,
`pnpm lint`, `pnpm build`. After changing the API, run `bash scripts/codegen.sh` to refresh
`packages/schemas/openapi.json` and the generated client types.

### Tune your own resume

Already have a resume you like? Upload it once under **Profile → Resume document** and Rhapto switches to tune
mode: instead of composing a new resume from your block library, Tailor edits your own document's wording in
place, and defaults to tune mode automatically whenever a document is on file. The review page's Changes pane
shows each edit as a before/after pair, and you can tweak any rewrite before saving a new version. Downloads
keep your document's original format and are named after you, not the job. Guardrails work the same way in tune
mode — they check every number, name, and date the edits introduce against your uploaded document, not just the
block library. Rhapto still never submits anything for you.

## Job discovery (phase 0.3)

Add the companies you follow to `profile/watchlist.yaml` (Greenhouse, Lever, or Ashby board slugs) and switch on
the aggregators you want (RemoteOK, Hacker News Who's Hiring). The worker polls every `RHAPTO_POLL_INTERVAL_HOURS`
(default 6) and the Queue's **Poll now** button runs a poll on demand. Every new posting is deduped, embedded
locally, and scored 0–100 against each of your tracks; the queue sorts by fit, low-fit jobs sit in their own
bucket you can rescue from, and re-posts are flagged, not re-queued. Scoring never calls the LLM.

### Location priority

Fit is scaled by where the job is, so a great role on the wrong continent cannot outrank a good one
down the road. Three answers in `profile/answers.yaml` (**Profile → Answers** in the web app — edit them
there any time, and the queue is re-scored as soon as you save) drive it:

| answer | example | what it does |
| --- | --- | --- |
| `location_home` | `Denver, CO` | Where you are. Used only as the default preferred area when `location_preferred` is empty — never sent to the LLM, and never written into an application. |
| `location_preferred` | `Denver, CO, Boulder, CO, Aurora, CO` | Comma-separated towns and regions you want. A whole-word match on the posting's location field puts the job in your preferred tier. |
| `remote_ok` | `yes` | `no`, `false` or `0` means a remote-only posting is worth no more to you than one abroad. Anything else (including a blank) means yes. |

**Qualify each entry with its state.** A bare `Denver` matches Denver, PA and Denver, NC too, and a bare
`Aurora` matches Aurora, IL — every Front Range namesake in the country would tier preferred. Write
`Denver, CO` instead: a trailing two-letter state code binds to the town before it, so `Denver, CO,
Boulder, CO` is two entries and not four, and a qualified entry needs both halves present in the posting
(in either spelling, so it matches `Denver, CO` and `Denver, Colorado` but not `Denver, PA`). An entry
that is not a `City, ST` pair — `Bay Area`, `Front Range`, `Colorado` — is matched whole-word as written.

Every posting lands in one tier, and its fit is multiplied accordingly: **preferred** ×1.0, **remote**
×0.95, **US** ×0.85, **abroad** ×0.60, **unknown** ×0.90. Only the posting's location field is read —
job descriptions name offices on three continents in their boilerplate. A named country settles it, so
"Dublin, Ireland" is abroad even when your preferred list names Dublin, CA — unless the same field also
names somewhere in the US, because boards list several offices at once and "San Francisco, CA; London,
UK" is still a job in San Francisco. A foreign city named next to its own country code wins over a
US state code that happens to be spelled the same: "Berlin, DE" is Germany, not Delaware. The queue's
**Region** filter (Preferred area / US and remote / Anywhere) and the chip on each job row show the result.

Two things to know. The tiering is **US-centric**: the country tier means the United States, so a user
based outside it gets `abroad` for their own city and should leave the Region filter on Anywhere until
the home country is derived from `location_home`. And a job with no location at all — anything you paste
by hand, and `rhapto score --jd` — tiers `unknown` and scores ×0.90, so a borderline one can land in
the Low fit bucket; rescue it from there, or fill in its location.

**Workday** boards use `<host prefix>/<site>` instead of a slug, and you can read both off the careers URL:
`https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/...` becomes `nvidia.wd5/NVIDIAExternalCareerSite`
(keep the `wd5`-style data-centre suffix — it differs per tenant). Set keywords on Workday rows: they are pushed
into Workday's own search, and without them a poll walks a board with thousands of postings.

```bash
rhapto discover --profile ./profile          # one poll from the terminal, nothing stored
rhapto score --jd job.txt --profile ./profile # per-track breakdown for one description
```

Adding a source is one adapter module plus a registry entry (`apps/api/src/rhapto/services/discovery/sources/`);
LinkedIn and Indeed scraping stay out of core.
