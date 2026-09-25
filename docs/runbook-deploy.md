# Deploy runbook — phase0-tenancy-fixes

Written to be followed at 2am with no prior context. `$RHAPTO` is `/opt/rhapto`. **Do not skip
step 3 or step 5.**

Source: `.superpowers/sdd/2026-09-24-shared-job-pool/final-review.md` (findings C1/C2, I1, I2, I4,
I5). Nothing here is invented beyond that review's runbook section.

## 1. Freeze

Stop the worker so no poll or tailor starts mid-deploy. Leave the API up for now.

```bash
cd /opt/rhapto
docker compose stop worker
curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/dashboard | tee /root/dashboard-pre-0010.json
```

Keep that file — step 7f compares against it.

## 2. Back up the database *and* the `.env`

```bash
docker compose exec -T db pg_dump -U rhapto -Fc rhapto > /root/rhapto-pre-0010-$(date -u +%Y%m%dT%H%M%SZ).dump
ls -lh /root/rhapto-pre-0010-*.dump          # must be non-trivial (~16MB at 1,430 jobs)
cp /opt/rhapto/.env /root/.env.pre-0010
```

The `.env` copy is what makes the rollback safe for credentials — do not skip it.

(`scripts/backup-db.sh` does the same thing with retention, but needs a host `pg_dump` at PG16+;
the `exec` form above is always version-matched.)

## 3. Confirm the starting revision — the migration-ID check

```bash
docker compose exec -T db psql -U rhapto -d rhapto -c "SELECT version_num FROM alembic_version;"
```

It **must print exactly `0009`**. If it prints `0010`, **STOP and do not deploy**: this database
carries the abandoned `shared-job-pool` branch's schema, the migration will silently no-op (an
opaque revision id makes the two states indistinguishable to alembic), and the new code will then
fail on the dropped `jobs.user_id`. Corroborate:

```bash
docker compose exec -T db psql -U rhapto -d rhapto -c "\d jobs" | grep -E 'user_id|owner_user_id'
```

Expect `user_id` present and `owner_user_id` absent.

## 4. Pre-flight the duplicate guards

Run this **hours before the deploy window, not inside it.**

```bash
docker compose exec -T db psql -U rhapto -d rhapto <<'SQL'
SELECT user_id, job_id,            count(*) FROM applications GROUP BY 1,2   HAVING count(*)>1;
SELECT user_id, source, board,     count(*) FROM watchlist    GROUP BY 1,2,3 HAVING count(*)>1;
SELECT user_id, job_id, track_id,  count(*) FROM job_scores   GROUP BY 1,2,3 HAVING count(*)>1;
SELECT user_id, job_id, version,   count(*) FROM packages     GROUP BY 1,2,3 HAVING count(*)>1;
SQL
```

All four must return zero rows. If `watchlist` returns any: keep one row per
`(user_id, source, board)`, prefer the row with `discovered = false`, union the `keywords` arrays
into the survivor, delete the rest. Re-run until clean.

## 5. The secret key — exact order of operations

**Do this BEFORE rebuilding anything.**

Read the live token and compute the key the existing ciphertext was encrypted under:

```bash
grep -E '^RHAPTO_API_TOKEN=' /opt/rhapto/.env
docker compose exec -T api python -c "import base64,hashlib,os; print(base64.urlsafe_b64encode(hashlib.sha256(os.environ['RHAPTO_API_TOKEN'].encode()).digest()).decode())"
```

Equivalently, `scripts/print-derived-secret-key.sh` runs the same computation from the host (it
reads `RHAPTO_API_TOKEN` from the environment and never prints the token itself):

```bash
RHAPTO_API_TOKEN="$(grep -E '^RHAPTO_API_TOKEN=' /opt/rhapto/.env | cut -d= -f2-)" \
  /opt/rhapto/scripts/print-derived-secret-key.sh
```

Write that 44-character value into `/opt/rhapto/.env`:

```
RHAPTO_SECRET_KEY=<the 44-character value printed above>
```

Then confirm both lines:

```bash
grep -E '^RHAPTO_(SECRET_KEY|API_TOKEN)=' /opt/rhapto/.env
```

- **Do NOT run `Fernet.generate_key()`.** A fresh key makes every stored provider key and
  aggregator credential permanently undecryptable.
- **Do NOT change `RHAPTO_API_TOKEN`** in this window, or ever again without first re-entering the
  provider keys in Settings. Rotating the token no longer breaks decryption once the derived value
  is pinned explicitly — pinning it is what decouples the two — but changing both at once loses the
  ability to recompute.
- Why this works: `services/secrets.py` prefers a configured key verbatim, and `derive_key` is
  exactly `urlsafe_b64encode(sha256(token))`. The derived value supplied as an explicit key is
  byte-identical to the one that encrypted the data, so every existing ciphertext still decrypts.
  Verified by round-trip.
