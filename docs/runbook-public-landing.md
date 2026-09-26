# Runbook — making the front page public

**Goal:** anyone who opens `https://rhapto.augaster.com` sees what Rhapto is, without logging in. If
they want to use it, *then* they get a login. Today the whole hostname sits behind Cloudflare Access,
so a stranger gets a login screen and no explanation — there is no link you can send anybody.

**Do this AFTER an invited person has signed in successfully**, not in the same window as the
access-mode switch (`docs/runbook-access-mode.md`). Changing Cloudflare's path routing and switching
authentication at the same time means a failure could be either, and you will not know which.

## Why this is safe, and where it stops being safe

**Correction (review finding I1):** an earlier version of this section verified `Landing.tsx` alone
(no `useQuery`, no `fetch`, no client hooks) and stopped there. That verification is scoped to the
wrong component — the page actually served at `/` is `layout → Shell → TokenGate → Landing`, and
`TokenGate` does call the API (`useMe`). What is true, and is what makes this safe: `TokenGate`
short-circuits on its `PUBLIC_ROUTES` (which `/` joined as part of the routing task this runbook
depends on, and which now also gates `useMe`'s `enabled` flag, review finding I1) before that call is
even made, so once this runbook's bypass is live, `/` issues **no API call at all** and renders no
user data. `Landing.tsx` itself still makes no calls of its own either way — that part of the original
claim was correct, just not the reason the page as a whole is safe.

What must never be bypassed is `/api/v1/*`. If it is, the application's own invite allowlist becomes
the only thing between the internet and everyone's résumés. That allowlist is genuinely well tested —
forged-token tests, an empty list that fails closed, three review rounds — but removing the outer door
buys nothing here, because `/` issues no API call at all.

## Prerequisite in the app

`"/"` must be in `PUBLIC_ROUTES` in `apps/web/src/components/shell/TokenGate.tsx`, so `/` renders the
landing page without waiting on `/me`. A2's fix round already moved the `PUBLIC_ROUTES` check *above*
the access-mode branch, which is what makes this possible. The queued task
`.superpowers/sdd/2026-09-25-multi-tenancy-a-b/task-landing-default-brief.md` does this as part of
moving the dashboard to `/dashboard`; ship that first.

## ATTEMPTED 2026-09-26 AND IT DID NOT WORK — read this before trying again

The configuration below was tried on the live account and **failed**. Do not repeat it as written.

What was built: a second self-hosted application named `rhapto`, destinations `rhapto.augaster.com/`,
`/about`, `/_next/*`, `/favicon.ico`, with one policy `Rhapto-Public`, action **Bypass**, include
**Everyone**. Saved and attached.

What happened: `/` and `/about` kept returning `302` to the Access login, and so did `/favicon.ico` and
`/_next/static/...`. So the bypass application matched **nothing**.

How that was established, rather than guessed: the `aud` claim inside the 302's `Location` meta token
was compared against `RHAPTO_ACCESS_AUD` on the server. **They matched** — meaning the redirect came
from the hostname-wide application the API verifies against, so the bypass application was never
evaluated for any of its four paths.

The likely cause, and the reason the obvious fix is not enough: a hostname-wide application
(`rhapto.augaster.com`) and a root destination (`rhapto.augaster.com/`) are the same destination, so
specificity cannot break the tie for `/`. That alone does not explain `/about` also failing, so
something in the destination rows or their attachment was additionally wrong — unresolved.

**The approach to try instead: invert the two applications.** Give the bypass application the public
paths, and change the *protected* application from the bare hostname to an explicit list —
`/jobs`, `/dashboard`, `/pipeline`, `/profile`, `/resumes`, `/settings`, `/api/*`. No overlap, so no
precedence question.

**The risk of that inversion, stated plainly: anything you forget to list becomes public.** Run
`scripts/check-access-boundary.sh` after every save, and stop immediately if any line under PROTECTED
returns anything other than a redirect to Access. Do not attempt it tired.

**The zero-risk alternative** is to put the explainer on `augaster.com`, which is already public and
already links to Rhapto, and leave `rhapto.augaster.com` as the app. Ten minutes, nothing to expose.

## Cloudflare configuration (as attempted — see the correction above)

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
