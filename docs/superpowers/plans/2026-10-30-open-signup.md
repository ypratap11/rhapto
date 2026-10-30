# Open Sign-up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let anyone who passes Cloudflare Access sign in to the hosted instance, give each account 5 free runs in total, and stop all free runs once the deployment key has spent a monthly dollar budget.

**Architecture:** One new flag (`RHAPTO_OPEN_SIGNUP`) bypasses the app's email allowlist in access mode. Every model call billed to the deployment key is wrapped by a metering provider that appends one row per call to a new, never-deleted `free_spend` ledger. A new gate (`check_free_budget`) sums this calendar month's ledger before every deployment-key run and refuses with a distinct 409 when the sum has reached `RHAPTO_MONTHLY_FREE_BUDGET_USD`.

**Tech Stack:** FastAPI, SQLAlchemy async + Alembic (Postgres), arq worker, pytest; Next.js/React + Vitest on the web side.

**Spec:** Approved in chat on 2026-10-30 (no separate design doc). The owner's decisions are: open to everyone; 5 runs per account in total (lifetime, existing behaviour); an app-wide monthly cap of **$50**; and free runs pause for everyone, with a plain message, when the cap is reached.

## Global Constraints

- `RHAPTO_OPEN_SIGNUP: bool = False`. It only has effect when `rhapto_auth_mode == "access"`. The lifespan's existing allowlist checks are unchanged, so the owner must stay on `RHAPTO_ALLOWED_EMAILS`.
- `RHAPTO_MONTHLY_FREE_BUDGET_USD: float = -1`. A negative value disables the budget, which keeps self-hosters and e2e stacks unchanged. `0` refuses every deployment-key run. The owner's production value is `50`.
- `RHAPTO_TRIAL_RUNS=5` is configuration only. No code changes for it.
- The month is the UTC calendar month: `created_at >= date_trunc('month', now(), 'UTC')` (three-argument form, independent of session timezone).
- A ledger write that raises is logged (user id only) and swallowed; the model result is still returned. Rationale: the DB failing breaks the run anyway, and the Anthropic Console spend limit is the backstop (runbook step 2).
- Plan review: `.superpowers/sdd/open-signup/architecture-plan-review.md` (APPROVED WITH CONDITIONS; I1-I6 folded in below).
- The refusal sentence, exact copy: `Free runs are paused until the 1st of next month. Add your own provider API key in Settings to keep going.`
- The 409 problem `code` is `free_runs_paused`. The body must carry no provider id, model id, key fragment, env var name, dollar amount or spend figure.
- When a call's model has no price, the ledger records the cost at the **highest** input and highest output rate in `MODEL_RATES` (conservative, accepted even for e.g. gpt-5 billed at Opus rates). It must never record `0` or `NULL`.
- A billed call that fails with `MalformedOutputError` is metered too: the response's usage travels on the exception.
- Ledger rows are written only for calls billed to the deployment key. Own-key users, token mode and the fake provider write nothing.
- The ledger is append-only. There is no FK cascade to `users`, so `user_id` is a plain UUID column with no foreign key, and deleting a user or job does not lower the month's spend.
- No logging of emails. Logs may carry user ids and counts only (see `services/trial.py` docstring).

## Review Focus

1. **A run that fails after its first model call, or whose every call returns malformed output.** Every billed call must be in the ledger. Tests: `test_calls_before_a_failure_are_still_metered`, `test_a_malformed_call_is_metered_then_reraised` (Task 3).
2. **Deleting a job or package must not refund spend.** Test: `test_deleting_a_job_does_not_lower_the_month_spend` (Task 4).
3. **Last month's spend must not count.** Test: `test_spend_from_last_month_does_not_count` (Task 2).
4. **An own-key user on a deployment whose budget is exhausted still runs.** Test: `test_own_key_user_is_not_paused` (Task 4).
5. **An unpriced model must not slip past the cap as free.** Test: `test_unpriced_model_is_recorded_at_the_highest_rate` (Task 3).

---

### Task 1: Open sign-up flag

**Files:**
- Modify: `apps/api/src/rhapto/config.py` (next to `rhapto_allowed_email_domains`)
- Modify: `apps/api/src/rhapto/api/deps.py:126` (the `is_allowed_email` check in `current_user`)
- Test: `apps/api/tests/api/test_access_mode.py`

**Interfaces:**
- Produces: `Settings.rhapto_open_signup: bool`.

