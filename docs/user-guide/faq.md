# FAQ

### Does Rhapto apply for me?

No, never. Rhapto opens the employer's own application page and downloads a tailored resume, but
the last click — the one that submits — is always yours. Nothing in Rhapto fills out or submits an
employer's form; see [`../product/overview.md`](../product/overview.md#the-human-in-the-loop-rule).

### Why is a job's fit blank?

A newly discovered job shows a dashed ring instead of a number until the scorer catches up — the
page refetches it every 3 seconds for up to a minute. If it's still dashed after that, give the
page a refresh; if it stays blank, the job may not have been matched to any track yet.

### Why did a resume get blocked?

A guardrail rejected something in it — most often a metric that doesn't trace back to a block
marked `verified: true`, or a name or detail the block library doesn't support. The guardrail
panel on the job page or the resume's review page lists every violation with a link that jumps
straight to it, so you can fix the source and regenerate.

### Why can I not filter by salary?

Salary and work type aren't filters yet in this version of the portal — a deliberate scope cut, not
an oversight. Salary still shows on a job's card whenever the source provides it; you just can't
filter the grid by it today.

### What does "No longer listed" mean?

A job a source stopped returning on two consecutive polls is marked no-longer-listed: it drops out
of Recommended for you and the Resumes queue, and any application tied to it shows the label. If the
same role reappears later, Rhapto links the new posting back to the original as a repost and offers
to reuse the resume you already tailored for it.

### Where do my keys live?

Both your LLM provider key and any job-source keys are encrypted at rest in your own Postgres
database and are never returned by the API once saved — Settings only ever shows a masked
placeholder or, for the LLM provider, the key's last four characters.

### Can I use it without Docker?

The CLI pipeline (`rhapto tailor`) can run directly with `uv` from `apps/api` without Docker at
all. The full portal needs Postgres and Redis at minimum; `docker compose up -d db redis` gets you
those while you run the API, worker, and web app locally with `uv` and `pnpm`. See the README's
"Development without Docker" section for the exact commands.

### How do I start over?

Stop the stack and drop its Compose volumes (for example `docker compose down -v`) to clear
everything Rhapto has stored, then bring it back up — see
[`../product/privacy.md`](../product/privacy.md#deleting).

### What data leaves my machine?

Only requests to the job sources you've enabled, and the prompts sent to your configured LLM
provider when you tailor a resume. Rhapto sends no telemetry to anyone. See
[`../product/privacy.md`](../product/privacy.md).

### How do I report a bug?

Open an issue on the project's repository with what you were doing, what you expected, and what
happened instead — screenshots help. Rhapto is AGPL-3.0 and open source, so pull requests are
welcome too.
