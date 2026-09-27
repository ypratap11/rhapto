# Bounded trial on the maintainer's key — deferrals and recorded findings

Written at the end of the trial-runs implementation run (spec and architecture under
`.superpowers/sdd/2026-09-27-trial-runs/`, full task report in the same directory). Everything here
was found or decided during that run and left deliberately undone. None of it is a known-broken
promise to a user except item 1, which is a promise the landing page has been making since
2026-09-26 and which is **still being made** — it needs the owner's wording before it can be fixed.

## 1. The landing page still tells invited users they pay for their own usage (architecture C3)

`apps/web/src/components/landing/Landing.tsx:225-228`, in the "Wherever you run it" panel:

> Either way you bring your own LLM key and pay only your own usage.

True for a self-hoster. **False for an invited user who never adds a key** — they spend the
deployment's key and the maintainer pays. It is the same class of defect the panel's own comment
records having shipped once before: a claim that is only true for half the readers.

**Decision: deferred, deliberately, to the owner.** Condition C3 routes the wording to him rather
than to the implementer, and it is not an implementation detail — three constraints have to hold at
once:

1. True for the self-hoster, for whom there is no trial and no cap at all (token mode is exempt), so
   it cannot become "three free runs, then bring your own key".
2. True for the invited user, who may spend the maintainer's key for a bounded number of runs.
3. It must not hard-code "three". `RHAPTO_TRIAL_RUNS` is the operator's knob: `3` by default, `0`
   means "no free runs at all", negative means "no cap". A page promising three runs is a promise a
   self-hoster with `RHAPTO_TRIAL_RUNS=0` cannot keep — the same defect again.

Proposed replacement (the full set of options is in the task report; this is the one recommended):

> Your provider key is yours, and the only usage you ever pay for is your own. If you have been
> invited onto someone else's instance, they choose whether to lend you a few runs on their key to
> start with; once those are used, you add your own key in Settings.

**Whatever is chosen touches two files together.** `Landing.test.tsx:104` currently asserts the false
sentence (`expect(block).toMatch(/you bring your own LLM key and pay only your own usage/i)`) and will
fail the moment the copy changes. It must assert the new clause, not be deleted: that assertion block
exists because a half-true claim shipped here once before.

## 2. `PUT /settings/llm` may already hold a stored copy of the deployment's key

`_key_for_write` used to fall back to the environment, so any user who pressed Save on the LLM form
without typing a key had the maintainer's key encrypted into their own `llm_settings` row. That write
path is closed (C1), and `services/trial.py`'s `same_key` recognises an existing copy as the
deployment's key so the cap still applies to whoever holds one.

What is **not** done is cleaning up a row that already exists. Before deploying, check the live
`llm_settings` table: if the second account has a row, compare its decrypted key against
`ANTHROPIC_API_KEY`. If they match, the row is a copy of the maintainer's key and should be deleted,
not kept — the user would otherwise see "your key is set" for a key that is not theirs.

## 3. `PATCH /packages/{id}` inherits the parent's token usage (pre-existing)

Found by the architect in passing (architecture §1.2a), outside this change's scope, and left alone.

`patch_package`'s `model_copy(update=...)` resets `llm_calls` to 0 but does not reset `usage`, so a
PATCH-created row inherits the parent's `input_tokens`/`output_tokens` and
`db/repositories/packages.py::usage_by_model` double-counts them in the Settings usage figure and its
cost estimate. Every human edit in the review queue inflates the reported spend.

Unrelated to the trial cap, which does not read `packages` at all.

## 4. `ProviderAuthError` relays the maintainer's own provider-account message

Also pre-existing, and made materially worse by this change — not by the code, but by the fact that
the trial is what turns invited strangers into legitimate users of these endpoints.

`ProviderAuthError` is in `worker/tasks.py`'s `SETUP_ERRORS`, so the provider's own sentence is shown
to the user. When the **maintainer's** key hits a spent balance, an invited user reads the vendor's
message about the maintainer's account ("your credit balance is too low…"). The key itself is
redacted; the account's billing state is not.

## 5. `Settings` has no `groq_api_key` or `openrouter_api_key`

`env_llm_config` derives its field name from `ProviderInfo.env_key.lower()`, and `config.py` has no
field for either, so `RHAPTO_LLM_PROVIDER=groq` / `openrouter` can never resolve from the
environment — only from a stored per-user key. The registry advertises five providers; the env path
supports three plus the fake. The architecture explicitly said not to "fix" this inside the trial
change. Recorded so the next person does not rediscover it from a confusing bug report.

## 6. The local dev database is behind

`postgresql://rhapto@localhost:5432/rhapto` was at revision **0010** when this work started — two
behind, so `0011` had never been applied to it either. It was left alone: bringing it forward runs
0011's `seeded_at` backfill against local data for no benefit to this task. Run
`alembic upgrade head` there before running the app locally. Unrelated to this change, and unrelated
to production, which is at `0011` and needs `0012` — **the owner is asked before any production
migration, every time.**