- [ ] **Step 1: Write failing tests** in `test_access_mode.py`, reusing the existing signed-assertion fixtures (see `test_non_allowlisted_email_gets_403_and_no_account`):
  - `test_open_signup_admits_an_unlisted_email_and_creates_its_account`: with `rhapto_open_signup=True` and an unlisted email, `GET /api/v1/me` returns 200 and exactly one `users` row exists for that email.
  - `test_open_signup_off_still_refuses_an_unlisted_email`: with the default value, the same request returns 403 and no row.
  - `test_open_signup_still_requires_a_valid_assertion`: with the flag on and no or invalid `Cf-Access-Jwt-Assertion`, the request returns 401, the same as today.
- [ ] **Step 2:** Run `cd apps/api && uv run pytest tests/api/test_access_mode.py -q`. Expected: the two new admit/refuse tests fail.
- [ ] **Step 3:** Add `rhapto_open_signup: bool = False` to `Settings`, with a comment saying Cloudflare Access is then the only gate. Change the check to `if not settings.rhapto_open_signup and not is_allowed_email(...)`.
- [ ] **Step 4:** Run the test file. Expected: all pass. Run `uv run pytest tests/api -q -k "access or auth"`. Expected: all pass.
- [ ] **Step 5: Commit** `feat(auth): RHAPTO_OPEN_SIGNUP admits any Access-verified email`

### Task 2: Free-spend ledger (table, migration, repository)