- Rotating to a genuinely new key is a **separate, later** operation: set the new key, then
  re-enter the provider key in Settings and re-save each aggregator credential. Not part of this
  deploy.

## 6. Deploy

```bash
cd /opt/rhapto
git fetch --all
git checkout phase0-tenancy-fixes
git log --oneline -1                      # expect the tip commit of this branch
docker compose build api worker web
docker compose up -d
```

The `api` container's CMD is `rhapto db upgrade && uvicorn …`; `db_upgrade` now builds a bare
`Settings()` so the migration runs without needing the key, and the migration runs exactly once,
inside one transaction.

## 7. Verify, in this order — do not stop early

a. `docker compose ps` — `api` healthy, `worker` up, and **no restart counter climbing**. A loop
   with `MissingSecretKeyError` in the log means step 5 did not take effect.

b. `docker compose exec -T db psql -U rhapto -d rhapto -c "SELECT version_num FROM alembic_version;"`
   → `0010`. If it still says `0009`, the migration failed — read the api log for the
   `refusing to add UNIQUE(...)` message, which names the offending rows; the database is
   untouched.

c. The constraints actually exist:

```bash
docker compose exec -T db psql -U rhapto -d rhapto -c "\d applications" | grep uq_
docker compose exec -T db psql -U rhapto -d rhapto -c "\d watchlist"    | grep uq_
docker compose exec -T db psql -U rhapto -d rhapto -c "\d job_scores"   | grep -E 'uq_|_key'
docker compose exec -T db psql -U rhapto -d rhapto -c "\d packages"     | grep -E 'uq_|_key'
```

   Expect all four `uq_*` present, and `job_scores_job_id_track_id_key` /
   `packages_job_id_version_key` **gone**. This is the check that catches the migration's silent
   no-op case from step 3.

d. `docker compose logs --tail 80 api worker` — no `MissingSecretKeyError`, no traceback.

e. **Decryption proof — the step that validates step 5.** Open the web app's Settings page: the
   saved provider key must still show as configured. Then run one tailor against an existing job
   and let it complete. A `KeyUnreadableError` ("stored key cannot be decrypted; RHAPTO_SECRET_KEY
   changed") in the api or worker log means the key in step 5 is wrong — **go to rollback, do not
   re-enter keys yet**, because the correct key may still be recoverable from the token.

f. `curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/dashboard` and diff
   against `/root/dashboard-pre-0010.json`. Counts should match (the `needs_review_count` join fix
   only changes behaviour when a *second* user's application exists, which it does not today).

## 8. Post-deploy rescore

Existing jobs still carry the old location penalty. Trigger a rescore:

```bash
curl -sH "Authorization: Bearer $TOKEN" http://127.0.0.1:8000/api/v1/profile/answers > /tmp/answers.json
curl -sX PUT -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
     --data @/tmp/answers.json http://127.0.0.1:8000/api/v1/profile/answers
docker compose logs -f worker            # watch rescore_jobs finish across all 1,430 jobs
```

Re-saving the identical answers enqueues `rescore_jobs`. It commits per chunk, so an interruption
keeps its progress. Spot-check a few `country`-tier jobs afterwards: their fit should have risen by
roughly 1/0.85.

## 9. Rollback — on any failure in step 6 or 7

```bash
cd /opt/rhapto
docker compose stop api worker
docker compose exec -T db psql -U rhapto -d rhapto -c "SELECT version_num FROM alembic_version;"
# if it reports 0010, step the schema back BEFORE the old image starts:
docker compose run --rm api alembic downgrade 0009
cp /root/.env.pre-0010 /opt/rhapto/.env     # restores the blank RHAPTO_SECRET_KEY
git checkout 9452716                        # previous main
docker compose build api worker web
docker compose up -d
docker compose exec -T db psql -U rhapto -d rhapto -c "SELECT version_num FROM alembic_version;"  # expect 0009
```

`downgrade()` is present and reverses in the opposite order of `upgrade()`, verified by QA against
a real database.

Restoring the `.env` copy is what makes this rollback safe for credentials: the old code derives
the Fernet key from `RHAPTO_API_TOKEN` again, and the ciphertext itself was never rewritten, so
provider keys decrypt exactly as before. Nothing is lost either way — which is also the proof that
step 5, done correctly, is a no-op on the data.

If the schema is *damaged* rather than merely ahead, restore step 2's dump instead of downgrading:

```bash
docker compose stop api worker
docker compose exec -T db dropdb   -U rhapto rhapto
docker compose exec -T db createdb -U rhapto rhapto
cat /root/rhapto-pre-0010-<timestamp>.dump | docker compose exec -T db \
  pg_restore -U rhapto -d rhapto --no-owner --no-privileges
```

then bring the old images up as above.
