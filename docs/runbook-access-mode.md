# Runbook — switching production to Cloudflare Access (Phase A)

Written to be followed at 2am with no prior context. Every fact below was verified against the live
box on 2026-09-26, not recalled.

**What this does:** turns the single-tenant instance at `rhapto.augaster.com` into a multi-tenant one
behind Cloudflare Access, so a second person can be invited. **What it risks:** the owner's own
account, which holds **1,819 jobs** and is the only account with real data in it.

## Starting state, as verified

| Thing | Value |
|---|---|
| Schema revision | `0010` — migration `0011` will apply during this deploy |
| `RHAPTO_SECRET_KEY` | **pinned** in `/opt/rhapto/.env`. Do not touch it, and do not touch `RHAPTO_API_TOKEN` — provider keys are Fernet-encrypted under a key derived from the token, and changing either makes every stored key undecryptable |
| Containers | `api`, `db`, `redis`, `web`, `worker` all running |
| `/opt/rhapto` | **not a git checkout.** No `.git`, no remote. Code arrives by file sync — `git fetch`/`git checkout` there cannot work |
| Already set in `.env` | `RHAPTO_ACCESS_AUD` (64 hex, validated), `RHAPTO_ACCESS_TEAM=rhapto`, `RHAPTO_ALLOWED_EMAILS=<owner>`, `RHAPTO_AUTH_MODE=token` |
| Cloudflare | One-time PIN enabled and tested; team domain renamed to `rhapto.cloudflareaccess.com`; Access policy still restricted to the owner's email |

## Step 0 — merge and push, because the deploy script ships `origin/main`

All of Phase A is on `multi-tenancy-a-b` and unpushed. `scripts/deploy-server.sh` deploys
**`origin/main`** by default, deliberately, so that what reaches production does not depend on which
branch happens to be checked out. So this happens first:

```bash
git checkout main && git merge --no-ff multi-tenancy-a-b
git push origin main
```

Nothing is deployed by pushing. If you would rather deploy the branch without merging, that is
`RHAPTO_REF=multi-tenancy-a-b scripts/deploy-server.sh`, but then the box is running code that is not
on `main` and the next ordinary deploy will silently revert it.

## Step 1 — back up the database. Not optional.

```bash
ssh root@64.225.30.51
cd /opt/rhapto
docker compose exec -T db pg_dump -U rhapto -Fc rhapto > /root/rhapto-pre-0011-$(date -u +%Y%m%dT%H%M%SZ).dump
ls -lh /root/rhapto-pre-0011-*.dump        # must be non-trivial, ~20MB at 1,819 jobs
cp /opt/rhapto/.env /root/.env.pre-0011
```

The `.env` copy is what makes the rollback safe for credentials. Take both.

## Step 2 — the one `.env` change, and why it needs a rebuild

Change one line in `/opt/rhapto/.env`:

```
RHAPTO_PUBLIC_API_URL=
```

It is currently `https://rhapto.augaster.com`. **Empty is meaningful, not absent:**
`SAME_ORIGIN_DEPLOYMENT` is `process.env.NEXT_PUBLIC_API_URL === ""`
(`apps/web/src/lib/api/client.ts`), and compose passes it with a single dash
(`${RHAPTO_PUBLIC_API_URL-...}`) precisely so empty survives. An absent variable gets the localhost
default and same-origin mode never engages.

**This is a build-time value.** Next.js inlines `NEXT_PUBLIC_*` into the client bundle, so it needs a
rebuild, not a restart.

Leave `RHAPTO_AUTH_MODE=token` for now. That is the point of the next step.

## Step 3 — deploy in token mode first, and prove the proxy works

```bash
# from your workstation, not the server
scripts/deploy-server.sh api worker web
```

This backs up `/opt/rhapto`, syncs `git archive origin/main` (excluding `.env` and `profile/`),
rebuilds, and brings the stack up. The api container's CMD runs `rhapto db upgrade` first, so
migration `0011` applies here.

Then verify, in this order:

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose exec -T db psql -U rhapto -d rhapto -tAc "SELECT version_num FROM alembic_version;"'
# expect 0011
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose ps --format "{{.Service}} {{.State}}" && docker compose logs --tail 40 api worker | grep -iE "error|traceback" || echo "no errors"'
```

**Then open `https://rhapto.augaster.com` in a browser and confirm it still works for you.**

This is the step that de-risks everything after it. You are still in token mode, so authentication has
not changed — but the browser is now talking to the API through the new same-origin proxy. If the site
works here, the proxy and the build arg are both good. If it does not, the fault is the build arg or
the proxy, **not** the authentication code, and you have not touched authentication yet.

## Step 4 — flip to access mode

