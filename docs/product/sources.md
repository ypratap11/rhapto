# Job sources

Rhapto polls two kinds of source: **aggregators** that search the market on your behalf, driven by
your saved searches, and **company boards** on your watchlist, polled directly. Settings → Job
sources shows every aggregator and lets you turn one on, enter its key, and test it; watchlist
boards are managed on Profile → Watchlist.

| Source | Kind | Needs a key | Cap | Notes |
|---|---|---|---|---|
| The Muse | Aggregator | No | 30 (live) / 100 (background) | Zero-setup, on by default |
| Remotive | Aggregator | No | 30 (live) / 100 (background) | Zero-setup, on by default |
| RemoteOK | Aggregator | No | 30 (live) / 100 (background) | Zero-setup, on by default |
| HN Who's Hiring | Aggregator | No | 30 (live) / 100 (background) | Zero-setup, on by default |
| Adzuna | Aggregator | Yes — `app_id`, `app_key` from developer.adzuna.com | 30 (live) / 100 (background) | Free tier available |
| Jooble | Aggregator | Yes — `api_key` from jooble.org/api/about | 30 (live) / 100 (background) | Free tier available |
| JSearch (Google Jobs) | Aggregator | Yes — `rapidapi_key` from rapidapi.com | 30 (live) / 100 (background) | Via RapidAPI |
| Greenhouse | Company board | No (per board, from your watchlist) | 30 (live) / 100 (background) | `boards.greenhouse.io/<board>` |
| Lever | Company board | No (per board, from your watchlist) | 30 (live) / 100 (background) | `jobs.lever.co/<slug>` |
| Ashby | Company board | No (per board, from your watchlist) | 30 (live) / 100 (background) | `jobs.ashbyhq.com/<slug>` |
| Workday | Company board | No (per board, from your watchlist) | 30 (live) / 100 (background) | Addressed as `<host prefix>/<site>`, not a plain slug — see below |

Settings → Job sources shows each aggregator's status as one of three states: **enabled** (on and
usable), **needs a key** (on, but no credentials saved yet), or **key set** (a key has been saved).
A saved key is never displayed back — the form only ever shows a masked placeholder, never the
key itself.

## Caps and timeouts

Every source gets an 8-second timeout per request. A live search (the one you trigger from the
Jobs page) caps each source at 30 results; the background poll the worker runs on its own schedule
caps each source at 100. A source that times out or errors is reported in the search's per-source
summary rather than silently dropped.

## Auto-discovered boards

When a live search result points at a job hosted on a company's own ATS — a URL under
`boards.greenhouse.io`, `jobs.lever.co`, `jobs.ashbyhq.com`, or a `*.myworkdayjobs.com` tenant —
Rhapto adds that board to your watchlist automatically, marked as discovered, so future postings
from that company are picked up without you having to find and add the board yourself. Remove it
from Profile → Watchlist if you're not interested in that employer.

Workday boards are the one source addressed differently from a plain slug: both halves — the host
prefix (its data-centre suffix, like `wd5`) and the site name — come straight off the careers URL,
for example `https://exampleco.wd5.myworkdayjobs.com/en-US/ExampleCoCareers/...` becomes
`exampleco.wd5/ExampleCoCareers`. Keywords are strongly recommended on a Workday watchlist row:
they become the board's own search text, and without them a poll walks a board that can list
thousands of postings.

## What Rhapto never does

Rhapto never scrapes LinkedIn, Indeed, or Glassdoor postings — those sites' terms forbid it, and
Rhapto sticks to open aggregator APIs and the ATS boards companies publish for their own careers
pages. Source credentials you enter in Settings are encrypted at rest and are never returned by
the API once saved; they leave your machine only in the request Rhapto itself makes to that
source's own API.