**Files:**
- Modify: `apps/api/src/rhapto/db/models.py` (new model `FreeSpend`)
- Create: `apps/api/alembic/versions/0015_free_spend.py` (revision `"0015"`, down_revision `"0014"`, docstring in 0014's style)
- Create: `apps/api/src/rhapto/db/repositories/free_spend.py`
- Test: `apps/api/tests/db/test_free_spend_repo.py`

**Interfaces:**
- Produces:
  - Table `free_spend`: `id uuid pk`, `user_id uuid not null` (no FK, indexed), `created_at timestamptz not null default now()` (indexed), `model varchar(60) not null`, `input_tokens`, `output_tokens`, `cache_read_tokens` and `cache_creation_tokens` as `int not null default 0`, `cost_usd numeric(12,6) not null` with `CHECK (cost_usd >= 0)`.
  - `async def record_free_spend(session: AsyncSession, *, user_id: uuid.UUID, model: str, usage: TokenUsage, cost_usd: Decimal) -> None`, which adds a row and leaves the commit to the caller.
  - `async def month_free_spend(session: AsyncSession) -> Decimal`, which returns this UTC month's sum across all users and `Decimal(0)` when the table is empty.

- [ ] **Step 1: Write failing tests:**
  - `test_month_spend_is_zero_when_empty`: `assert await month_free_spend(s) == Decimal(0)`.
  - `test_month_spend_sums_all_users`: two users with rows of 0.10 and 0.25 give `Decimal("0.35")`.
  - `test_spend_from_last_month_does_not_count`: one row with `created_at` set to the first day of the current UTC month minus 1 second, plus one row of 0.05 now, gives `Decimal("0.05")`.
- [ ] **Step 2:** Run `uv run pytest tests/db/test_free_spend_repo.py -q`. Expected: fails on import.
- [ ] **Step 3:** Implement the model, the migration (downgrade drops the table, and the docstring says the downgrade loses the ledger) and both functions. The month boundary goes in SQL as in Global Constraints, not in Python.
- [ ] **Step 4:** Run the tests and `uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head` against the test database. Expected: tests pass and the migration round-trips.
- [ ] **Step 5: Commit** `feat(db): free_spend ledger for deployment-key model calls`

### Task 3: Metering provider and wiring

**Files:**
- Create: `apps/api/src/rhapto/services/free_spend.py`
- Modify: `apps/api/src/rhapto/services/pricing.py` (add `conservative_cost`)
- Modify: `apps/api/src/rhapto/engine/providers/llm.py` (`MalformedOutputError` gains `usage: TokenUsage | None = None`) and the three adapters `anthropic.py`, `openai.py`, `gemini.py` (pass the response usage wherever they raise `MalformedOutputError` after a response arrived)
- Modify: `apps/api/src/rhapto/worker/tasks.py` (around line 228, right after `llm = await resolver(...)`)
- Modify: `apps/api/src/rhapto/api/routers/profile.py:350` (import endpoint)
- Test: `apps/api/tests/unit/test_free_spend_meter.py`, `apps/api/tests/api/test_free_spend_wiring.py`

**Interfaces:**
- Consumes: `record_free_spend` (Task 2), `on_deployment_key` and `deployment_key_trial_limit` logic (`services/trial.py`), `env_llm_config` (`services/llm.py`), `estimate_cost` (`services/pricing.py`).
- Produces:
  - `def conservative_cost(model: str | None, usage: TokenUsage) -> Decimal`, which returns `estimate_cost(...)` when not None and otherwise prices the usage at `max(input_per_million)` and `max(output_per_million)` across `MODEL_RATES`, using the same cache multipliers.
  - `class MeteredLLM` (implements `LLMProvider`): `__init__(self, inner: LLMProvider, *, model: str, user_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession])`. It exposes `self.model = model`, because `engine/pipeline.py:160` reads `getattr(llm, "model")` into `packages.llm_model`. It delegates `complete_structured`. After each call that returns, it opens its own session, calls `record_free_spend` with `conservative_cost(model, result.usage)` and commits. A `MalformedOutputError` whose `usage` is not None is recorded the same way and then re-raised unchanged. Any other exception records nothing.
  - `async def meter_if_free(llm: LLMProvider, session: AsyncSession, settings: Settings, user_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]) -> LLMProvider`. This returns `MeteredLLM(llm, model=getattr(llm, "model", None) or env_llm_config(settings).model, ...)` when `free_budget_applies(settings)` and `await on_deployment_key(session, settings, user_id)`, and otherwise returns `llm` unchanged.
  - `def free_budget_applies(settings: Settings) -> bool` (lives in `services/trial.py`). It is True only when auth mode is access, the provider is not the fake (mirror exemption 2 in `deployment_key_trial_limit`), `env_llm_config(settings)` is not None, and `rhapto_monthly_free_budget_usd >= 0`. Metering is skipped when the budget is disabled, because nothing reads it then. Add `rhapto_monthly_free_budget_usd: float = -1` to `Settings` here, with a comment matching `rhapto_trial_runs`'s style.

- [ ] **Step 1: Write failing unit tests** (`test_free_spend_meter.py`, using `FakeLLMProvider` as the inner provider):
  - `test_each_returned_call_writes_one_row`: two calls give two rows with the inner provider's token counts.
  - `test_unpriced_model_is_recorded_at_the_highest_rate`: model `"mystery-1"` with 1,000,000 input tokens records `cost_usd == max input rate in MODEL_RATES`.
  - `test_a_raising_call_writes_nothing`: an inner provider that raises `RuntimeError` leaves 0 rows, and the exception propagates unchanged.
  - `test_a_malformed_call_is_metered_then_reraised`: an inner provider raising `MalformedOutputError(..., usage=TokenUsage(input_tokens=1000))` gives 1 row with 1000 input tokens, and the same exception propagates.
  - `test_metered_llm_exposes_the_model`: `MeteredLLM(inner, model="claude-opus-5", ...).model == "claude-opus-5"`.
  - One test per adapter (in the existing adapter test files) asserting the raised `MalformedOutputError.usage` matches the mocked response's usage.
- [ ] **Step 2: Write failing API/worker tests** (`test_free_spend_wiring.py`, using `test_trial_limit_api.py`'s access-mode setup and fake script helpers):
  - `test_a_free_tailor_run_writes_ledger_rows`: one rows per model call made in the run, with `model` equal to the env model.
  - `test_calls_before_a_failure_are_still_metered`: the script makes the first call succeed and the second raise `MalformedOutputError` twice, so the task fails. Ledger rows are at least 1.
  - `test_a_free_import_writes_ledger_rows`: `POST` import of `build_fixture_docx()` gives ≥1 row.
  - `test_own_key_runs_write_nothing`: after `upsert_llm_settings` with a different key, a run writes 0 rows.
  - `test_budget_disabled_writes_nothing`: with `rhapto_monthly_free_budget_usd=-1`, 0 rows.
- [ ] **Step 3:** Run both files. Expected: fail.
- [ ] **Step 4:** Implement the pieces above. In the worker, wrap right after the resolver returns, using the worker's `factory`. In `import_resume_endpoint`, wrap after `resolve_llm`, using `get_state(request).session_factory` (`api/deps.py:33`). Add `request: Request` to the endpoint signature if it isn't there.
- [ ] **Step 5:** Run both files plus `uv run pytest tests/api/test_trial_limit_api.py tests/api/test_trial_limit_worker.py tests/api/test_import_resume_api.py -q`. Expected: all pass.
- [ ] **Step 6: Commit** `feat(trial): meter every deployment-key model call into free_spend`

### Task 4: Monthly budget gate

**Files:**
- Modify: `apps/api/src/rhapto/services/trial.py`
- Modify: `apps/api/src/rhapto/api/errors.py` (handler next to `_trial_limit`)
- Modify: `apps/api/src/rhapto/worker/tasks.py:66` (`SETUP_ERRORS`)
- Test: `apps/api/tests/api/test_free_budget_api.py`

**Interfaces:**
- Consumes: `month_free_spend` (Task 2), `free_budget_applies` and `on_deployment_key` (Task 3 and existing).
- Produces:
  - `FREE_RUNS_PAUSED_MESSAGE: str` (the exact copy from Global Constraints).
  - `class FreeRunsPausedError(Exception)`, whose message is `FREE_RUNS_PAUSED_MESSAGE`.
  - `async def check_free_budget(session: AsyncSession, settings: Settings, user_id: uuid.UUID) -> None`. It raises when `free_budget_applies(settings)`, the user is on the deployment key, and `await month_free_spend(session) >= Decimal(str(settings.rhapto_monthly_free_budget_usd))`.
  - Call sites. `check_free_budget` does its own `on_deployment_key` check, so own-key users pass through, and it runs even when the trial cap is disabled.
    - `consume_trial_run` and `claim_import_allowance`: the **first** statement, before `trial_limit_for`, so a refusal consumes neither a run nor the free import.
    - `check_trial_allowance`: the existing trial-limit check stays first, so an exhausted account still hears its own sentence. `check_free_budget` comes after it.
    - `worker/tasks.py` `tailor_job`: also call `check_free_budget` **unconditionally**, just before the `if not active_task.progress_json.get("trial_claimed")` block (tasks.py:279). An arq re-delivery skips `consume_trial_run`, but it must not skip the budget.
  - The 409 problem has `code="free_runs_paused"` and no extra fields. `FreeRunsPausedError` is added to `SETUP_ERRORS`, so a worker refusal marks the task failed with the sentence, the same as the trial limit.

- [ ] **Step 1: Write failing tests:**
  - `test_tailor_is_refused_with_409_once_the_month_budget_is_spent`: set the budget to 1.00 and seed one ledger row of 1.00. `POST` tailor returns 409, `code == "free_runs_paused"`, and the `detail` equals the exact sentence.
  - `test_import_is_refused_once_the_month_budget_is_spent`: the same, for the import endpoint, and no `free_import_used_at` is consumed.
  - `test_worker_refuses_when_budget_ran_out_after_enqueue`: enqueue while under budget, seed spend over budget, run the worker. The task fails with the sentence, and `trial_runs_used` is unchanged.
  - `test_own_key_user_is_not_paused`: budget spent, user with own key, tailor returns 202 or 200 (whatever the current success code is).
  - `test_deleting_a_job_does_not_lower_the_month_spend`: run once, read `month_free_spend`, `DELETE /jobs/{id}`, and the sum is unchanged.
  - `test_worker_redelivery_still_checks_the_budget`: a task whose `progress_json` already has `trial_claimed: True`, with spend over budget, fails with the sentence and makes no model call.
  - `test_the_pause_leaks_nothing`: the full body contains no env model id, provider id, `"RHAPTO_"` or `"$"`. The `detail` field contains no digit other than the `1` in "1st". (The body's `"status": 409` is expected, so don't check digits there.)
  - `test_budget_disabled_never_pauses`: budget `-1` with a large seeded spend still allows the run.
- [ ] **Step 2:** Run `uv run pytest tests/api/test_free_budget_api.py -q`. Expected: fail.
- [ ] **Step 3:** Implement the above.
- [ ] **Step 4:** Run the file, then the whole API suite: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src`. Expected: all green.
- [ ] **Step 5: Commit** `feat(trial): pause free runs when the monthly budget is spent`

### Task 5: Web copy, public links and owner runbook

**Files:**
- Modify: `apps/web/src/lib/coach/errors.ts` (add the sentence to `SETTINGS_SENTENCES`, plus a `free_runs_paused` branch next to `trial_limit_reached`)
- Modify: `apps/web/Dockerfile` and `docker-compose.yml` (a new build arg `NEXT_PUBLIC_OPEN_SIGNUP`, sourced from `${RHAPTO_OPEN_SIGNUP-false}` exactly as `NEXT_PUBLIC_TRIAL_RUNS` is sourced from `RHAPTO_TRIAL_RUNS`, docker-compose.yml:99-101)
- Modify: `apps/web/src/components/landing/access.ts` (add `export function openSignup(): boolean`, true only when `process.env.NEXT_PUBLIC_OPEN_SIGNUP === "true"`, following `copy.ts`'s reader)
- Modify: `apps/web/src/components/landing/Landing.tsx`, `apps/web/src/components/shell/Footer.tsx`, `apps/web/src/components/shell/TopBar.tsx` (when `openSignup()`, hide the "Request beta access" link, and on the landing page hide the whole "No invite yet?" line around it)
- Create: `docs/runbook-open-signup.md`
- Test: the existing `*.test.tsx` next to each of these files, plus `apps/web/src/lib/coach/errors.test.ts`

**Interfaces:**
- Consumes: the 409 `code="free_runs_paused"` and the exact sentence (Task 4).

- [ ] **Step 1: Write failing tests:**
  - errors: `describeCoachError(new ApiError(409, {code: "free_runs_paused", detail: SENTENCE}), "tailor")` returns `{ message: SENTENCE, next: "settings", link: SETTINGS_LINK }`. With an unknown detail it falls back to the same sentence. It never shows the raw detail.
  - Landing, Footer and TopBar: with `NEXT_PUBLIC_OPEN_SIGNUP="true"` stubbed, there is no link named /request beta access/i and no "No invite yet?" text. The primary CTA "Tailor my resume" → `/start` is still present. With the variable unset, the existing request link renders as today.
  - Keep `TokenGate`'s and the coach 403 "invite-only" copy unchanged. That is the correct message if the server flag is off.
- [ ] **Step 2:** Run `cd apps/web && pnpm vitest run src/lib/coach src/components/landing src/components/shell`. Expected: the new tests fail.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `pnpm vitest run`, `pnpm lint` and `pnpm typecheck`. Expected: green.
- [ ] **Step 5:** Write `docs/runbook-open-signup.md` with these exact steps in order:
  1. Back up: confirm `/usr/local/sbin/rhapto-backup.sh` exists, then run it and check `/var/log/rhapto-backup.log`.
  2. Anthropic Console: confirm the server's `ANTHROPIC_API_KEY` belongs to the workspace holding the Max-plan credit, and set that workspace's monthly spend limit at or slightly above the app cap.
  3. In `/opt/rhapto/.env`: `RHAPTO_OPEN_SIGNUP=true`, `RHAPTO_TRIAL_RUNS=5`, `RHAPTO_MONTHLY_FREE_BUDGET_USD=50`. Keep `RHAPTO_ALLOWED_EMAILS` (the lifespan requires it, and it must include the owner).
  4. Edit `.env` **before** deploying (the web build bakes in `RHAPTO_TRIAL_RUNS` and `RHAPTO_OPEN_SIGNUP`). Then deploy from an up-to-date main with `scripts/deploy-server.sh api worker web` (the owner runs it with `!`). With no arguments the script rebuilds only the web. The rebuilt api runs migration 0015 on start. Confirm with `SELECT version_num FROM alembic_version;` → `0015`.
  5. Verify inside the api container with `printenv` that the three values are set, without printing emails.
  6. Cloudflare Zero Trust: change the Rhapto application's Access policy Include to **Everyone**, with One-time PIN enabled as a login method. Note the Zero Trust Free plan's **50-user seat limit**: check the seat count in Zero Trust → Users, and remove inactive users or upgrade before it fills.
  7. Smoke test as a visitor in a private window with an address that isn't on the list: sign in, reach `/start`, and see the 5-run allowance.
  8. Rollback: set `RHAPTO_OPEN_SIGNUP=false`, recreate the api container, and restore the Access policy's email list.
  9. Check the month's spend: run a one-line SQL query in the db container, `SELECT sum(cost_usd) FROM free_spend WHERE created_at >= date_trunc('month', now(), 'UTC');`.
  10. Watch for abuse: run `SELECT user_id, count(*), sum(cost_usd) FROM free_spend WHERE created_at >= date_trunc('month', now(), 'UTC') GROUP BY user_id ORDER BY 3 DESC LIMIT 10;`. Look for many new accounts that share a mailbox, for example `name+1@`, `name+2@`. To respond, set those accounts' `trial_runs_used` to the cap (`UPDATE users SET trial_runs_used = 5 WHERE id IN (...)`) and remove their Cloudflare seats.
- [ ] **Step 6: Commit** `feat(web): open sign-up copy and free-runs-paused message; runbook`
