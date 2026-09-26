# Runbook — making the front page public

**Goal:** anyone who opens `https://rhapto.augaster.com` sees what Rhapto is, without logging in. If
they want to use it, *then* they get a login. Today the whole hostname sits behind Cloudflare Access,
so a stranger gets a login screen and no explanation — there is no link you can send anybody.

**Do this AFTER an invited person has signed in successfully**, not in the same window as the
access-mode switch (`docs/runbook-access-mode.md`). Changing Cloudflare's path routing and switching
authentication at the same time means a failure could be either, and you will not know which.

## Why this is safe, and where it stops being safe

The landing page makes **zero API calls** — verified: no `useQuery`, no `fetch`, no client hooks in
`apps/web/src/components/landing/Landing.tsx`. It is server-rendered markup. So a visitor with no
session can render it completely without touching any user's data.

What must never be bypassed is `/api/v1/*`. If it is, the application's own invite allowlist becomes
the only thing between the internet and everyone's résumés. That allowlist is genuinely well tested —
forged-token tests, an empty list that fails closed, three review rounds — but removing the outer door
buys nothing here, because the landing page never calls the API.

## Prerequisite in the app

`"/"` must be in `PUBLIC_ROUTES` in `apps/web/src/components/shell/TokenGate.tsx`, so `/` renders the
landing page without waiting on `/me`. A2's fix round already moved the `PUBLIC_ROUTES` check *above*
the access-mode branch, which is what makes this possible. The queued task
`.superpowers/sdd/2026-09-25-multi-tenancy-a-b/task-landing-default-brief.md` does this as part of
moving the dashboard to `/dashboard`; ship that first.

## Cloudflare configuration

In Zero Trust → Access → Applications, add a **second** self-hosted application. A more specific path
takes precedence over the hostname-wide application, so this one carves the public holes and the
existing application keeps protecting everything else.

| | |
|---|---|
| Application | `rhapto-public` |
| Domain | `rhapto.augaster.com` |
| Paths | `/` (exact), `/about`, `/_next/*`, `/favicon.ico` |
| Policy | one policy, action **Bypass**, rule **Everyone** |

`/_next/*` is not optional. `next/font/google` self-hosts the fonts at build time under
`/_next/static/media/`, so blocking it renders your public page unstyled with no fonts — which looks
worse than the login screen you are replacing. Those files are compiled client code and public
assets; the repository itself is public under AGPL, so there is nothing there to protect.

Do **not** add: `/api/v1/*`, `/jobs`, `/pipeline`, `/profile`, `/resumes`, `/settings`, `/dashboard`.

## Verify — do not skip, and do not verify in a browser you are logged into

```bash
scripts/check-access-boundary.sh
```

It sends no cookies and checks three things: the public paths reach the origin and return 200; a
`/_next/static/...` URL **scraped from the live page** also returns 200, so the page is styled; and
every data-bearing path is answered by a Cloudflare redirect to the team login domain.

**The subtlety it exists for:** an unauthenticated request to a protected path is answered by
Cloudflare with a 302 and never reaches the origin. A bypassed path reaches the origin, which answers
for itself — 200 for a page, **401 for the API**. So a 401 from `/api/v1/me` is *not* a pass. It means
Access let the request through and only the application refused it, which is one misconfigured
allowlist away from a data leak and completely invisible if you only check "am I locked out".

Then, in a browser you are **not** logged into: open `https://rhapto.augaster.com` and confirm you see
the styled landing page with the five steps, no login prompt, and that clicking through to the app
does prompt for a login.

## Rollback

Delete the `rhapto-public` application. The hostname-wide application resumes covering every path
immediately; nothing in the app or the database changes. This is a Cloudflare-only change, which is
the reason to do it separately from anything that touches the server.

## After this

`https://rhapto.augaster.com` is the link to send people. `augaster.com` can point at it rather than
carrying a duplicate explanation of the product.