```bash
# in /opt/rhapto/.env
RHAPTO_AUTH_MODE=access
```

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose up -d --force-recreate api worker'
```

The api **will refuse to start** if `RHAPTO_ALLOWED_EMAILS` and `RHAPTO_ALLOWED_EMAIL_DOMAINS` are
both empty — that is deliberate, and the error names the fix. Unconfigured never means open.

**Then sign in yourself, in a fresh private window.** Expect the Access one-time-PIN screen, a code by
email, then your own dashboard with your 1,819 jobs. If you are refused, you are the only person
affected and rollback is step 7.

## Step 5 — only now open the Cloudflare policy

**Do not do this before step 4 succeeds.** Until the app-side allowlist is live, the Cloudflare policy
is the only gate on a still-single-tenant instance, and One-time PIN is enabled — so opening it early
lets anyone who can receive email into the owner's account.

Zero Trust → Access → Applications → the rhapto app → set the policy to any authenticated user, and
make sure no email is left in **Require** (Require is AND, so an email there denies everyone else no
matter what Include says).

After this, Cloudflare is never edited to invite someone again.

## Step 6 — invite the second person

```
RHAPTO_ALLOWED_EMAILS=<owner>,<second person>
```

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose up -d --force-recreate api worker'
```

Have them open `https://rhapto.augaster.com`, enter their email, and use the code. They should land on
a **populated** first screen — that is A5's backfill copying public postings into the new account. It
must contain **no** job whose source is `manual`: those are hand-pasted and private to the owner. If a
manual job appears, stop, tell the owner, and treat it as a privacy incident rather than a bug.

Their first poll is deferred by a minute per user (A4's stagger), so their own fresh jobs arrive on the
next cycle, not instantly.

## Step 7 — rollback

Any failure in steps 3–4:

```bash
ssh root@64.225.30.51
cd /opt/rhapto
docker compose stop api worker
docker compose exec -T db psql -U rhapto -d rhapto -tAc "SELECT version_num FROM alembic_version;"
# if 0011, step the schema back BEFORE the old image starts:
docker compose run --rm api alembic downgrade 0010
cp /root/.env.pre-0011 /opt/rhapto/.env
# restore the pre-deploy file backup; its path is printed by deploy-server.sh
rm -rf /opt/rhapto && mv /root/rhapto-predeploy-<timestamp> /opt/rhapto
cd /opt/rhapto && docker compose up -d --build
```

If the schema is *damaged* rather than merely ahead, restore step 1's dump instead of downgrading:

```bash
docker compose stop api worker
docker compose exec -T db dropdb   -U rhapto rhapto
docker compose exec -T db createdb -U rhapto rhapto
cat /root/rhapto-pre-0011-<timestamp>.dump | docker compose exec -T db pg_restore -U rhapto -d rhapto --no-owner --no-privileges
```

Reverting `RHAPTO_AUTH_MODE` to `token` is itself a complete rollback of authentication, with no
schema change, and is worth trying before anything heavier.

## Model cost: invited accounts spend the owner's key, by decision

`services/llm.py:132` is `stored_llm_config(...) or env_llm_config(settings)`, so an account with no
provider key of its own falls back to the **server's** `ANTHROPIC_API_KEY`, with
`RHAPTO_LLM_MODEL=claude-opus-5`. An invited person therefore needs no API key and just works — and
every resume they tailor bills the owner at the measured **29–36c**, about $6.50 per 20 applications.

**The owner confirmed this is intended (2026-09-26):** he does not want someone who has just lost a job
to have to buy an API key first. It is recorded here because it is a decision, not a default, and
because it is the behaviour *every* future invited account inherits.

Two consequences worth knowing before the guest list grows past family:

- It is unbounded. There is no per-user cap, and nothing in Phase A adds one. Ten active invitees
  applying to 20 roles a month is roughly $65/month on the owner's card.
- It contradicts the business plan's BYOK assumption (`rhapto-business-plan.md` argues against BYOK on
  paid seats). Fine while invitees are family; revisit before anyone unrelated is invited.

The control, when it is wanted, is to make the env fallback apply only in `token` mode — a self-hoster's
own key is their own business, whereas a hosted instance's key is the operator's.

## What is NOT in this runbook

- **Account deletion and retention** — Phase B (plan tasks 6–8), not built.
- **The `_defer_by` stagger** is sound for 2–10 users and breaks around 61 on an hourly interval.
- **`get_settings()` is `lru_cache(maxsize=1)`** and running a *subset* of `tests/unit` yields spurious
  `MissingSecretKeyError` failures. A test-infrastructure issue only; fix is planned as its own commit.
  If you see nine of those in a partial run, it is not your change.
