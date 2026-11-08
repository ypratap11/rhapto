# Runbook — opening sign-up (anyone can sign in, 3 free runs each)

Written to be followed at 2am with no prior context. `$RHAPTO` is `/opt/rhapto`, which is **not a git
checkout** (no `.git`, no remote): code arrives by `scripts/deploy-server.sh`, never by `git` on the box.

**What this does:** with `RHAPTO_OPEN_SIGNUP=true` anyone who passes Cloudflare Access gets an account
and a free allowance paid for by the server's `ANTHROPIC_API_KEY`. **What it risks:** the server key's
spend. The allowance is capped per account and in total per month; the steps below set both caps and
the watch queries.

**How the allowance works:**

- The **3-run allowance** (`RHAPTO_TRIAL_RUNS`) and the **first free import** are **per account and
  lifetime**, not monthly. They do not refill.
- The **$50 budget** (`RHAPTO_MONTHLY_FREE_BUDGET_USD`) is shared by all accounts and **resets on the
  1st (UTC)**. When it is spent, free runs answer 409 `free_runs_paused` ("Free runs are paused until
  the 1st of next month") and the person is pointed to Settings to add their own key.

## 1. Back up. Not optional.

```bash
ssh root@64.225.30.51 'ls -l /usr/local/sbin/rhapto-backup.sh'      # must exist
ssh root@64.225.30.51 '/usr/local/sbin/rhapto-backup.sh'
ssh root@64.225.30.51 'tail -n 20 /var/log/rhapto-backup.log'       # must show a fresh, successful run
```

If the script is missing, stop and take the manual dump from `docs/runbook-deploy.md` step 2 instead.

## 2. Anthropic Console

Confirm the server's `ANTHROPIC_API_KEY` belongs to the **workspace that holds the Max-plan credit**,
then set that workspace's **monthly spend limit at or slightly above the app cap** ($50, so about $55).
The app cap is the first fence; this limit is the one that still holds if the app's metering is wrong.

## 3. Confirm the model is priced

A blank `RHAPTO_LLM_MODEL` (the default) means the provider default from
`apps/api/src/rhapto/engine/providers/registry.py` (`claude-sonnet-5` for Anthropic), which `printenv`
does not show. Whichever model id is in force must appear as a key in `MODEL_RATES`
(`apps/api/src/rhapto/services/pricing.py`). An unpriced model is charged at the table's highest rate
(`claude-opus-5`), which under-records a pricier model, so the $50 budget would last longer in the
ledger than it does on the invoice.

Print the effective model and whether it is priced (no key is printed). It must end in `True`:

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose exec -T api python -c "from rhapto.config import get_settings; from rhapto.services.llm import env_llm_config; from rhapto.services.pricing import estimate_cost; from rhapto.engine.providers.llm import TokenUsage; c=env_llm_config(get_settings()); print(c.model, estimate_cost(c.model, TokenUsage()) is not None)"'
```

If it prints `False`, set a priced `RHAPTO_LLM_MODEL` in `.env` before going on.

## 4. Edit `/opt/rhapto/.env`

```
RHAPTO_OPEN_SIGNUP=true
RHAPTO_TRIAL_RUNS=3
RHAPTO_MONTHLY_FREE_BUDGET_USD=50
```

**Keep `RHAPTO_ALLOWED_EMAILS`.** The api's lifespan refuses to start when it and
`RHAPTO_ALLOWED_EMAIL_DOMAINS` are both empty, and it must still include the owner.

## 5. Deploy

**Edit `.env` before deploying:** the web build bakes in `RHAPTO_TRIAL_RUNS` and `RHAPTO_OPEN_SIGNUP`
(`NEXT_PUBLIC_*`), so a change made after the build needs another build, not a restart.

From a workstation with an up-to-date `main` (the owner runs it with `!`):

```bash
scripts/deploy-server.sh api worker web
```

**With no arguments the script rebuilds only the web**, so name all three. It stops at a
`Deploy this to ...? [y/N]` prompt; with no terminal (Claude Code's `!`, a tool call) that prompt is
invisible (bash prints a `read -p` prompt only to a terminal) and the script exits there with no
message, so pipe the answer in:
`echo y | scripts/deploy-server.sh api worker web`. The rebuilt api runs
migration `0015` on start. Confirm:

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose exec -T db psql -U rhapto -d rhapto -tAc "SELECT version_num FROM alembic_version;"'
# expect 0015
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose ps --format "{{.Service}} {{.State}}" && docker compose logs --tail 40 api worker | grep -iE "error|traceback" || echo "no errors"'
```

## 6. Verify the three values inside the api container

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose exec -T api printenv RHAPTO_OPEN_SIGNUP RHAPTO_TRIAL_RUNS RHAPTO_MONTHLY_FREE_BUDGET_USD'
# expect: true / 3 / 50, one per line
```

Never `printenv` the whole environment or `cat .env`: they hold `RHAPTO_ALLOWED_EMAILS` and the keys.

## 7. Cloudflare Zero Trust

Zero Trust -> Access -> Applications -> the Rhapto application -> change the policy **Include** to
**Everyone**, with **One-time PIN** enabled as a login method. Leave nothing in **Require** (Require is
AND, so a rule there denies everyone else regardless of Include).

**The Zero Trust Free plan has a 50-user seat limit.** Check the count in Zero Trust -> Users, and
remove inactive users or upgrade before it fills; at the limit new people cannot sign in at all.

Do this step **after** step 5 succeeds: until the api accepts open sign-up, the app-side allowlist is
the only gate behind the open policy.

## 8. Smoke test as a visitor

In a private window, with an address that is **not** on the allowlist: open the site, confirm there is
no "Request beta access" link, sign in with the one-time code, reach `/start`, and see the 3-run
allowance. Do not run a tailor on the owner's key unless you mean to spend a few cents.

## 9. Rollback

```bash
# in /opt/rhapto/.env:  RHAPTO_OPEN_SIGNUP=false
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose up -d --force-recreate api'
```

Then restore the Cloudflare Access policy's **email list** (Include -> Emails). The web keeps showing
open-sign-up copy until it is rebuilt: `scripts/deploy-server.sh web` after the `.env` change. Accounts
created while open stay; with the flag off the api refuses everyone not on the allowlist (403).

## 10. Check the month's spend

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose exec -T db psql -U rhapto -d rhapto -tAc "SELECT sum(cost_usd) FROM free_spend WHERE created_at >= date_trunc('"'"'month'"'"', now(), '"'"'UTC'"'"');"'
```

Compare with $50. The query is the ledger the app enforces; the Anthropic Console is the invoice.

## 11. Watch for abuse

```bash
ssh root@64.225.30.51 'cd /opt/rhapto && docker compose exec -T db psql -U rhapto -d rhapto -c "SELECT user_id, count(*), sum(cost_usd) FROM free_spend WHERE created_at >= date_trunc('"'"'month'"'"', now(), '"'"'UTC'"'"') GROUP BY user_id ORDER BY 3 DESC LIMIT 10;"'
```

Look for many new accounts that share a mailbox, for example `name+1@`, `name+2@`. `free_spend` holds
user ids, not addresses; look the ids up inside the psql session and **do not paste addresses into
shell history, tickets or chat**. To respond, set those accounts' allowance to the cap and remove their
Cloudflare seats (Zero Trust -> Users):

```sql
-- 3 = the current RHAPTO_TRIAL_RUNS; use the live value if the cap has changed
UPDATE users SET trial_runs_used = 3, free_import_used_at = now() WHERE id IN (...);
```
