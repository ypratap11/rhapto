# Completeness Guardrail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Revision 2026-09-29 (senior developer, role 3) — READ THIS FIRST

This revision answers `.superpowers/sdd/completeness-guardrail/plan-review.md` (verdict: NOT SAFE TO EXECUTE, 4 Critical, 5 Important, 6 Minor) and applies the owner's decision on C-2 (2026-09-29): **Option 2 — keep the completeness clauses strict and change `profile.example`.**

**How this revision was verified (do not re-derive it, but do re-run it).** Every path, line, test name and signature below was re-checked against `main` = `d96015a`, not carried over from the 2026-09-25 plan. Every code block and unified diff in this document was then *applied* to a scratch worktree of `d96015a`, one commit per task, in the order Task 1b → 1 → 2 → 3 → 4 → 5. At every one of those six commits `ruff format --check .`, `ruff check .` and `mypy` were clean and the scoped suite (`tests/unit tests/guardrails tests/golden tests/api/test_guardrail_remedies.py`) was green: 644, 671, 675, 676, 681, 688 passed (97 skipped: DB tests, no Postgres here). Those runs used a temporary `apps/api/.env` holding a Fernet `RHAPTO_SECRET_KEY` (so `test_cli.py`'s nine environment failures could not mask anything) and deselected `test_config.py::test_get_settings_requires_a_secret_key` (which that same `.env` breaks). After the last commit the whole `apps/api` suite ran the same way: 708 passed, 494 skipped, and the only failures were the two Postgres-less migration tests from "Local baseline" below plus the deliberately-broken `test_config` one. `lint-imports` kept all 6 contracts. Web: `vitest` on `GuardrailPanel.test.tsx` 8 passed, `tsc --noEmit` and `eslint src/components/review` clean. The diffs are exactly what those commits contain. They are indented two spaces to sit under their list items: dedent before `git apply`, or transcribe. As a last check this file itself was round-tripped: all 11 diffs and all 5 new-file blocks were extracted from it, applied in document order to a clean checkout of `main`, and the result matched the verified final commit exactly.

### Review findings → where resolved

| Finding | Resolution | Where |
|---|---|---|
| **C-1** wiring breaks `test_registry.py` | `tests/guardrails/test_registry.py` added to Task 1's Files; the two `rules_run` assertions changed. **Current numbers differ from the review's**: `main` has since made `no-unverified-metrics` unconditional, so the assertions are at lines 23 and 48 (not 16/25) and the expected list is now `["provenance", "no-unverified-metrics", "completeness"]`. The false Step-8 claim is deleted. | Task 1 Step 6, Files |
| **C-2** fake provider cannot satisfy the rule | Owner Option 2. New **Task 1b** (executes *before* Task 1; green on its own): `profile.example/blocks.yaml` gains a usable role on `side-llm-tool` and loses the digits from its content; `cred-pmp` becomes `verified: true`. No fake-provider *code* change is needed (docstring only). Two proof tests added, one of them a known-bad input that must block. | Task 1b, Task 1 Step 6 |
| **C-3** `ghost` test cannot pass | Selection is now only `["ghost-not-in-library"]`. | `test_selection_id_not_in_block_map_is_skipped_not_raised` |
| **C-4** `_describe` is a mypy-strict error | `[p for p in (block.org, block.role) if p and p.strip()]`. `mypy` verified clean at every task commit. | `completeness.py` `_describe` |
| **I-1** attribution narrowing rests on a false premise | The gap is added only when the phrase is absent from the same joined text `check_attribution` builds. **Deliberate tightening beyond the review's snippet:** it is also added only when the entry has no bullet text. With a bullet present and the phrase missing, `attribution` already errors; a second `completeness` error would break C7 (one violation per defect). Two new tests pin both edges. | `_attribution_unreachable`, Task 1 Step 5 |
| **I-2** `ruff format --check` red | Every Python block below is `ruff format` output (verified `--check` clean at each commit), and **every task now has an explicit `ruff format .` step before its gate**. | each task's "Format and gate" step |
| **I-3** `summarize_run` mis-measures C6 | `TailorResult` gains `pre_repair_report: GuardrailReport \| None` and `repaired: bool` (Task 2). Task 5's helper is rewritten to read them instead of `llm_calls`; the malformed-retry shape (3 calls, `draft`, no repair) has its own regression test in Task 2 and Task 5. | Task 2 Step 3, Task 5 |
| **I-4** no `date-consistency` test | Three tests: an overlapping non-`concurrent` side role, once restored, yields exactly one `date-consistency` error and no `completeness` error; the same role flagged `concurrent: true` is clean; dropping it is now a `completeness` error. | `test_completeness.py` |
| **I-5** CLI message wrong after Task 4 | Reworded; `cli/main.py` added to Task 4's Files; `test_tailor_blocked_exits_3` asserts the message and that `resume.docx` is absent. | Task 4 |
| M-1 | `_org_appears_in_entry_text` is a whole-word match (`"Independent"` no longer lights up `"independently"`); one test. | Task 1 |
| M-2 | One comment on the asymmetry of `_org_matches`. | Task 1 |
| M-3 | Moot: the dead-click rule is now the `selection.` prefix only, so `cover_note`, `summary[..]` and tune `edits[..]` stay clickable (see D-3). | Task 3 |
| M-4 | `--provider` validated with `parser.error`. | Task 5 |
| M-5 | Carried forward as a coder note and an unresolved risk (U-1); for `profile.example` it disappears (the block now has a role). | Task 1 Step 5, U-1 |
| M-6 | Architecture line numbers are stale (`registry.py:130-157`, `repair.py:388`, `attribution.py:226-235`); this plan's own citations were re-verified against `d96015a` instead. | throughout |

### Drift since 2026-09-25 (found by re-verifying; none of these is in the review)

- **D-1 `no-unverified-metrics` is now unconditional** (`registry.py`, commit `d94b98d`). `rules_run` starts as `[PROVENANCE, METRICS]`, and the old plan's `[PROVENANCE, COMPLETENESS]` edit would have been made against code that no longer exists. Completeness is wired third, after metrics, so `violations[0].rule == "provenance"` in `test_registry.py` still holds.
- **D-2 A remedy is now mandatory for every rule.** `REMEDIES` in `registry.py` plus `tests/api/test_guardrail_remedies.py::test_every_rule_has_a_remedy` walk the package for `RULE_NAME` constants, and `test_the_six_rules_this_build_ships_are_the_ones_expected` pins the set. A `completeness.py` without a remedy fails that test the moment the file exists. Task 1 adds the remedy and renames the pin to seven (`tests/api/` holds these tests but they are pure functions and run locally).
- **D-3 `GuardrailPanel.tsx` has changed since the plan was written.** It now renders `severity`, `block_id`, a per-rule `remedy`, and takes a `remedies` prop; the old Task 3 replacement block would have silently deleted all of it. Worse, its `startsWith("sections[")` rule would have de-linked every tune-mode violation (`edits[i]`), which the review page routes through `scrollToChange` and the job page routes through `?path=`. Task 3 is rewritten as a three-hunk edit against the current file that only special-cases the one synthetic prefix, with a test for the paths that must stay clickable.
- **D-4 Line references moved.** `tailor()`'s repair block, `_edited_blocks_version` (`packages.py:213-226`), `cli/main.py:183-185`, `test_packages_api.py:102-111`, `test_pipeline.py:148-168`. All re-read.
- **D-5 The tune branch has the same unguarded `budget.before_call()`.** The old plan mentioned it in one sentence with no code and no test. Task 2 now guards it, with a test.
- **D-6 CI now exists** (`.github/workflows/ci.yml`) and changes what "done" means; see "CI facts" below.

### CI facts (apply to every task's gate)

`.github/workflows/ci.yml` runs on **push to `main` and on every pull request**: job `api` (Postgres `pgvector/pgvector:pg16` + Redis 7) runs `ruff check`, `ruff format --check`, `mypy`, `lint-imports`, then the **full** `pytest` with `RHAPTO_TEST_REQUIRE_SERVICES=1` (an unreachable Postgres or Redis *fails* the run instead of skipping) and `--junitxml`; then `.github/scripts/check_skips.py` fails the job on **any** skip other than `test_live_gemini_accepts_every_engine_schema`. Job `web` runs `pnpm typecheck`, `pnpm lint`, `pnpm test`. **CI does not run Playwright e2e.**

Consequences for the coder, stated once so no task report can claim more than it ran:

1. **The laptop has no working Docker.** Locally, every DB/Redis-dependent test skips (97 in the scoped run above, 494 in a full run). A green local run therefore proves the non-DB suites only.
2. **CI is the full gate.** A task is not "verified" for `tests/api` and `tests/db` until CI is green on the pushed commit. Do not push to `main` to find out; open a PR or push a branch (CI also runs on `pull_request`).
3. **Every task report (`task-N-report.md`) must state:** (a) the exact commands run and their results; (b) which suites ran locally and which skipped, by count; (c) that the DB-dependent tests this task touches (named in the task) were **not** executed locally and are covered only by CI; (d) that the local-baseline failures below were observed unchanged.
4. **New tests must not skip.** CI's skip guard fails the job on any new skip. Every test added here is a plain unit test or a DB test that uses existing fixtures; none adds a `skip`/`skipif`.

### Local baseline (`main` = `d96015a`, before any change here; recorded so nobody mistakes it for a regression)

- `tests/unit/test_cli.py`: **9 tests fail** with `MissingSecretKeyError` (no `RHAPTO_SECRET_KEY` in the environment or an `.env` next to `apps/api`; `tests/conftest.py` seeds one, but the CLI tests read `get_settings()` after a fixture removes it). They pass if `apps/api/.env` holds `RHAPTO_SECRET_KEY=<a Fernet key>`; then `tests/unit/test_config.py::test_get_settings_requires_a_secret_key` fails instead. Create that file **only** for a `test_cli.py` run, never commit it, delete it afterwards. Task 4 edits `test_tailor_blocked_exits_3`, which is one of the nine, so its evidence needs this run.
- `tests/db/test_migrations_0011.py::test_0011_backfills_seeded_at_for_pre_existing_rows` and `tests/db/test_migrations_0012.py::test_0012_does_not_backfill_a_pre_existing_account` fail (rather than skip) without Postgres.
- Everything else in `tests/unit`, `tests/guardrails`, `tests/golden` and `tests/api/test_guardrail_remedies.py` is green.

### Execution order and what is *not* resolved

Order: **Step 0 (branch) → Task 1b → 1 → 2 → 3 → 4 → 5.** Task 1b is lettered because review C-2 produced it, but it is a prerequisite of Task 1 and lands first; it is green by itself (its new test fails before the fixture edit and passes after it).

- **U-1 (open risk, not fixable by a fixture).** The project clause requires `title` or `role` on the entry, and *no rule validates an entry's `title`* (architecture §12.2). `profile.example` now carries a role, so the demo is clean, but a real profile's project blocks commonly have no `role`; for those the composer must invent a `title` to satisfy the clause. Checked read-only against the owner's local `profile/` (counts withheld, CLAUDE.md rule 4): this is not hypothetical. Option 2 does not touch it. **Task 5 now builds the instrument** (`invented_project_titles`: project entries whose title or role text is not made of words from the block they cite, one row per model, with a known-bad test that fails without it); if the measurement shows models inventing project titles, architecture §12.2's remedy (invert the clause, extend `no-invented-entities` to `title`) is the follow-up. The instrument is an upper bound (a paraphrase counts) and it measures, it does not block. **Coder note for Task 1:** do not "fix" a project block with no label by fabricating a title in a fixture.
- **U-2 (verification gap).** The e2e claim in review C-2 (`apps/web/e2e/resumes.spec.ts` "Skip archives the resume", which looks for the row under `/resumes?tab=review`, and every spec that tailors on the fake stack) cannot be run here (no Docker) and CI does not run Playwright. What protects it: `test_a_whole_tailor_run_produces_a_clean_package` (API level, runs in CI) now asserts all three mandatory blocks are cited and `completeness` ran, and the unit test in Task 1b proves the fake places every mandatory block. **Role 5 (QA) must run the Playwright suite on a Docker-capable machine before delivery.** No e2e spec asserts block content (`git grep` for the changed strings finds none), so no e2e file needs editing.
- **U-3.** The fake provider still skips a selected role whose period overlaps an earlier one, and any unverified block with a digit. Under this rule either is now a blocked run instead of a silent omission (deliberate, and documented in its docstring); `profile.example` triggers neither.
- **U-4 (behaviour change the owner should know about).** Task 4 means a hand edit that trips *any* rule now yields a package with `has_docx: false`, where before it kept a DOCX "for review". That is the owner's 2026-09-25 decision; the review page already handles `has_docx: false` (tune mode and orphan bullets produced it before). **A second user-visible case (plan-review-2, Minor 2):** in the review UI, removing the *only* bullet of a label-less credential (the demo's `cred-pmp` shape; `removeBullet` is one click) now saves a version that fails `completeness`, and after Task 4 that version has no DOCX. That outcome is correct (`_compact_entry` would render nothing for it), but it is new, so the owner should not first meet it in production. **Stored files:** Task 4 also refuses to *serve* a DOCX/PDF for any package whose report failed, so blocked rows written before Phase 5 stop being downloadable without deleting anything (plan-review-2, I-1); their `has_docx` stays true, so the buttons remain enabled and a click shows a toast carrying the 409's `detail`.

### Revision 2 (2026-09-29, after plan-review-2)

`.superpowers/sdd/completeness-guardrail/plan-review-2.md`: **SAFE WITH FIXES**, 0 Critical, 2 Important, 5 Minor. It also re-ran every claim of the first revision and found them true. Everything below was applied to a fresh scratch worktree of `main` (`2026039`), one commit per task, with the same gates: `ruff format --check`, `ruff check`, `mypy` clean at every commit; scoped suite 644, 671, 675, 676, 681, 688 passed; full suite and `lint-imports` on the last commit (numbers in the verification paragraph above). Mutations were run against the new tests, and each was killed (listed per item).

| Item | Resolution | Where |
|---|---|---|
| **I-1** blocked packages stored before Phase 5 keep a downloadable DOCX/PDF | A **serve-time gate**, no file deleted. `package_file` answers **409** (with a `detail` saying why) for `resume.docx`/`resume.pdf` when the stored report did not pass; `download_package` passes `include_documents=passed` to `build_zip`, so the blocked zip still downloads (the existing, tested behaviour) but contains no resume document; the zip's `GUARDRAILS-BLOCKED.md` wording no longer says the files are there. **409, not 404, and after the existence check:** the file exists and is being refused, so 404 would lie; a blocked package with no file (everything written since Phase 5) still answers 404, so "nothing was rendered" and "rendered earlier, refused now" stay distinguishable and `test_patch_with_orphan_bullet_has_no_docx`'s 404 still holds. **Web:** `downloadAuthenticated` turns any non-2xx into `ApiError` carrying the problem `detail`, and `PackageActions`/`JobHeader` already toast `e.message`; a 409 with no `code` or `existing_application_id` triggers none of the special 409 handlers in `queries.ts`. No web change. **This also fixes a pinned test both reviews missed:** `test_blocked_package_download_is_unmistakable` asserts `resume.docx` is `200` for a blocked package and would have failed in CI after Task 4. Tests first, including the known-bad case (a blocked package with a DOCX *on disk* must not be served): unit tests that run locally (`package_file` called directly with its two lookups stubbed; `build_zip` against a real temp directory) plus the CI-only HTTP test. Mutations killed: gate removed → both known-bad cases fail; `include_documents` ignored → the zip test fails. | Task 4 |
| **I-2** U-1's mitigation not built | `invented_project_titles(result, blocks)` in `measurement.py`, a field on every measurement row, printed by the script. Known-bad unit test: a run whose project entry carries an invented title is a clean `draft` (no rule validates titles, so this is the blind spot) and the helper must name it; a title copied from its block must not be flagged. Mutation killed: helper returning `[]` fails the known-bad test. | Task 5 |
| **Minor 1** fixture-revert proof is weak | Task 1 Step 8's proof is now the **unwire mutation** (delete the `check_completeness` call from `run_guardrails`): 5 tests fail at Task 1's commit and 10 at the last commit, including the fake-provider trap test. The fixture-revert remains as a second check for the fake-provider tests only. | Task 1 Step 8 |
| **Minor 2** U-4 misses the label-less credential case | Disclosed in U-4 above, and in Task 3 (the task that touches the review UI). | U-4, Task 3 |
| **Minor 3** a duplicate entry is two violations | Decided: a **recorded exception**, not a fix. C7 and AC8 are worded around merge and substitution; a block printed twice overlaps itself, `date-consistency` errors, and suppressing that would mean changing a rule this project does not own (both messages are true). Pinned by `test_a_duplicated_entry_is_reported_by_two_rules_by_design` (exactly one `completeness` error plus `date-consistency`). See Global Constraints. | Task 1, Global Constraints |
| **Minor 4** `rules_run` is not proof of wiring | Stated in Task 1 Step 8: `rules_run` lists `completeness` even if the call is removed, so the two `rules_run` assertions prove nothing about execution. Wiring is proved by behaviour: `test_completeness_cannot_be_switched_off_by_an_empty_guardrails_table`, `test_dropping_that_side_role_is_now_a_completeness_error_not_a_pass`, the fake-provider trap test and, from Task 2, the pipeline and measurement tests (all fail under the unwire mutation). | Task 1 Step 8 |
| **Minor 5** no branch step | **Step 0** added before Task 1b. | Step 0 |

---

**Goal:** Close the silent-omission gap: when the composer's output drops a block that `select_blocks` already chose (role, project, or credential), the run must fail a new, unconditional `completeness` guardrail — repaired automatically once like any other violation, and, if it still fails, blocked with a report naming exactly what vanished. Blocked packages must never persist a DOCX, in any run mode.

**Architecture:** A new deterministic rule module (`engine/guardrails/completeness.py`) reads the same `GuardrailContext` every other rule already reads (`resume`, `blocks`, `selection_ids`) and is wired unconditionally in `registry.run_guardrails`, outside the configurable `RULES` dict, mirroring `provenance` and `no-unverified-metrics`. It detects three shapes of non-appearance (missing/wrong-section/unrenderable-identity) plus duplicates, and annotates a plain "missing" finding with fold/substitution evidence when a block's content appears to have survived inside a different entry. The existing one-shot repair loop is retargeted (its instructions currently say "drop bullets", which is the offence this project exists to catch) and hardened against a latent `LLMBudgetExceeded` crash, and `TailorResult` now keeps the first report so repair success is measurable. `COMPOSE_RULES` gets one added rule so the composer is told up front never to drop an entry. Finally, blocks-mode DOCX rendering — in both the CLI/worker pipeline and the API's hand-edit path — is gated on `report.passed`, closing a gap that today lets a blocked package still produce a real, attachable Word document.

**Tech Stack:** Python 3.12, Pydantic v2, pytest (`pytest-asyncio`, `asyncio_mode = "auto"`), ruff, mypy strict, rapidfuzz; TypeScript/React (Next.js) + Vitest + Testing Library for the one web change.

**Spec:** `.superpowers/sdd/completeness-guardrail/functional-spec.md` (10 acceptance criteria + owner decisions) and `.superpowers/sdd/completeness-guardrail/architecture.md` (APPROVED WITH CONDITIONS C1–C7, including the 2026-09-25 owner confirmation putting Phase 5 in scope). Review: `.superpowers/sdd/completeness-guardrail/plan-review.md`.

## Global Constraints

- **Unconditional, not configurable** (owner decision 1, spec §7.1 / architecture §11 C4): `completeness` is never added to `registry.RULES`. It cannot be switched off from `guardrails.yaml`, and a `guardrails.yaml` entry naming `rule: completeness` must raise `UnknownGuardrailError`, exactly like any other typo. It becomes the **seventh** rule name (three unconditional: `provenance`, `no-unverified-metrics`, `completeness`; four configurable).
- **`role`, `project`, and `credential` are all mandatory** (owner decision 2). `skill` and `achievement` are never checked, regardless of presence (AC3).
- **`MANDATORY_KINDS = {"role": "experience", "project": "projects", "credential": "credentials"}`** — block type maps to the one section `kind` its entry must live in.
- **An entry may survive with no bullets** (owner decision 3) — **except** a block carrying `attribution` whose phrase the entry's header cannot supply: `check_attribution` reads `title + org + role + bullets`, so the entry then needs a bullet (architecture §5.5, narrowed per review I-1 to avoid a false positive and a doubled report).
- **The rule reads no `config`** (architecture §11 C5): `DEFAULT_FUZZY_THRESHOLD = 90` is a module constant in `engine/guardrails/base.py`, not read from `ctx.config`.
- **No new LLM call, no new pipeline step** (AC9): the rule runs against the already-composed `ResumeDocument`, `Selection.block_ids`, and `profile.block_map()`.
- **One violation per defect, not two** (AC8 / architecture §11 C7): a merge or substitution produces exactly one `completeness` violation (the missing block's), annotated with where its content went — never a second violation for the same physical defect.
- **Recorded exception to that: a duplicated entry.** A block printed twice is one `completeness` error *and* a `date-consistency` overlap error (the block overlaps itself). C7/AC8 concern merge and substitution; the second error belongs to a rule this project does not own and is true, so it is not suppressed (plan-review-2, Minor 3; pinned by a test).
- **`rules_run` is not evidence of wiring.** It lists `completeness` whether or not `check_completeness` is called. Prove wiring with behaviour (a dropped role fails a bare account), never with a `rules_run` assertion.
- **The tune path (`run_tune_guardrails`) never emits `rule == "completeness"`** (spec §6, architecture §7.8) — asserted by test, not left to accident.
- **A failing guardrail report must not persist a DOCX, in any run mode** — pipeline (blocks branch), CLI, worker, and the API's hand-edit path (owner confirmation, 2026-09-25; AC5). The tune branch already does this correctly and is the pattern to copy.
- **No page-count mechanism exists or is added.** There is no page-count code anywhere in the engine (verified: `render/templates.py`'s "two-page" references are comments only). The two-page tension (spec §3) is resolved by a prompt line telling the composer to thin bullets, never drop entries — nothing else.
- **Fixtures come from `profile.example/`, never from `profile/`** (CLAUDE.md rule 4). Task 1b edits `profile.example/blocks.yaml` — the fictional demo profile, which is exactly where rule 4 says fixtures live — and every string it adds is fictional. Any test needing more than `profile.example`'s one role/one project/one credential builds fictional `Block`/`ResumeDocument` objects locally. `scripts/check-no-personal-data.py` matches *organisation names from the real profile*; the strings added here (`Creator and maintainer`) contain none, and it was run before and after: `clean: no org name from profile/ in tracked files (11 names checked)`.
- **Max 3 LLM calls per tailoring run** (CLAUDE.md) — unchanged; this project never adds a call.
- **Every task ships green, and says what "green" covered.** For every task: from `apps/api`, run `uv run ruff format .` and commit the result (review I-2), then `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, `uv run lint-imports`, and the suites the task names. The one web-touching task also runs `pnpm typecheck`, `pnpm lint`, `pnpm test` from `apps/web`. Per the working agreement, scope each task's pytest run to the suites it names and run the **whole** `uv run pytest` once, before hand-over to QA (Task 5's last step). Every task report follows "CI facts" above: local runs skip the DB suites (no Docker on the laptop) and **CI is the full gate**.

---

### Step 0: Create the branch (plan-review-2, Minor 5)

Nothing in this plan is committed to `main`. Before Task 1b, from a clean checkout of `main`:

```bash
git worktree add .claude/worktrees/completeness -b api/completeness-guardrail main
cd .claude/worktrees/completeness
```

(or `git switch -c api/completeness-guardrail main` if you do not use worktrees; other agents' worktrees already live under `.claude/worktrees/`). This plan file and the `.superpowers/sdd/completeness-guardrail/` documents are untracked in the main checkout: copy them in, or commit the plan as the branch's first commit (`docs: completeness guardrail plan`), so the branch carries what it implements. Every task's CI run happens on this branch (CI runs on `pull_request` and on branch pushes only if a PR exists; open a draft PR after Task 1b so each later push is gated). Never push to `main` to find out.

---

### Task 1b: Make the demo profile completeness-compatible (review C-2, owner Option 2)

**Advances:** review C-2 (owner decision 2026-09-29). Prerequisite of Task 1. **Executes first.**

**Why this is needed (verified, not asserted).** `DeterministicFakeProvider` (`engine/providers/fake.py`) skips any block that is `verified: false` and whose `content` contains a digit, to stay clear of `no-unverified-metrics`. In `profile.example/blocks.yaml`, `side-llm-tool` (project, content `... (1.2k GitHub stars).`) and `cred-pmp` (credential, content `PMP certification (2021).`) both hit that, so the fake's resume cites only `acme-data-pm`; with `completeness` wired, the two skipped blocks are two errors, `status == "blocked"`, and (after Task 4) no DOCX at all. That breaks `tests/unit/test_fake_provider.py::test_the_composed_resume_passes_every_guardrail`, `tests/api/test_fake_provider_api.py::test_a_whole_tailor_run_produces_a_clean_package`, the `RHAPTO_LLM_PROVIDER=fake` Docker/Playwright stack (`docker-compose.e2e.yml:13,16`) and `apps/web/e2e/resumes.spec.ts` "Skip archives the resume".

**The two choices, and why they differ (review C-2 offered "strip digits or set `verified: true`"):**

- `side-llm-tool` → **strip the digits, stay unverified, add a `role`.** Three tests in `tests/guardrails/test_metrics.py` use it as *the* unverified block (`test_flags_number_from_unverified_block_even_if_present_in_source`, `test_message_wording_is_exact` — which pins wording the landing page quotes — and `test_adversarial_unit_suffixed_and_hyphenated_metrics`); `verified: true` would break them and would also undo the demo's own story that an unverified number cannot get through. Stripping is nearly free: no fixture ever printed the star count in a bullet (`helpers.demo_resume()` says `"Built an open-source LLM eval harness."`, the golden cases `"Built and maintain an open-source LLM eval harness."`), so the block now reads like its own fixtures. The project clause needs a label the fake can copy without inventing one (it writes no words of its own, and no rule validates `title`); `role: Creator and maintainer` is copied verbatim onto `entry.role`, which `no-invented-entities` checks and passes.
- `cred-pmp` → **`verified: true`, keep `(2021)`.** A certification year is a checkable fact, `verified` is the honest flag for it, and the demo stays realistic (a credential with no year is a worse demo). `no-unverified-metrics` then accepts `2021` from the block's own verified source. `git grep` finds no test that depends on `cred-pmp` being unverified. It has no `org`/`role`, and does not need one: the credential clause accepts a bullet with no label (architecture §2, and this is the shape the canonical fixture already uses).
- **Golden churn: zero files.** The three golden cases' `compose.json`/`repair.json` cite both blocks with a `title` (project) and a bullet (credential) and no digits; both are accepted by the clauses and by every other rule, and `tests/golden` stays green (verified, both before and after Task 1). `helpers.demo_resume()` is unchanged and deliberately keeps a project entry carrying `title` (the *title* branch of the project clause), while the fake exercises the *role* branch.

**Files:**
- Modify: `profile.example/blocks.yaml`
- Modify: `apps/api/src/rhapto/engine/providers/fake.py` (docstring only — under Option 2 the provider needs no code change)
- Modify: `apps/api/tests/unit/test_fake_provider.py` (new proof test)
- Modify: `apps/api/tests/api/test_fake_provider_api.py` (`test_a_whole_tailor_run_produces_a_clean_package`: cited-block assertion; **DB test, CI-only**)
- Modify: `apps/api/tests/guardrails/test_metrics.py` (`test_flags_number_from_unverified_block_even_if_present_in_source` keeps its meaning)
- Verified, no edit: `apps/api/tests/golden/cases/{acme-data-pm-clean,invented-metric-repaired,invented-metric-unrepairable}/*.json`, `apps/api/tests/helpers.py`, every `apps/web/e2e/*.spec.ts` (none asserts block content), `scripts/check-no-personal-data.py`

**Interfaces:** none produced or consumed. After this task `profile.example` holds exactly one `role`, one `project` and one `credential` block, all three placeable by the fake provider.

- [ ] **Step 1: Add the tests first, and watch the proof test fail**

  Apply this diff (tests and the docstring; **not** the fixture):

  ```diff
  diff --git a/apps/api/src/rhapto/engine/providers/fake.py b/apps/api/src/rhapto/engine/providers/fake.py
  index e3e371f..64f64cf 100644
  --- a/apps/api/src/rhapto/engine/providers/fake.py
  +++ b/apps/api/src/rhapto/engine/providers/fake.py
  @@ -157,6 +157,12 @@ class DeterministicFakeProvider:
         entry (this provider never merges bullets, so it cannot fold an achievement into its role's
         own entry the way the real prompt does) is skipped for the same reason -- and named in
         `change_log`, so the drop is visible rather than silent.
  +
  +      Either skip is a hazard for a selected role, project or credential block: the
  +      `completeness` guardrail turns the omission into a blocked package. `profile.example` is
  +      therefore written so that never happens (its project block carries a role and no number, its
  +      credential is verified), and `test_every_mandatory_block_of_the_demo_profile_gets_an_entry`
  +      fails if that stops being true.
       * **Tune** proposes no edits at all. Zero edits is the only rewrite of a human's own document
         that is guaranteed not to invent anything.
       * The cover note is deliberately bland: no company name, no numbers, nothing for a guardrail
  diff --git a/apps/api/tests/api/test_fake_provider_api.py b/apps/api/tests/api/test_fake_provider_api.py
  index c9d9337..039495c 100644
  --- a/apps/api/tests/api/test_fake_provider_api.py
  +++ b/apps/api/tests/api/test_fake_provider_api.py
  @@ -114,3 +114,11 @@ async def test_a_whole_tailor_run_produces_a_clean_package(
           for b in entry["bullets"]
       }
       assert block_ids, "every bullet must still cite a block"
  +    # Review C-2: the fake must place every selected mandatory block, or `completeness` blocks the
  +    # demo stack. The three mandatory blocks of profile.example are all selected by default.
  +    entry_ids = {
  +        entry["source_block_id"]
  +        for section in package["resume"]["sections"]
  +        for entry in section["entries"]
  +    }
  +    assert {"acme-data-pm", "side-llm-tool", "cred-pmp"} <= entry_ids
  diff --git a/apps/api/tests/guardrails/test_metrics.py b/apps/api/tests/guardrails/test_metrics.py
  index 14e3680..f927f3c 100644
  --- a/apps/api/tests/guardrails/test_metrics.py
  +++ b/apps/api/tests/guardrails/test_metrics.py
  @@ -1,3 +1,4 @@
  +from dataclasses import replace
   from pathlib import Path

   import pytest
  @@ -77,7 +78,16 @@ def test_flags_number_from_unverified_block_even_if_present_in_source(
       resume.sections[1].entries[0].bullets[0] = bullet(
           "Built an LLM eval harness with 1.2k GitHub stars.", "side-llm-tool"
       )
  -    violations = check_metrics(make_ctx(demo_profile_dir, resume))
  +    ctx = make_ctx(demo_profile_dir, resume)
  +    # `profile.example`'s side-llm-tool carries no number any more (the fake provider has to be
  +    # able to copy it), so this test builds its own unverified block whose SOURCE does hold
  +    # the number -- the case its name is about.
  +    block = ctx.blocks["side-llm-tool"].model_copy(
  +        update={"content": "Built an open-source LLM eval harness (1.2k GitHub stars)."}
  +    )
  +    assert not block.verified and "1.2k" in block.content
  +    ctx = replace(ctx, blocks={**ctx.blocks, "side-llm-tool": block})
  +    violations = check_metrics(ctx)
       assert len(violations) == 1 and "not verified" in violations[0].message


  diff --git a/apps/api/tests/unit/test_fake_provider.py b/apps/api/tests/unit/test_fake_provider.py
  index 5b92881..9e43868 100644
  --- a/apps/api/tests/unit/test_fake_provider.py
  +++ b/apps/api/tests/unit/test_fake_provider.py
  @@ -123,6 +123,22 @@ async def test_compose_cites_only_selected_blocks_and_copies_them_verbatim(
       assert output.cover_note and output.change_log


  +async def test_every_mandatory_block_of_the_demo_profile_gets_an_entry(
  +    demo_profile_dir: object,
  +) -> None:
  +    """Review C-2 (2026-09-29). The fake skips any unverified block whose content holds a digit,
  +    and (before this fixture change) `side-llm-tool` and `cred-pmp` both did, so the demo stack
  +    produced a resume with two selected blocks missing. Every role, project and credential block
  +    in `profile.example` must be one the fake can place."""
  +    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
  +    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
  +    output = await _compose(json.dumps(blocks), [b["id"] for b in blocks])
  +    cited = {e.source_block_id for s in output.sections for e in s.entries}
  +    mandatory = {b.id for b in profile.blocks if b.type in ("role", "project", "credential")}
  +    assert mandatory == {"acme-data-pm", "side-llm-tool", "cred-pmp"}, "fixture drifted"
  +    assert mandatory <= cited, sorted(mandatory - cited)
  +
  +
   async def test_a_block_outside_the_selection_is_never_cited(demo_profile_dir: object) -> None:
       profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
       blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
  ```

  Run: `cd apps/api && uv run pytest tests/unit/test_fake_provider.py -q`
  Expected: the new test **FAILS** with `AssertionError: ['cred-pmp', 'side-llm-tool']` (`{'acme-data-pm'}` is all the fake cited) — the two blocks it skips. Everything else in the file passes. (If the new test passes here, it proves nothing; stop.) Verified.

- [ ] **Step 2: Change the fixture**

  ```diff
  diff --git a/profile.example/blocks.yaml b/profile.example/blocks.yaml
  index 46bf0e1..a7b1999 100644
  --- a/profile.example/blocks.yaml
  +++ b/profile.example/blocks.yaml
  @@ -19,9 +19,11 @@ blocks:
     - id: side-llm-tool
       type: project
       org: Independent
  -    content: Built an open-source LLM eval harness (1.2k GitHub stars).
  +    role: Creator and maintainer
  +    content: Built an open-source LLM eval harness.
       tags: [ai, oss]
     - id: cred-pmp
       type: credential
  +    verified: true
       content: PMP certification (2021).
       tags: [credential]
  ```

- [ ] **Step 3: Re-run the proof test and the suites the fixture can reach**

  Run: `cd apps/api && uv run pytest tests/unit/test_fake_provider.py tests/guardrails tests/golden tests/unit/test_select.py tests/unit/test_compose.py -q`
  Expected: all pass (verified). This reaches the fake, every guardrail rule, the golden cases, block-text scoring in `select` (its hashed-embedding ranking `acme-migration > cred-pmp` is unchanged) and the block fixtures in `compose`.

- [ ] **Step 4: Personal-data scan**

  Run, from the repo root: `python scripts/check-no-personal-data.py`
  Expected: `clean: no org name from profile/ in tracked files (N names checked)`. (It is a no-op without a local `profile/`; note in the report which it was.)

- [ ] **Step 5: Format and gate**

  ```
  cd apps/api
  uv run ruff format .        # commit whatever it changes (review I-2)
  uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
  ```
  Report per "CI facts": suites run locally = `tests/unit/test_fake_provider.py`, `tests/guardrails`, `tests/golden`, `tests/unit/test_select.py`, `tests/unit/test_compose.py`; **not run locally, CI-only:** `tests/api/test_fake_provider_api.py` (needs Postgres/Redis) and the Playwright e2e suite (needs Docker; CI never runs it — see U-2).

- [ ] **Step 6: Commit**

  ```bash
  git add profile.example/blocks.yaml apps/api/src/rhapto/engine/providers/fake.py \
          apps/api/tests/unit/test_fake_provider.py apps/api/tests/api/test_fake_provider_api.py \
          apps/api/tests/guardrails/test_metrics.py
  git commit -m "fix(profile.example): make the demo profile placeable by the fake provider (review C-2)"
  ```

---

### Task 1: The `completeness` rule, wired unconditionally

**Advances AC:** 1, 2, 3, 4, 6, 7, 8, 9, 10. **Depends on Task 1b.**

**Files:**
- Create: `apps/api/src/rhapto/engine/guardrails/completeness.py`
- Modify: `apps/api/src/rhapto/engine/guardrails/base.py` (add `DEFAULT_FUZZY_THRESHOLD`, `fuzzy_entity_match`, `from rapidfuzz import fuzz`)
- Modify: `apps/api/src/rhapto/engine/guardrails/entities.py` (use the promoted `fuzzy_entity_match`; behaviour unchanged)
- Modify: `apps/api/src/rhapto/engine/guardrails/registry.py` (wire `completeness` unconditionally after `no-unverified-metrics`; add its `REMEDIES` entry; docstring)
- Create: `apps/api/tests/guardrails/test_completeness.py`
- Modify: `apps/api/tests/guardrails/test_registry.py` (**review C-1**: the two literal `rules_run` assertions; two tests renamed from "both" to "all"; `completeness` added to the not-in-`RULES` assertion)
- Modify: `apps/api/tests/api/test_guardrail_remedies.py` (**D-2**: the rule-set pin becomes seven)
- Modify: `apps/api/tests/unit/test_fake_provider.py` (completeness ran + known-bad input must block)
- Modify: `apps/api/tests/api/test_fake_provider_api.py` (`rules_run` includes `completeness`; **DB test, CI-only**)
- Modify: `docs/requirements-architecture.md` (one clause in §7 step 4)

**Interfaces:**
- Consumes: `GuardrailContext` (`resume: ResumeDocument`, `blocks: Mapping[str, Block]`, `selection_ids: frozenset[str]`) from `rhapto.engine.guardrails.base`; `iter_entries_with_section(resume) -> Iterator[tuple[str, ResumeSection, ResumeEntry]]`; `violation(rule, message, path, block_id=None, severity="error") -> Violation`; `normalize_entity(text: str) -> str`; `Block` (`id, type, org, role, period, content, attribution` — read-only here) from `rhapto.models.profile.blocks`.
- Produces (frozen for later tasks, per architecture §6):
  - `RULE_NAME: str = "completeness"`, `MANDATORY_KINDS: Mapping[str, str]`, `check_completeness(ctx: GuardrailContext) -> list[Violation]`
  - `fuzzy_entity_match(candidate: str, source: str, threshold: int) -> bool` and `DEFAULT_FUZZY_THRESHOLD: int = 90` on `base.py`
  - `registry.run_guardrails` now always returns `rules_run` beginning `["provenance", "no-unverified-metrics", "completeness"]`, and `REMEDIES["completeness"]`.

- [ ] **Step 1: Promote the fuzzy-match helper to `base.py` and re-point `entities.py`**

  Exact diff (a pure refactor; `DEFAULT_THRESHOLD` stays `entities.py`'s own configurable constant):

  ```diff
  diff --git a/apps/api/src/rhapto/engine/guardrails/base.py b/apps/api/src/rhapto/engine/guardrails/base.py
  index 6fd0593..ee8dc1c 100644
  --- a/apps/api/src/rhapto/engine/guardrails/base.py
  +++ b/apps/api/src/rhapto/engine/guardrails/base.py
  @@ -5,6 +5,8 @@ from collections.abc import Callable, Iterator, Mapping
   from dataclasses import dataclass, field, replace
   from typing import Any, Literal

  +from rapidfuzz import fuzz
  +
   from rhapto.models.guardrail_report import Violation
   from rhapto.models.jd_extract import JDExtract
   from rhapto.models.profile.blocks import Block
  @@ -29,6 +31,31 @@ def normalize_entity(text: str) -> str:
       return re.sub(r"\s+", " ", collapsed_dashes).strip().casefold()


  +DEFAULT_FUZZY_THRESHOLD = 90
  +
  +
  +def _entity_tokens(normalized: str) -> list[str]:
  +    return normalized.replace("-", " ").split()
  +
  +
  +def fuzzy_entity_match(candidate: str, source: str, threshold: int) -> bool:
  +    """The ratio absorbs case, dash and spacing differences; the token check rejects added words.
  +
  +    "Sr Product Manager", "Product Manager II" and "Acme Analytica" all clear the ratio floor
  +    against "Product Manager" / "Acme Analytics", but each carries a token the source does not
  +    have, which is exactly the title and org inflation `no-invented-entities` exists to stop, and
  +    exactly the false positive `completeness`'s merge/substitution detection must not trip on a
  +    client org that merely sounds like the employer.
  +    """
  +    a, b = normalize_entity(candidate), normalize_entity(source)
  +    if a == b:
  +        return True
  +    if fuzz.ratio(a, b) < threshold:
  +        return False
  +    source_tokens = set(_entity_tokens(b))
  +    return all(token in source_tokens for token in _entity_tokens(a))
  +
  +
   @dataclass(frozen=True)
   class GuardrailContext:
       resume: ResumeDocument
  diff --git a/apps/api/src/rhapto/engine/guardrails/entities.py b/apps/api/src/rhapto/engine/guardrails/entities.py
  index 5a7e4ca..f63858d 100644
  --- a/apps/api/src/rhapto/engine/guardrails/entities.py
  +++ b/apps/api/src/rhapto/engine/guardrails/entities.py
  @@ -1,9 +1,8 @@
   from __future__ import annotations

  -from rapidfuzz import fuzz
  -
   from rhapto.engine.guardrails.base import (
       GuardrailContext,
  +    fuzzy_entity_match,
       iter_entries,
       normalize_entity,
       violation,
  @@ -14,26 +13,6 @@ RULE_NAME = "no-invented-entities"
   DEFAULT_THRESHOLD = 90


  -def _tokens(normalized: str) -> list[str]:
  -    return normalized.replace("-", " ").split()
  -
  -
  -def _fuzzy_match(candidate: str, source: str, threshold: int) -> bool:
  -    """The ratio absorbs case, dash and spacing differences; the token check rejects added words.
  -
  -    "Sr Product Manager", "Product Manager II" and "Acme Analytica" all clear the ratio floor
  -    against "Product Manager" / "Acme Analytics", but each carries a token the source does not
  -    have, which is exactly the title and org inflation this rule exists to stop.
  -    """
  -    a, b = normalize_entity(candidate), normalize_entity(source)
  -    if a == b:
  -        return True
  -    if fuzz.ratio(a, b) < threshold:
  -        return False
  -    source_tokens = set(_tokens(b))
  -    return all(token in source_tokens for token in _tokens(a))
  -
  -
   def check_entities(ctx: GuardrailContext) -> list[Violation]:
       """Entry org, role, and period must match the entry's source block (fuzzy for org/role, exact for period)."""
       threshold = int(ctx.config.get("fuzzy_threshold", DEFAULT_THRESHOLD))
  @@ -56,7 +35,7 @@ def check_entities(ctx: GuardrailContext) -> list[Violation]:
                           )
                       )
                   continue
  -            if source is None or not _fuzzy_match(value, source, threshold):
  +            if source is None or not fuzzy_entity_match(value, source, threshold):
                   out.append(
                       violation(
                           RULE_NAME,
  ```

- [ ] **Step 2: Run the existing entities tests to confirm the refactor is behaviour-preserving**

  Run: `cd apps/api && uv run pytest tests/guardrails/test_entities.py -v`
  Expected: all pass, unchanged.

- [ ] **Step 3: Write `completeness.py`**

  Create `apps/api/src/rhapto/engine/guardrails/completeness.py`. Three things differ from the 2026-09-25 draft and are load-bearing: `_describe` builds its list with a truthiness test that mypy strict can narrow (review C-4); `_attribution_unreachable` mirrors `check_attribution`'s joined text (review I-1); `_org_appears_in_entry_text` is a whole-word match (review M-1).

  ```python
  """Completeness: every selected role/project/credential block gets exactly one identifiable entry.

  Unconditional, like provenance and no-unverified-metrics (owner decision 1): not registered in
  `registry.RULES`, so it cannot be switched off or mistyped out of `guardrails.yaml`, and it reads
  no `ctx.config` (C5 -- an unconditional rule with a tunable knob is a configurable rule wearing a
  disguise).

  See `.superpowers/sdd/completeness-guardrail/architecture.md` sections 1-3 and 7 for the design
  this implements.
  """

  from __future__ import annotations

  import re
  from collections.abc import Mapping

  from rhapto.engine.guardrails.base import (
      DEFAULT_FUZZY_THRESHOLD,
      GuardrailContext,
      fuzzy_entity_match,
      iter_entries_with_section,
      normalize_entity,
      violation,
  )
  from rhapto.models.guardrail_report import Violation
  from rhapto.models.profile.blocks import Block
  from rhapto.models.resume_document import ResumeEntry, ResumeSection

  RULE_NAME = "completeness"

  #: Block type -> the section kind that block's entry must live in.
  MANDATORY_KINDS: Mapping[str, str] = {
      "role": "experience",
      "project": "projects",
      "credential": "credentials",
  }

  KIND_TITLE: Mapping[str, str] = {
      "experience": "Experience",
      "projects": "Projects",
      "credentials": "Credentials",
  }

  _Entry = tuple[str, ResumeSection, ResumeEntry]


  def _present(value: str | None) -> bool:
      return bool((value or "").strip())


  def _org_matches(a: str | None, b: str | None) -> bool:
      # Asymmetric on purpose (it is `no-invented-entities`' own comparison): the first argument's
      # tokens must all appear in the second's. It only ever feeds a message annotation here, never
      # a violation, so the asymmetry cannot create or hide an error.
      if not a or not b:
          return False
      return fuzzy_entity_match(a, b, DEFAULT_FUZZY_THRESHOLD)


  def _org_appears_in_entry_text(org: str, entry: ResumeEntry) -> bool:
      """Whole-word match, so an org like "Independent" does not light up "independently"."""
      needle = re.compile(rf"\b{re.escape(normalize_entity(org))}\b")
      haystacks = [entry.org, entry.title, entry.role, *(b.text for b in entry.bullets)]
      return any(needle.search(normalize_entity(h)) for h in haystacks if h)


  def _block_is_unrenderable(block: Block) -> bool:
      """A mandatory block with no org, no role and empty content renders as nothing in either
      template (`render/templates.py`); flagging its absence as an error would block every run
      forever. Architecture §7.3."""
      return not _present(block.org) and not _present(block.role) and not _present(block.content)


  def _attribution_unreachable(block: Block, entry: ResumeEntry) -> bool:
      """Whether `block` needs an attribution phrase this bullet-less entry can never carry.

      Architecture §5.5: `check_attribution` reads the entry's title, org and role as well as its
      bullets (`guardrails/attribution.py`), so the phrase can already be satisfied from a header
      field. The gap therefore exists only when the entry has no bullet text AND the phrase is absent
      from that same joined text. With a bullet present, `attribution` itself reports a missing
      phrase, and a second `completeness` error for the same defect would break C7 (one violation
      per defect).
      """
      if not block.attribution or any(_present(b.text) for b in entry.bullets):
          return False
      text = " ".join(filter(None, [entry.title, entry.org, entry.role]))
      return block.attribution.casefold() not in text.casefold()


  def _identity(block: Block, entry: ResumeEntry) -> tuple[bool, str]:
      """Whether `entry` gives `block` a renderable identity, per the per-type clauses in
      architecture §2, and -- when it doesn't -- a description of what's missing, for the violation
      message.
      """
      has_bullet_text = any(_present(b.text) for b in entry.bullets)
      if block.type == "role":
          has_org = _present(entry.org)
          has_title = _present(entry.role) or _present(entry.title)
          gaps = [g for g, ok in (("org", has_org), ("role/title", has_title)) if not ok]
      elif block.type == "project":
          has_title = _present(entry.title) or _present(entry.role)
          gaps = [] if has_title else ["title/role"]
      else:  # credential
          has_label = _present(entry.title) or _present(entry.role) or _present(entry.org)
          gaps = [] if (has_label or has_bullet_text) else ["a label (title/role/org) or a bullet"]
      if _attribution_unreachable(block, entry):
          gaps.append("a bullet carrying the required attribution phrase")
      return (not gaps, " and ".join(gaps))


  def _describe(block: Block) -> str:
      """Identify `block` from its own fields, never the document -- the document is what's
      missing. Falls back to the start of `content` for a block with no org, role or period
      (the `cred-pmp` shape)."""
      parts = [p for p in (block.org, block.role) if p and p.strip()]
      head = " — ".join(parts)
      if _present(block.period):
          head = f"{head}, {block.period}" if head else (block.period or "")
      return head or (block.content or "").strip()[:60]


  def _merge_annotation(
      ctx: GuardrailContext, block: Block, kind: str, all_entries: list[_Entry]
  ) -> str:
      """Architecture §3: when `block` has no entry anywhere, look for evidence its content
      survived somewhere else. Substitution is checked before fold, and fold's bullet scan
      excludes bullets citing the entry's own block -- otherwise an entry that cites a same-org
      block which is unselected, or of another type (so the substitution branch does not fire),
      would have its own bullets reported as "folded".
      """
      if not _present(block.org):
          return ""
      org = block.org or ""
      for path, section, entry in all_entries:
          if section.kind != kind or entry.source_block_id == block.id:
              continue
          sibling = ctx.blocks.get(entry.source_block_id)
          if (
              sibling is not None
              and sibling.id in ctx.selection_ids
              and sibling.type == block.type
              and _org_matches(sibling.org, org)
          ):
              return (
                  f"; block {sibling.id!r} (same organisation) is present at {path} -- check "
                  "whether one entry was substituted for both"
              )
          folded = [
              i
              for i, b in enumerate(entry.bullets)
              if b.source_block_id != entry.source_block_id
              and (src := ctx.blocks.get(b.source_block_id)) is not None
              and _org_matches(src.org, org)
          ]
          if folded:
              return (
                  f"; its content appears folded into {path} (bullets {folded} cite blocks whose "
                  f"org is {org!r})"
              )
          if _org_appears_in_entry_text(org, entry):
              return (
                  f"; its content appears folded into {path} (org {org!r} appears in that "
                  "entry's text)"
              )
      return ""


  def check_completeness(ctx: GuardrailContext) -> list[Violation]:
      """Every selected role/project/credential block has exactly one identifiable entry citing it.

      Reads only `ctx.resume`, `ctx.blocks` and `ctx.selection_ids` -- never `ctx.config` (C5).
      Violations are sorted by `(block_id, message)` so output order never depends on `frozenset`
      iteration order.
      """
      all_entries: list[_Entry] = list(iter_entries_with_section(ctx.resume))
      out: list[Violation] = []
      for block_id in sorted(ctx.selection_ids):
          block = ctx.blocks.get(block_id)
          if block is None or block.type not in MANDATORY_KINDS:
              continue
          if _block_is_unrenderable(block):
              out.append(
                  violation(
                      RULE_NAME,
                      f"{block.type} block {block.id!r} is selected but carries no org, role or "
                      "content and cannot be rendered; fix the block library",
                      f"selection.block_ids[{block.id!r}]",
                      block.id,
                      severity="warning",
                  )
              )
              continue
          kind = MANDATORY_KINDS[block.type]
          citing = [(p, s, e) for p, s, e in all_entries if e.source_block_id == block_id]
          right_section = [(p, s, e) for p, s, e in citing if s.kind == kind]
          qualifying = [(p, s, e) for p, s, e in right_section if _identity(block, e)[0]]
          if len(qualifying) == 1:
              continue
          if len(qualifying) > 1:
              paths = [p for p, _, _ in qualifying]
              out.append(
                  violation(
                      RULE_NAME,
                      f"{block.type} block {block.id!r} ({_describe(block)}) appears in "
                      f"{len(paths)} entries ({', '.join(paths)}); expected exactly one",
                      paths[1],
                      block.id,
                  )
              )
          elif right_section:
              path, _, entry = right_section[0]
              _, gap = _identity(block, entry)
              out.append(
                  violation(
                      RULE_NAME,
                      f"{block.type} block {block.id!r} ({_describe(block)}) was selected but its "
                      f"entry in {KIND_TITLE[kind]} is missing {gap} and cannot be identified",
                      path,
                      block.id,
                  )
              )
          elif citing:
              wrong_kinds = sorted({s.kind for _, s, _ in citing})
              out.append(
                  violation(
                      RULE_NAME,
                      f"{block.type} block {block.id!r} ({_describe(block)}) was selected but "
                      f"does not appear in {KIND_TITLE[kind]}; its entry is in "
                      f"{'/'.join(wrong_kinds)} instead",
                      citing[0][0],
                      block.id,
                  )
              )
          else:
              message = (
                  f"{block.type} block {block.id!r} ({_describe(block)}) was selected but does "
                  f"not appear in {KIND_TITLE[kind]}"
              )
              message += _merge_annotation(ctx, block, kind, all_entries)
              out.append(
                  violation(RULE_NAME, message, f"selection.block_ids[{block.id!r}]", block.id)
              )
      return sorted(out, key=lambda v: (v.block_id or "", v.message))
  ```

- [ ] **Step 4: Wire it unconditionally, add its remedy**

  ```diff
  diff --git a/apps/api/src/rhapto/engine/guardrails/registry.py b/apps/api/src/rhapto/engine/guardrails/registry.py
  index c3d8942..1938016 100644
  --- a/apps/api/src/rhapto/engine/guardrails/registry.py
  +++ b/apps/api/src/rhapto/engine/guardrails/registry.py
  @@ -5,6 +5,8 @@ from collections.abc import Iterable
   from rhapto.engine.guardrails.attribution import RULE_NAME as ATTRIBUTION
   from rhapto.engine.guardrails.attribution import check_attribution
   from rhapto.engine.guardrails.base import GuardrailContext, Rule, violation
  +from rhapto.engine.guardrails.completeness import RULE_NAME as COMPLETENESS
  +from rhapto.engine.guardrails.completeness import check_completeness
   from rhapto.engine.guardrails.dates import RULE_NAME as DATES
   from rhapto.engine.guardrails.dates import check_dates
   from rhapto.engine.guardrails.entities import RULE_NAME as ENTITIES
  @@ -76,6 +78,10 @@ REMEDIES: dict[str, str] = {
           "A claim needs the context that makes it true -- scope, team size or scale. Add it to the "
           "block, then regenerate."
       ),
  +    COMPLETENESS: (
  +        "A role, project or credential your profile selected for this job is missing from the "
  +        "resume. Regenerate; if the same one keeps vanishing, try a stronger model."
  +    ),
   }


  @@ -100,10 +106,11 @@ def run_guardrails(
       extract: JDExtract,
       cover_note: str | None = None,
   ) -> GuardrailReport:
  -    """Run the two unconditional rules plus every active configured rule.
  +    """Run the three unconditional rules plus every active configured rule.

  -    Provenance and no-unverified-metrics always run, for every account, whatever is or is not in the
  -    `guardrails` table. They are the product's two promises; a deployment where they depend on a row
  +    Provenance, no-unverified-metrics and completeness always run, for every account, whatever is or
  +    is not in the `guardrails` table. They are the product's promises (completeness is provenance's
  +    other half: a silent omission is a truthfulness failure); a deployment where they depend on a row
       existing is a deployment where a fresh account quietly has one of them switched off.

       A user may still carry a `no-unverified-metrics` row -- older profiles all do. Its `config` is
  @@ -116,12 +123,13 @@ def run_guardrails(
           selection_ids=frozenset(selection_ids),
           extract=extract,
       )
  -    rules_run = [PROVENANCE, METRICS]
  +    rules_run = [PROVENANCE, METRICS, COMPLETENESS]
       violations: list[Violation] = check_provenance(ctx)
       # Honour an existing row's config if the profile has one; otherwise the rule's own defaults.
       metrics_config = next((r.config for r in profile.guardrails if r.rule == METRICS), None)
       metrics_ctx = ctx if metrics_config is None else ctx.with_config(metrics_config)
       violations.extend(check_metrics(metrics_ctx))
  +    violations.extend(check_completeness(ctx))
       for rule in profile.guardrails:
           if rule.rule == METRICS:
               continue  # already run above, unconditionally
  ```

  Do **not** add `COMPLETENESS` to the `RULES` dict — that is what makes it unconditional (C4): `RULES.get("completeness")` stays `None`, so a `guardrails.yaml` entry naming it raises `UnknownGuardrailError`, same as any other typo. The remedy is required, not optional: `test_every_rule_has_a_remedy` discovers `RULE_NAME` constants by walking the package and fails without it (D-2), and `test_no_remedy_is_empty_or_a_restatement_of_the_rule_id` requires more than 40 characters.

- [ ] **Step 5: Write `test_completeness.py`**

  Create `apps/api/tests/guardrails/test_completeness.py` (26 tests). It builds fictional `Block`/`ResumeDocument` fixtures locally (CLAUDE.md rule 4; `profile.example` has only one block of each mandatory type, not enough for the 5-block adversarial case AC10 asks for) and uses `profile.example` via `demo_profile_dir`/`demo_resume` only where the fixture already fits. Changes from the draft: C-3 (`test_selection_id_not_in_block_map_is_skipped_not_raised` now selects *only* the unknown id, because a co-selected real absent role correctly produces a violation and hid the test's subject); I-1 (two attribution edges); I-4 (three `date-consistency` interaction tests); M-1 (one whole-word test); an extra test that an empty `guardrails` table still catches a dropped role; and one that pins a duplicated entry as `completeness` plus `date-consistency` (recorded exception, Global Constraints). **Coder note (review M-5, U-1):** the project clause pushes a composer toward inventing a `title` — a field no rule validates. Do not paper over that in any fixture.

  ```python
  from pathlib import Path

  import pytest
  from helpers import bullet, demo_extract, demo_resume

  from rhapto.engine.guardrails.base import GuardrailContext
  from rhapto.engine.guardrails.completeness import RULE_NAME, check_completeness
  from rhapto.engine.guardrails.registry import RULES, UnknownGuardrailError, run_guardrails
  from rhapto.engine.guardrails.tune import run_tune_guardrails
  from rhapto.models.profile.blocks import Block
  from rhapto.models.profile.guardrails import GuardrailRule
  from rhapto.models.resume_document import (
      ResumeDocument,
      ResumeEntry,
      ResumeHeader,
      ResumeSection,
  )
  from rhapto.profile.loader import load_profile


  def _role(id: str, org: str, role: str, period: str, content: str, **extra: object) -> Block:
      return Block(id=id, type="role", org=org, role=role, period=period, content=content, **extra)  # type: ignore[arg-type]


  ROLE_A = _role("role-a", "Globex", "Engineer", "2018-2020", "Built things.")
  ROLE_B = _role("role-b", "Initech", "Analyst", "2020-2021", "Analysed things.")
  ROLE_C = _role("role-c", "Umbrella", "Lead", "2021-2022", "Led things.")
  ROLE_D = _role("role-d", "Hooli", "Manager", "2022-2023", "Managed things.")
  ROLE_E = _role("role-e", "Vertex Robotics", "Founder", "2023-Present", "Founded a company.")
  FIVE_ROLES = [ROLE_A, ROLE_B, ROLE_C, ROLE_D, ROLE_E]

  ROLE_F = _role("role-f", "Vertex Robotics", "Co-Founder", "2023-Present", "Co-founded.")
  VERTEX_ACHIEVEMENT = Block(
      id="vertex-achievement", type="achievement", org="Vertex Robotics", content="Shipped a robot."
  )

  PROJECT_A = Block(id="project-a", type="project", org="Independent", content="Built a tool.")
  CRED_A = Block(id="cred-a", type="credential", content="Some certification.")
  SKILL_X = Block(id="skill-x", type="skill", content="Python")
  ACHIEVEMENT_X = Block(id="ach-x", type="achievement", org="Globex", content="Did a thing.")
  UNRENDERABLE = Block(id="ghost-role", type="role", content="")
  ATTRIBUTION_ROLE = _role(
      "attrib-role",
      "Globex",
      "Consultant",
      "2019-2020",
      "Consulted.",
      attribution="as part of the Globex Partner Program",
  )


  def _ctx(blocks: list[Block], resume: ResumeDocument, selection_ids: list[str]) -> GuardrailContext:
      return GuardrailContext(
          resume=resume,
          blocks={b.id: b for b in blocks},
          selection_ids=frozenset(selection_ids),
          extract=demo_extract(),
      )


  def _entry(block: Block, **overrides: object) -> ResumeEntry:
      defaults: dict[str, object] = dict(
          source_block_id=block.id,
          org=block.org,
          role=block.role,
          period=block.period,
          bullets=[bullet(f"Did {block.role} work.", block.id)],
      )
      defaults.update(overrides)
      return ResumeEntry(**defaults)  # type: ignore[arg-type]


  def _resume(
      entries: list[ResumeEntry], kind: str = "experience", title: str = "Experience"
  ) -> ResumeDocument:
      return ResumeDocument(
          header=ResumeHeader(name="Test Person"),
          sections=[ResumeSection(title=title, kind=kind, entries=entries)],  # type: ignore[arg-type]
      )


  def test_measured_case_one_role_missing_of_five() -> None:
      present = FIVE_ROLES[:4]
      resume = _resume([_entry(b) for b in present])
      ctx = _ctx(FIVE_ROLES, resume, [b.id for b in FIVE_ROLES])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      v = violations[0]
      assert v.rule == RULE_NAME and v.severity == "error" and v.block_id == "role-e"
      assert "role-e" in v.message and "Vertex Robotics" in v.message and "Founder" in v.message
      assert v.path == "selection.block_ids['role-e']"


  def test_merge_fold_produces_one_violation_naming_the_entry() -> None:
      entry_a = _entry(
          ROLE_A,
          bullets=[
              bullet("Did Engineer work.", ROLE_A.id),
              bullet("Shipped a robot for Vertex Robotics.", VERTEX_ACHIEVEMENT.id),
          ],
      )
      resume = _resume([entry_a] + [_entry(b) for b in FIVE_ROLES[1:4]])
      blocks = FIVE_ROLES + [VERTEX_ACHIEVEMENT]
      ctx = _ctx(blocks, resume, [b.id for b in FIVE_ROLES] + [VERTEX_ACHIEVEMENT.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      assert violations[0].block_id == "role-e"
      assert "sections[0].entries[0]" in violations[0].message
      assert "folded" in violations[0].message


  def test_substitution_same_org_sibling_present() -> None:
      entries = [_entry(b) for b in FIVE_ROLES[:4]] + [_entry(ROLE_F)]
      resume = _resume(entries)
      blocks = FIVE_ROLES + [ROLE_F]
      ctx = _ctx(blocks, resume, [b.id for b in FIVE_ROLES] + [ROLE_F.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      assert violations[0].block_id == "role-e"
      assert "role-f" in violations[0].message and "substituted" in violations[0].message


  def test_a_common_word_org_does_not_annotate_an_unrelated_entry_as_a_fold() -> None:
      """M-1: "Independent" is an org in `profile.example`; it must not match "independently"."""
      independent_role = _role("role-i", "Independent", "Consultant", "2016-2017", "Consulted.")
      sibling = _entry(ROLE_A, bullets=[bullet("Worked independently on a rebuild.", ROLE_A.id)])
      ctx = _ctx([ROLE_A, independent_role], _resume([sibling]), [ROLE_A.id, independent_role.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1 and violations[0].block_id == "role-i"
      assert "folded" not in violations[0].message


  def test_duplicate_entries_for_one_block() -> None:
      resume = _resume([_entry(ROLE_A), _entry(ROLE_A)])
      ctx = _ctx([ROLE_A], resume, [ROLE_A.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      assert violations[0].block_id == "role-a"
      assert "expected exactly one" in violations[0].message


  def test_clean_variation_with_reworded_bullets_passes(demo_profile_dir: Path) -> None:
      profile = load_profile(demo_profile_dir)
      resume = demo_resume()
      resume.sections[0].entries[0].bullets = list(reversed(resume.sections[0].entries[0].bullets))
      resume.sections[0].entries[0].bullets[0] = bullet(
          "Different wording, same block.", "acme-data-pm"
      )
      resume.sections[0].title = "Career History"
      ctx = GuardrailContext(
          resume=resume,
          blocks=profile.block_map(),
          selection_ids=frozenset(profile.block_map()),
          extract=demo_extract(),
      )
      assert check_completeness(ctx) == []


  def test_skill_and_achievement_never_checked() -> None:
      resume = _resume([])
      ctx = _ctx([SKILL_X, ACHIEVEMENT_X], resume, [SKILL_X.id, ACHIEVEMENT_X.id])
      assert check_completeness(ctx) == []


  def test_role_entry_in_wrong_section_kind() -> None:
      resume = ResumeDocument(
          header=ResumeHeader(name="Test Person"),
          sections=[ResumeSection(title="Projects", kind="projects", entries=[_entry(ROLE_A)])],
      )
      ctx = _ctx([ROLE_A], resume, [ROLE_A.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      assert violations[0].block_id == "role-a"
      assert "projects" in violations[0].message


  def test_role_entry_with_blank_org_is_flagged() -> None:
      resume = _resume([_entry(ROLE_A, org=None)])
      ctx = _ctx([ROLE_A], resume, [ROLE_A.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1 and "org" in violations[0].message


  def test_project_entry_with_blank_title_and_role_is_flagged() -> None:
      resume = ResumeDocument(
          header=ResumeHeader(name="Test Person"),
          sections=[
              ResumeSection(
                  title="Projects",
                  kind="projects",
                  entries=[
                      ResumeEntry(
                          source_block_id=PROJECT_A.id,
                          org="Independent",
                          bullets=[bullet("Built a tool.", PROJECT_A.id)],
                      )
                  ],
              )
          ],
      )
      ctx = _ctx([PROJECT_A], resume, [PROJECT_A.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1 and "title/role" in violations[0].message


  def test_credential_with_neither_label_nor_bullets_is_flagged() -> None:
      resume = ResumeDocument(
          header=ResumeHeader(name="Test Person"),
          sections=[
              ResumeSection(
                  title="Credentials",
                  kind="credentials",
                  entries=[ResumeEntry(source_block_id=CRED_A.id)],
              )
          ],
      )
      ctx = _ctx([CRED_A], resume, [CRED_A.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1 and violations[0].block_id == "cred-a"


  def test_credential_with_bullet_and_no_label_is_clean(demo_profile_dir: Path) -> None:
      """The `cred-pmp` shape: no org/role/title, one bullet -- must stay clean."""
      profile = load_profile(demo_profile_dir)
      resume = demo_resume()
      ctx = GuardrailContext(
          resume=resume,
          blocks=profile.block_map(),
          selection_ids=frozenset(profile.block_map()),
          extract=demo_extract(),
      )
      assert check_completeness(ctx) == []


  def test_empty_selection_produces_no_violations() -> None:
      resume = _resume([])
      ctx = _ctx(FIVE_ROLES, resume, [])
      assert check_completeness(ctx) == []


  def test_selection_id_not_in_block_map_is_skipped_not_raised() -> None:
      """C-3: the selection names ONLY the unknown id. Naming a real, absent role alongside it would
      (correctly) produce a violation for that role and hide what this test is about."""
      resume = _resume([])
      ctx = _ctx([ROLE_A], resume, ["ghost-not-in-library"])
      assert check_completeness(ctx) == []


  def test_unrenderable_block_is_a_warning_not_an_error() -> None:
      resume = _resume([])
      ctx = _ctx([UNRENDERABLE], resume, [UNRENDERABLE.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      assert violations[0].severity == "warning" and violations[0].block_id == "ghost-role"


  def test_unrenderable_block_leaves_the_report_passed(demo_profile_dir: Path) -> None:
      base = load_profile(demo_profile_dir)
      profile = base.model_copy(update={"blocks": [*base.blocks, UNRENDERABLE]})
      resume = demo_resume()
      report = run_guardrails(resume, profile, [*base.block_map(), UNRENDERABLE.id], demo_extract())
      assert report.passed is True
      assert any(v.rule == RULE_NAME and v.severity == "warning" for v in report.violations)


  def test_attribution_bearing_block_with_bullet_less_entry_is_a_completeness_error() -> None:
      entry = ResumeEntry(
          source_block_id=ATTRIBUTION_ROLE.id,
          org="Globex",
          role="Consultant",
          period="2019-2020",
          bullets=[],
      )
      ctx = _ctx([ATTRIBUTION_ROLE], _resume([entry]), [ATTRIBUTION_ROLE.id])
      violations = check_completeness(ctx)
      assert len(violations) == 1
      assert violations[0].rule == RULE_NAME and violations[0].block_id == ATTRIBUTION_ROLE.id
      assert "attribution" in violations[0].message


  def test_attribution_phrase_carried_by_the_entry_header_is_not_a_gap() -> None:
      """I-1: `check_attribution` also reads title/org/role, so a bullet-less entry whose header
      carries the phrase satisfies `attribution` -- and must not be failed by `completeness`."""
      entry = ResumeEntry(
          source_block_id=ATTRIBUTION_ROLE.id,
          title="Consultant as part of the Globex Partner Program",
          org="Globex",
          role="Consultant",
          period="2019-2020",
          bullets=[],
      )
      ctx = _ctx([ATTRIBUTION_ROLE], _resume([entry]), [ATTRIBUTION_ROLE.id])
      assert check_completeness(ctx) == []


  def test_attribution_missing_from_a_bulleted_entry_is_left_to_the_attribution_rule() -> None:
      """One violation per defect (C7): with a bullet present, only `attribution` reports it."""
      ctx = _ctx([ATTRIBUTION_ROLE], _resume([_entry(ATTRIBUTION_ROLE)]), [ATTRIBUTION_ROLE.id])
      assert check_completeness(ctx) == []


  def _with_blocks(demo_profile_dir: Path, *extra: Block):  # type: ignore[no-untyped-def]
      base = load_profile(demo_profile_dir)
      return base.model_copy(update={"blocks": [*base.blocks, *extra]})


  def test_restoring_a_dropped_concurrent_side_role_surfaces_a_date_overlap(
      demo_profile_dir: Path,
  ) -> None:
      """Architecture §5.4: a model that dropped the overlapping side role made `date-consistency`
      pass BECAUSE of the omission. Once completeness forces the role back, the overlap is real.
      The fix is `concurrent: true` on the block, not a change to either rule."""
      side = _role("side-role", "Sidecar Labs", "Advisor", "2019-2021", "Advised.")
      profile = _with_blocks(demo_profile_dir, side)
      resume = demo_resume()
      resume.sections[0].entries.append(_entry(side))
      selected = [*profile.block_map()]
      report = run_guardrails(resume, profile, selected, demo_extract())
      assert not any(v.rule == RULE_NAME for v in report.violations)
      assert [v.rule for v in report.violations if v.severity == "error"] == ["date-consistency"]
      assert report.passed is False


  def test_the_same_side_role_flagged_concurrent_is_clean(demo_profile_dir: Path) -> None:
      side = _role("side-role", "Sidecar Labs", "Advisor", "2019-2021", "Advised.", concurrent=True)
      profile = _with_blocks(demo_profile_dir, side)
      resume = demo_resume()
      resume.sections[0].entries.append(_entry(side))
      report = run_guardrails(resume, profile, [*profile.block_map()], demo_extract())
      assert report.passed is True, [v.model_dump() for v in report.violations]


  def test_dropping_that_side_role_is_now_a_completeness_error_not_a_pass(
      demo_profile_dir: Path,
  ) -> None:
      """The other half of the interaction: before this rule the drop passed silently."""
      side = _role("side-role", "Sidecar Labs", "Advisor", "2019-2021", "Advised.", concurrent=True)
      profile = _with_blocks(demo_profile_dir, side)
      report = run_guardrails(demo_resume(), profile, [*profile.block_map()], demo_extract())
      assert [(v.rule, v.block_id) for v in report.violations if v.severity == "error"] == [
          (RULE_NAME, "side-role")
      ]


  def test_completeness_is_unconditional_and_rejected_as_a_configured_rule(
      demo_profile_dir: Path,
  ) -> None:
      assert "completeness" not in RULES
      profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
      report = run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())
      assert report.rules_run == ["provenance", "no-unverified-metrics", "completeness"]
      bad = profile.model_copy(update={"guardrails": [GuardrailRule(rule="completeness")]})
      with pytest.raises(UnknownGuardrailError, match="completeness"):
          run_guardrails(demo_resume(), bad, profile.block_map(), demo_extract())


  def test_completeness_cannot_be_switched_off_by_an_empty_guardrails_table(
      demo_profile_dir: Path,
  ) -> None:
      """The half that protects the user: a bare account still catches a dropped role."""
      profile = load_profile(demo_profile_dir).model_copy(update={"guardrails": []})
      resume = demo_resume()
      resume.sections[0].entries = []
      report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
      assert report.passed is False
      assert [v.block_id for v in report.violations if v.rule == RULE_NAME] == ["acme-data-pm"]


  def test_tune_guardrails_never_emit_completeness(demo_profile_dir: Path) -> None:
      from helpers_docx import build_fixture_docx

      from rhapto.engine.document import parse_docx

      profile = load_profile(demo_profile_dir)
      doc = parse_docx(build_fixture_docx(), "resume.docx")
      report = run_tune_guardrails(doc, [], demo_extract(), profile.guardrails, cover_note=None)
      assert "completeness" not in report.rules_run
      assert all(v.rule != "completeness" for v in report.violations)


  def test_a_duplicated_entry_is_reported_by_two_rules_by_design(demo_profile_dir: Path) -> None:
      """Recorded exception to "one violation per defect" (C7 / AC8 are worded around merge and
      substitution). A block printed twice overlaps itself, so `date-consistency` also errors. That
      rule is not ours to suppress, and both messages are true; this test pins the behaviour so a
      change to either rule is a decision rather than an accident."""
      profile = load_profile(demo_profile_dir)
      resume = demo_resume()
      resume.sections[0].entries.append(resume.sections[0].entries[0].model_copy(deep=True))
      report = run_guardrails(resume, profile, [*profile.block_map()], demo_extract())
      errors = [v.rule for v in report.violations if v.severity == "error"]
      assert errors.count("completeness") == 1
      assert sorted(set(errors)) == ["completeness", "date-consistency"]
  ```

- [ ] **Step 6: Update the existing tests this change breaks or must extend**

  This is where review C-1 lands: `test_registry.py` asserted the old `rules_run`. Also the remedies pin (D-2) and the fake-provider tests (C-2). Exact diff:

  ```diff
  diff --git a/apps/api/tests/api/test_fake_provider_api.py b/apps/api/tests/api/test_fake_provider_api.py
  index 039495c..b8359f6 100644
  --- a/apps/api/tests/api/test_fake_provider_api.py
  +++ b/apps/api/tests/api/test_fake_provider_api.py
  @@ -122,3 +122,4 @@ async def test_a_whole_tailor_run_produces_a_clean_package(
           for entry in section["entries"]
       }
       assert {"acme-data-pm", "side-llm-tool", "cred-pmp"} <= entry_ids
  +    assert "completeness" in package["guardrail_report"]["rules_run"]
  diff --git a/apps/api/tests/api/test_guardrail_remedies.py b/apps/api/tests/api/test_guardrail_remedies.py
  index a2e40e3..87e9c4c 100644
  --- a/apps/api/tests/api/test_guardrail_remedies.py
  +++ b/apps/api/tests/api/test_guardrail_remedies.py
  @@ -24,7 +24,7 @@ from rhapto.engine.guardrails.registry import REMEDIES, remedies_for
   def declared_rule_names() -> set[str]:
       """Every `RULE_NAME` constant in `rhapto.engine.guardrails`, found by walking the package.

  -    Discovered, not listed: a hard-coded list of the six rules would have to be updated by the same
  +    Discovered, not listed: a hard-coded list of the rules would have to be updated by the same
       person who forgot the remedy, so it would not catch them.
       """
       names: set[str] = set()
  @@ -45,10 +45,10 @@ def test_every_rule_has_a_remedy() -> None:
       )


  -def test_the_six_rules_this_build_ships_are_the_ones_expected() -> None:
  -    """Pinned by name as well as by count. Six rules exist; four of them are user-configurable
  -    (`RULES`), and `provenance` and `no-unverified-metrics` run unconditionally. A note saying "only
  -    5 rules exist" is imprecise -- 5 is the typical length of `rules_run`, not the number of rules.
  +def test_the_seven_rules_this_build_ships_are_the_ones_expected() -> None:
  +    """Pinned by name as well as by count. Seven rules exist; four of them are user-configurable
  +    (`RULES`), and `provenance`, `no-unverified-metrics` and `completeness` run unconditionally.
  +    The typical length of `rules_run` is not the number of rules.
       """
       assert declared_rule_names() == {
           "provenance",
  @@ -57,6 +57,7 @@ def test_the_six_rules_this_build_ships_are_the_ones_expected() -> None:
           "date-consistency",
           "attribution",
           "visibility-context",
  +        "completeness",
       }


  diff --git a/apps/api/tests/guardrails/test_registry.py b/apps/api/tests/guardrails/test_registry.py
  index 70f33e0..ae94a5b 100644
  --- a/apps/api/tests/guardrails/test_registry.py
  +++ b/apps/api/tests/guardrails/test_registry.py
  @@ -8,7 +8,7 @@ from rhapto.models.profile.guardrails import GuardrailRule
   from rhapto.profile.loader import load_profile


  -def test_both_unconditional_rules_run_with_no_configured_rules(demo_profile_dir: Path) -> None:
  +def test_all_unconditional_rules_run_with_no_configured_rules(demo_profile_dir: Path) -> None:
       """An account with an empty `guardrails` table still gets BOTH product promises.

       This asserted `["provenance"]` until 2026-09-26, which was the true behaviour and the defect:
  @@ -20,7 +20,7 @@ def test_both_unconditional_rules_run_with_no_configured_rules(demo_profile_dir:
       resume = demo_resume()
       resume.summary.append(bullet("Made up.", "ghost"))
       report = run_guardrails(resume, profile, profile.block_map(), demo_extract())
  -    assert report.rules_run == ["provenance", "no-unverified-metrics"]
  +    assert report.rules_run == ["provenance", "no-unverified-metrics", "completeness"]
       assert report.passed is False and report.violations[0].rule == "provenance"


  @@ -43,9 +43,10 @@ def test_inactive_rules_are_skipped(demo_profile_dir: Path) -> None:
       inactive = [GuardrailRule(rule=r.rule, active=False) for r in profile.guardrails]
       profile = profile.model_copy(update={"guardrails": inactive})
       report = run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())
  -    # The configurable rules obey `active: false`; the two unconditional ones do not appear here
  +    # The configurable rules obey `active: false`; the three unconditional ones do not appear here
       # because of a row, so they cannot be switched off by clearing one.
  -    assert report.rules_run == ["provenance", "no-unverified-metrics"] and report.passed is True
  +    assert report.rules_run == ["provenance", "no-unverified-metrics", "completeness"]
  +    assert report.passed is True


   def test_metrics_cannot_be_switched_off_by_an_inactive_row(demo_profile_dir: Path) -> None:
  @@ -86,7 +87,8 @@ def test_unknown_rule_raises(demo_profile_dir: Path) -> None:
           run_guardrails(demo_resume(), profile, profile.block_map(), demo_extract())


  -def test_registry_has_no_entry_for_either_unconditional_rule() -> None:
  -    """Both promises are run directly by run_guardrails, not looked up from a user's config."""
  +def test_registry_has_no_entry_for_any_unconditional_rule() -> None:
  +    """All three are run directly by run_guardrails, not looked up from a user's config."""
       assert "provenance" not in RULES
       assert "no-unverified-metrics" not in RULES
  +    assert "completeness" not in RULES
  diff --git a/apps/api/tests/unit/test_fake_provider.py b/apps/api/tests/unit/test_fake_provider.py
  index 9e43868..0e07474 100644
  --- a/apps/api/tests/unit/test_fake_provider.py
  +++ b/apps/api/tests/unit/test_fake_provider.py
  @@ -17,6 +17,7 @@ from rhapto.engine.providers.registry import (
   )
   from rhapto.engine.tune import TuneOutput
   from rhapto.models.jd_extract import JDExtract
  +from rhapto.models.profile.blocks import Block
   from rhapto.profile.loader import load_profile
   from rhapto.services.llm import env_llm_config, warn_if_fake_llm

  @@ -159,6 +160,33 @@ async def test_the_composed_resume_passes_every_guardrail(demo_profile_dir: obje
       extract = JDExtract(company="ExampleCo", title="Technical Program Manager")
       report = run_guardrails(resume, profile, selected, extract, cover_note=output.cover_note)
       assert report.passed, [v.model_dump() for v in report.violations]
  +    assert "completeness" in report.rules_run
  +
  +
  +async def test_a_mandatory_block_the_fake_cannot_place_blocks_instead_of_vanishing(
  +    demo_profile_dir: object,
  +) -> None:
  +    """A known-bad input for the check above. An unverified project with a number and no
  +    role/title is one the fake skips (it writes no words of its own and will not risk the
  +    metrics rule); the completeness rule must turn that silence into a blocked report. If this
  +    passes, the guard in the test above proves nothing."""
  +    from rhapto.engine.compose import assemble_resume
  +
  +    base = load_profile(demo_profile_dir)  # type: ignore[arg-type]
  +    trap = Block(
  +        id="trap-project", type="project", org="Independent", content="Shipped to 300 users."
  +    )
  +    profile = base.model_copy(update={"blocks": [*base.blocks, trap]})
  +    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
  +    selected = [b["id"] for b in blocks]
  +    output = await _compose(json.dumps(blocks), selected)
  +    assert "trap-project" not in {e.source_block_id for s in output.sections for e in s.entries}
  +    extract = JDExtract(company="ExampleCo", title="Technical Program Manager")
  +    report = run_guardrails(
  +        assemble_resume(output, profile), profile, selected, extract, cover_note=output.cover_note
  +    )
  +    assert not report.passed
  +    assert [v.block_id for v in report.violations if v.rule == "completeness"] == ["trap-project"]


   async def test_a_period_nested_inside_another_entrys_period_is_skipped_and_recorded(
  ```

- [ ] **Step 7: Update the architecture doc's pipeline description**

  In `docs/requirements-architecture.md` §7 step 4, change `guardrail engine checks provenance, metrics, attribution, dates.` to `guardrail engine checks provenance, metrics, completeness (every selected role, project and credential appears), attribution, dates.`

- [ ] **Step 8: Run the new and affected tests**

  Run: `cd apps/api && uv run pytest tests/guardrails tests/unit/test_fake_provider.py tests/golden tests/api/test_guardrail_remedies.py -q`
  Expected: all pass. `tests/golden/test_golden.py` passes unchanged: all three cases cite all four demo blocks, and the project/credential entries satisfy the identity clauses.

  **Prove the wiring, by mutation (plan-review-2, Minor 1).** `rules_run` gains `completeness` even if nothing calls the rule, so the `rules_run` assertions prove nothing about execution. Temporarily delete the line `violations.extend(check_completeness(ctx))` from `run_guardrails`, run the same command, and confirm it **fails** (verified: 5 tests at this commit, among them `test_a_mandatory_block_the_fake_cannot_place_blocks_instead_of_vanishing`, `test_completeness_cannot_be_switched_off_by_an_empty_guardrails_table` and `test_dropping_that_side_role_is_now_a_completeness_error_not_a_pass`); then `git checkout -- apps/api/src/rhapto/engine/guardrails/registry.py`. If nothing fails, the tests do not prove the rule runs; stop.

  Second check, for the fake-provider tests only: temporarily restore the pre-1b fixture (`git show 2026039:profile.example/blocks.yaml > profile.example/blocks.yaml`), re-run `tests/unit/test_fake_provider.py`, and confirm `test_every_mandatory_block_of_the_demo_profile_gets_an_entry` and `test_the_composed_resume_passes_every_guardrail` **fail** (the trap test also fails there, but only because the old fixture adds extra violations, which is why it is *not* the wiring proof); then `git checkout -- profile.example/blocks.yaml`.

- [ ] **Step 9: Audit the tests this rule can reach but the laptop cannot run**

  `tests/api/`, `tests/db/` and much of `tests/unit/test_worker_tasks.py` skip locally. Every one that tailors scripts `helpers.good_output()`, whose entries cite all four `profile.example` blocks, against an `imported_profile` whose selection is all four (there is no `bases.yaml`, so the default base takes every block, and `select_blocks` has no score cutoff). Re-check with `git grep -n "good_output\|default_tailor_script\|fake_llm" -- apps/api/tests` that no test scripts a compose output missing a mandatory block; list any hit in the task report. Nothing was found at `d96015a`; CI is the proof.

- [ ] **Step 10: Format and gate**

  ```
  cd apps/api
  uv run ruff format .        # commit whatever it changes (review I-2)
  uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
  ```
  Report per "CI facts". Suites run locally: `tests/guardrails`, `tests/golden`, `tests/unit/test_fake_provider.py`, `tests/api/test_guardrail_remedies.py` (pure; runs locally despite its directory). **CI-only:** `tests/api/test_fake_provider_api.py`, and every other DB-dependent test that tailors (Step 9).

- [ ] **Step 11: Commit**

  ```bash
  git add apps/api/src/rhapto/engine/guardrails/completeness.py \
          apps/api/src/rhapto/engine/guardrails/base.py \
          apps/api/src/rhapto/engine/guardrails/entities.py \
          apps/api/src/rhapto/engine/guardrails/registry.py \
          apps/api/tests/guardrails/test_completeness.py \
          apps/api/tests/guardrails/test_registry.py \
          apps/api/tests/api/test_guardrail_remedies.py \
          apps/api/tests/unit/test_fake_provider.py \
          apps/api/tests/api/test_fake_provider_api.py \
          docs/requirements-architecture.md
  git commit -m "feat(guardrails): add unconditional completeness rule (Phase 1)"
  ```

---

### Task 2: Repair loop — instructions that restore, a budget guard that can't crash, and a result that remembers the first report

**Advances AC:** 6, 8 (indirectly, by making the repair prompt consistent with "never delete"); architecture conditions C1, C2; review I-3 (plumbing).

**Files:**
- Modify: `apps/api/src/rhapto/engine/repair.py` (`REPAIR_INSTRUCTIONS`)
- Modify: `apps/api/src/rhapto/engine/pipeline.py` (`TailorResult` gains two fields; blocks-branch **and tune-branch** repair: guard `budget.before_call()`)
- Modify: `apps/api/tests/unit/test_repair.py` (instructions-content test)
- Modify: `apps/api/tests/unit/test_pipeline.py` (replace the budget-exhaustion-during-repair test; add pipeline-level completeness tests; assert the new result fields)

**Interfaces:**
- Consumes: `repair(previous, report, system, llm) -> tuple[ComposeOutput, TokenUsage]` (signature unchanged); `CallBudget.before_call()` (raises `LLMBudgetExceeded`, defined in `pipeline.py` itself, so no new import), `CallBudget.after_call(usage)`.
- Produces: `REPAIR_INSTRUCTIONS: str` (content changes); `TailorResult.pre_repair_report: GuardrailReport | None = None` (the first compose's report, set only when it failed) and `TailorResult.repaired: bool = False` (true only when a repair call actually returned an output). Both default so every existing constructor call and consumer is unchanged (`TailorResult(` is constructed in `pipeline.py` only; `worker/tasks.py` and `services/packaging.py` read `.package`/`.docx`/`.selection`). Blocks mode only — the tune branch leaves the defaults. `tailor()`'s behaviour on an exhausted budget during repair changes from *raise* to *return a blocked package* (C2).

**A claim in the architecture that does not match the code:** architecture §4.2 suggests referencing `<selected_block_ids>` in the new repair instructions. Verified against `engine/repair.py` and `engine/compose.py`: the repair call's `system` is `build_system_blocks(profile, track, selection)`, which contains `<blocks>` (`compose.py:100`) but **not** `<selected_block_ids>` — that tag exists only in `build_user_message` (`compose.py:113`), which repair does not send. The instructions therefore reference `<blocks>`, and rely on each `completeness` violation's message already naming the block id, org, role and period (Task 1's `_describe`), which `repair()` serialises as `- {path} [{rule}]: {message}`.

- [ ] **Step 1: Write the tests first (this diff includes them all)**

  ```diff
  diff --git a/apps/api/tests/unit/test_pipeline.py b/apps/api/tests/unit/test_pipeline.py
  index 8ca3b72..570c0e2 100644
  --- a/apps/api/tests/unit/test_pipeline.py
  +++ b/apps/api/tests/unit/test_pipeline.py
  @@ -51,6 +51,20 @@ def cover_note_metric_output() -> dict[str, Any]:
       return output


  +def missing_role_output() -> dict[str, Any]:
  +    """Drops the acme-data-pm entry entirely -- the adversarial case this project targets."""
  +    output = good_output()
  +    output["sections"][0]["entries"] = []
  +    return output
  +
  +
  +def repair_drops_credential_output() -> dict[str, Any]:
  +    """A 'repair' that fixes the role but drops the credential instead -- must still block."""
  +    output = good_output()
  +    output["sections"][2]["entries"] = []
  +    return output
  +
  +
   def test_call_budget() -> None:
       budget = CallBudget(max_calls=2)
       budget.before_call()
  @@ -91,6 +105,8 @@ async def test_malformed_compose_is_retried_within_the_budget(profile: Profile)
       result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
       assert result.package.status == "draft" and result.package.llm_calls == 3
       assert len(llm.calls) == 3
  +    # I-3: three calls and a draft, but the third was a malformed-output retry, not a repair.
  +    assert result.pre_repair_report is None and result.repaired is False


   async def test_malformed_compose_twice_raises_instead_of_a_fourth_call(profile: Profile) -> None:
  @@ -111,6 +127,8 @@ async def test_repair_path_uses_three_calls_and_passes(profile: Profile) -> None
       llm = FakeLLMProvider([demo_extract(), bad_output(), good_output()])
       result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
       assert result.package.status == "draft" and result.package.llm_calls == 3
  +    assert result.repaired is True
  +    assert result.pre_repair_report is not None and not result.pre_repair_report.passed
       repair_call = llm.calls[2]
       assert "25%" in repair_call.messages[0].content and repair_call.output_schema is ComposeOutput
       assert repair_call.system == llm.calls[1].system  # same cached system blocks as compose
  @@ -121,6 +139,7 @@ async def test_usage_reaches_the_package(profile: Profile) -> None:
       llm = FakeLLMProvider([demo_extract(), good_output()])
       result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
       assert result.package.llm_calls == 2
  +    assert result.pre_repair_report is None and result.repaired is False
       assert result.package.usage.input_tokens == 20
       assert result.package.usage.output_tokens == 10

  @@ -155,17 +174,24 @@ async def test_unrepairable_output_is_blocked(profile: Profile) -> None:
       )  # still rendered for review; the orphan check is the only hard stop


  -async def test_budget_exceeded_raises_before_fourth_call(profile: Profile) -> None:
  +async def test_budget_exceeded_during_repair_yields_a_blocked_package_not_a_crash(
  +    profile: Profile,
  +) -> None:
  +    """C2: an exhausted budget on the repair path must not raise -- it must return the blocked
  +    draft, exactly like a MalformedOutputError on the same path already does."""
       llm = FakeLLMProvider([demo_extract(), bad_output(), bad_output()])
  -    with pytest.raises(LLMBudgetExceeded):
  -        await tailor(
  -            TailorRequest(jd_text=JD),
  -            profile,
  -            llm,
  -            FakeEmbeddingProvider(),
  -            budget=CallBudget(max_calls=2),
  -        )
  +    result = await tailor(
  +        TailorRequest(jd_text=JD),
  +        profile,
  +        llm,
  +        FakeEmbeddingProvider(),
  +        budget=CallBudget(max_calls=2),
  +    )
  +    assert result.package.status == "blocked" and result.package.llm_calls == 2
       assert len(llm.calls) == 2
  +    assert not result.package.guardrail_report.passed
  +    # The first report is kept, and the result says no repair ever ran.
  +    assert result.pre_repair_report is not None and result.repaired is False


   async def test_orphan_bullet_blocks_without_docx(profile: Profile) -> None:
  @@ -219,6 +245,34 @@ async def test_cover_note_metric_blocks_even_when_the_resume_is_clean(profile: P
       assert "37%" in violations[0].message


  +async def test_missing_role_block_triggers_repair_and_restoring_it_passes(
  +    profile: Profile,
  +) -> None:
  +    llm = FakeLLMProvider([demo_extract(), missing_role_output(), good_output()])
  +    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
  +    assert result.package.status == "draft" and result.package.llm_calls == 3
  +    assert result.package.guardrail_report.passed
  +    assert result.repaired is True
  +    assert result.pre_repair_report is not None
  +    first = [v for v in result.pre_repair_report.violations if v.rule == "completeness"]
  +    assert [v.block_id for v in first] == ["acme-data-pm"]
  +    # The violation itself, not REPAIR_INSTRUCTIONS' own mention of the word, must reach the model.
  +    sent = llm.calls[2].messages[0].content
  +    assert "[completeness]" in sent and "was selected but does not appear in Experience" in sent
  +    assert "acme-data-pm" in sent
  +
  +
  +async def test_repair_that_drops_a_different_block_is_blocked_with_the_post_repair_report(
  +    profile: Profile,
  +) -> None:
  +    llm = FakeLLMProvider([demo_extract(), missing_role_output(), repair_drops_credential_output()])
  +    result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
  +    assert result.package.status == "blocked" and result.package.llm_calls == 3
  +    violations = result.package.guardrail_report.violations
  +    assert any(v.rule == "completeness" and v.block_id == "cred-pmp" for v in violations)
  +    assert not any(v.block_id == "acme-data-pm" for v in violations)  # the role was restored
  +
  +
   # --- tune mode -------------------------------------------------------------------------------

   CLEAN_BULLET = "Led the Snowflake migration for 12 teams, reducing warehouse cost 30%."
  @@ -314,6 +368,22 @@ async def test_tune_mode_malformed_repair_keeps_the_blocked_draft(profile: Profi
       assert not result.package.guardrail_report.passed


  +async def test_tune_mode_budget_exhausted_before_repair_yields_a_blocked_package(
  +    profile: Profile,
  +) -> None:
  +    doc, data = _source()
  +    llm = FakeLLMProvider([demo_extract(), tune_output(DIRTY_BULLET), tune_output(CLEAN_BULLET)])
  +    result = await tailor(
  +        tune_request(doc, data),
  +        profile,
  +        llm,
  +        FakeEmbeddingProvider(),
  +        budget=CallBudget(max_calls=2),
  +    )
  +    assert result.package.status == "blocked" and result.package.llm_calls == 2
  +    assert len(llm.calls) == 2 and result.docx == b""
  +
  +
   async def test_tune_mode_regeneration_passes_previous_edits(profile: Profile) -> None:
       doc, data = _source()
       first = await tailor(
  diff --git a/apps/api/tests/unit/test_repair.py b/apps/api/tests/unit/test_repair.py
  index 668945d..a4eac60 100644
  --- a/apps/api/tests/unit/test_repair.py
  +++ b/apps/api/tests/unit/test_repair.py
  @@ -3,7 +3,7 @@ from helpers import demo_resume
   from rhapto.engine.compose import ComposeOutput
   from rhapto.engine.providers.fake import FakeLLMProvider
   from rhapto.engine.providers.llm import SystemBlock
  -from rhapto.engine.repair import repair
  +from rhapto.engine.repair import REPAIR_INSTRUCTIONS, repair
   from rhapto.models.guardrail_report import GuardrailReport, Violation


  @@ -38,3 +38,11 @@ async def test_repair_sends_violations_and_previous_output() -> None:
           and "25%" in body
           and "<previous_output>" in body
       )
  +
  +
  +def test_repair_instructions_no_longer_tell_the_model_to_drop_bullets() -> None:
  +    """C1: shipping the detector while the repair prompt still says 'drop bullets' spends an LLM
  +    call teaching the model to commit the offence again."""
  +    assert "drop bullets" not in REPAIR_INSTRUCTIONS
  +    assert "completeness" in REPAIR_INSTRUCTIONS
  +    assert "never" in REPAIR_INSTRUCTIONS.lower()
  ```

  What each new/changed test proves: the instructions no longer say "drop bullets" (C1); an exhausted budget during repair returns a blocked package and `repaired is False` (C2); a dropped role triggers repair, the **violation line** (`[completeness] ... was selected but does not appear in Experience`) reaches the model — asserted on the violation text, not on the word "completeness", which `REPAIR_INSTRUCTIONS` itself contains and would make the assertion vacuous; a repair that drops the credential instead is blocked with the post-repair report; the malformed-output retry (three calls, `draft`) is **not** a repair (I-3); the tune branch has the same budget guard.

- [ ] **Step 2: Run them and confirm they fail**

  Run: `cd apps/api && uv run pytest tests/unit/test_repair.py tests/unit/test_pipeline.py -q`
  Expected: FAIL — the instructions test (current text contains "drop bullets" and no "completeness"), the budget tests (`LLMBudgetExceeded` propagates), and every assertion on `result.repaired` / `result.pre_repair_report` (`AttributeError`).

- [ ] **Step 3: Apply the source changes**

  ```diff
  diff --git a/apps/api/src/rhapto/engine/pipeline.py b/apps/api/src/rhapto/engine/pipeline.py
  index a20579e..a67e50e 100644
  --- a/apps/api/src/rhapto/engine/pipeline.py
  +++ b/apps/api/src/rhapto/engine/pipeline.py
  @@ -57,6 +57,13 @@ class TailorResult(BaseModel):
       docx: bytes
       selection: Selection
       edits: list[Edit] = Field(default_factory=list)
  +    # Blocks mode only. `package.guardrail_report` is always the POST-repair report, so on its own
  +    # a model that dropped a role and repaired it looks the same as one that never dropped
  +    # anything. `pre_repair_report` is the first compose's report, set only when that report
  +    # failed; `repaired` is True only when a repair call actually returned an output (not when
  +    # the budget or a malformed answer skipped it). Phase 4 measurement reads both.
  +    pre_repair_report: GuardrailReport | None = None
  +    repaired: bool = False


   async def _notify(on_step: ProgressCallback | None, step: str) -> None:
  @@ -168,23 +175,35 @@ async def tailor(
           resume, profile, selection.block_ids, jd_extract, cover_note=output.cover_note
       )

  +    pre_repair_report: GuardrailReport | None = None
  +    was_repaired = False
       if not report.passed:
  +        pre_repair_report = report
           await _notify(on_step, "repair")
  -        budget.before_call()
           try:
  -            repaired, usage = await repair(
  -                output, report, build_system_blocks(profile, track, selection), llm
  -            )
  -        except MalformedOutputError:
  -            # The retry budget is spent; keep the blocked draft so the human sees the report.
  -            budget.after_call(TokenUsage())
  +            budget.before_call()
  +        except LLMBudgetExceeded:
  +            pass  # no calls left; keep the blocked draft so the human sees the report
           else:
  -            budget.after_call(usage)
  -            output = repaired
  -            resume = assemble_resume(output, profile)
  -            report = run_guardrails(
  -                resume, profile, selection.block_ids, jd_extract, cover_note=output.cover_note
  -            )
  +            try:
  +                fixed, usage = await repair(
  +                    output, report, build_system_blocks(profile, track, selection), llm
  +                )
  +            except MalformedOutputError:
  +                # The retry budget is spent; keep the blocked draft so the human sees the report.
  +                budget.after_call(TokenUsage())
  +            else:
  +                budget.after_call(usage)
  +                output = fixed
  +                was_repaired = True
  +                resume = assemble_resume(output, profile)
  +                report = run_guardrails(
  +                    resume,
  +                    profile,
  +                    selection.block_ids,
  +                    jd_extract,
  +                    cover_note=output.cover_note,
  +                )

       await _notify(on_step, "render")
       try:
  @@ -204,7 +223,13 @@ async def tailor(
           budget,
           llm,
       )
  -    return TailorResult(package=package, docx=docx, selection=selection)
  +    return TailorResult(
  +        package=package,
  +        docx=docx,
  +        selection=selection,
  +        pre_repair_report=pre_repair_report,
  +        repaired=was_repaired,
  +    )


   async def _tune_branch(
  @@ -236,19 +261,23 @@ async def _tune_branch(

       if not report.passed:
           await _notify(on_step, "repair")
  -        budget.before_call()
           try:
  -            repaired, usage = await tune_repair(output, report, build_tune_system_blocks(doc), llm)
  -        except MalformedOutputError:
  -            # The retry budget is spent; keep the blocked draft so the human sees the report.
  -            budget.after_call(TokenUsage())
  +            budget.before_call()
  +        except LLMBudgetExceeded:
  +            pass  # no calls left; keep the blocked draft so the human sees the report
           else:
  -            budget.after_call(usage)
  -            output = repaired
  -            edits = to_edits(doc, output)
  -            report = run_tune_guardrails(
  -                doc, edits, jd_extract, profile.guardrails, cover_note=output.cover_note
  -            )
  +            try:
  +                fixed, usage = await tune_repair(output, report, build_tune_system_blocks(doc), llm)
  +            except MalformedOutputError:
  +                # The retry budget is spent; keep the blocked draft so the human sees the report.
  +                budget.after_call(TokenUsage())
  +            else:
  +                budget.after_call(usage)
  +                output = fixed
  +                edits = to_edits(doc, output)
  +                report = run_tune_guardrails(
  +                    doc, edits, jd_extract, profile.guardrails, cover_note=output.cover_note
  +                )

       await _notify(on_step, "render")
       # Unlike blocks mode there is no safe partial artefact: the writer edits the user's own file
  diff --git a/apps/api/src/rhapto/engine/repair.py b/apps/api/src/rhapto/engine/repair.py
  index df97c77..78874c0 100644
  --- a/apps/api/src/rhapto/engine/repair.py
  +++ b/apps/api/src/rhapto/engine/repair.py
  @@ -6,8 +6,15 @@ from rhapto.models.guardrail_report import GuardrailReport

   REPAIR_INSTRUCTIONS = """Your previous output violated the guardrails listed in <violations>. Return the complete
   corrected output. Fix every violation: remove any number you cannot source verbatim from the cited block, restore
  -exact organisation names, titles, and periods, add missing attribution phrases, and drop bullets whose block is
  -not allowed. Do not introduce new block ids."""
  +exact organisation names, titles, and periods, and add missing attribution phrases. If a bullet cites a block id
  +that is not in <blocks>, remove only that bullet -- never the entry it was in, and never the block id itself.
  +
  +A "completeness" violation names a block that must have exactly one entry in its own section (role -> experience,
  +project -> projects, credential -> credentials), with org, role/title and period copied verbatim from that
  +block's fields in <blocks>. Never resolve ANY violation by deleting an entry, a section, or a block id: the
  +corrected document must keep an entry for every block id it already cites, plus a new entry for every block id
  +a completeness violation names. If the corrected document would be too long, shorten a low-priority entry to a
  +single bullet -- never remove the entry. Do not introduce new block ids."""


   async def repair(
  ```

  Notes for the coder. `LLMBudgetExceeded` is the class defined at the top of `pipeline.py`; nothing to import. The local `repaired` in the old blocks-branch code is renamed `fixed` because `repaired` would now read as the flag. In blocks mode `pre_repair_report` is set whenever the first report failed, even if the budget then prevented the repair — `repaired` is what distinguishes those two outcomes.

- [ ] **Step 4: Run the tests again**

  Run: `cd apps/api && uv run pytest tests/unit/test_repair.py tests/unit/test_pipeline.py tests/guardrails tests/golden -q`
  Expected: all pass. `LLMBudgetExceeded` is still imported and still used in `test_pipeline.py` (`test_call_budget`), so removing the old test causes no unused-import failure (`ruff check` verified). No test named `test_budget_exceeded_raises_before_fourth_call` remains.

- [ ] **Step 5: Format and gate**

  ```
  cd apps/api
  uv run ruff format .        # commit whatever it changes (review I-2)
  uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
  ```
  Report per "CI facts": suites run locally = `tests/unit/test_repair.py`, `tests/unit/test_pipeline.py`, `tests/guardrails`, `tests/golden`. **CI-only:** any DB-dependent test that reaches `tailor()` (`tests/api/test_tailor_api.py`, `test_trial_limit_*`, `tests/unit/test_worker_tasks.py` DB cases) — `TailorResult`'s two new fields default, so none should change; CI confirms.

- [ ] **Step 6: Commit**

  ```bash
  git add apps/api/src/rhapto/engine/repair.py apps/api/src/rhapto/engine/pipeline.py \
          apps/api/tests/unit/test_repair.py apps/api/tests/unit/test_pipeline.py
  git commit -m "fix(engine): repair prompt restores instead of dropping; repair budget guard; keep the first report (Phase 2, C1/C2, I-3)"
  ```

---

### Task 3: Prevent the drop at the source; fix the dead click in the review UI

**Advances AC:** 4 (usability of the message the user sees); spec §3 (two-page tension); architecture §8.3.

**Files:**
- Modify: `apps/api/src/rhapto/engine/prompts/compose.py` (`COMPOSE_RULES`)
- Modify: `apps/api/tests/unit/test_compose.py`
- Modify: `apps/web/src/components/review/GuardrailPanel.tsx`
- Modify: `apps/web/src/components/review/GuardrailPanel.test.tsx`

**Interfaces:**
- Consumes: `COMPOSE_RULES: str` (content only; still consumed unchanged by `build_system_blocks`, `compose.py:101`). `GuardrailReport`/`Violation` types from `@/lib/api/queries` (`Violation.path: string`, `block_id`, `severity`) and the `remedies` prop — all unchanged, no schema change.
- Produces: `GuardrailPanel({ report, remedies?, onSelect })` — **same props, same `onSelect(path)` contract**; a row whose `path` starts with `selection.` renders as a plain block (still showing severity, `block_id` and remedy) instead of a button. Nothing else about the component changes.

**A user-visible consequence in this UI that the owner should know (plan-review-2, Minor 2):** in the review editor, removing the only bullet of a label-less credential (the demo's `cred-pmp`: no org, role or title) is one click, and the saved version now fails `completeness` (`_compact_entry` would render nothing for it) and, after Task 4, has no DOCX. The message names the credential and this panel now shows it as plain text with its remedy. That is the correct outcome and no code here changes it; it is listed so it is not a surprise.

**Why this task was rewritten (D-3).** The 2026-09-25 plan replaced the whole violation list. `main`'s panel has since gained severity styling, the `block_id` chip and the per-rule remedy line (`0b35f3f`), so that replacement would have deleted them, and its `startsWith("sections[")` test would have de-linked tune-mode `edits[i]`, `summary[i]` and `cover_note` rows. The change below is a three-hunk edit that special-cases only the one synthetic prefix this project introduces.

- [ ] **Step 1: Add the prevention rule to `COMPOSE_RULES`, and its test**

  The rule tells the model an entry with an attribution phrase keeps one bullet (I-1: the two rules must not give the composer contradictory advice). Everything else in the string is untouched; the rule is numbered 6 because rule 5 is the last numbered one.

  ```diff
  diff --git a/apps/api/src/rhapto/engine/prompts/compose.py b/apps/api/src/rhapto/engine/prompts/compose.py
  index f7bdc46..3bcce41 100644
  --- a/apps/api/src/rhapto/engine/prompts/compose.py
  +++ b/apps/api/src/rhapto/engine/prompts/compose.py
  @@ -10,6 +10,10 @@ Hard rules (a validator enforces every one of them and will reject your output):
   3. Copy organisation names, role titles, and periods exactly from the block. Never inflate a title.
   4. If a block has an attribution phrase, every bullet from it must contain that phrase verbatim.
   5. Rephrase and reorder freely to match the job's requirements and keywords. Do not invent experience.
  +6. Every selected role, project, and credential block gets exactly one entry, in its section, citing that
  +   block: role -> Experience, project -> Projects, credential -> Credentials. Never drop an entry to save
  +   space -- if the resume is too long, shorten the least relevant entry to a single bullet instead. (A block
  +   with an attribution phrase keeps one bullet carrying it.)

   Open each achievement bullet with a short label sentence naming what it is, then the detail:
   "Executive decisions. Drove the go/no-go and buy-vs-build decision with the VP Finance..."
  diff --git a/apps/api/tests/unit/test_compose.py b/apps/api/tests/unit/test_compose.py
  index 3221ed8..6ec2e46 100644
  --- a/apps/api/tests/unit/test_compose.py
  +++ b/apps/api/tests/unit/test_compose.py
  @@ -253,3 +253,11 @@ def test_assemble_resume_adds_header(demo_profile_dir: Path) -> None:
           "Led cross-functional delivery of the customer data platform across 4 teams.",
           "acme-data-pm",
       )
  +
  +
  +def test_compose_rules_forbid_dropping_a_selected_entry() -> None:
  +    """Spec §3: completeness wins on existence; length pressure is absorbed by bullet depth,
  +    never by dropping an entry. This is prompt-only -- there is no page-count code anywhere in
  +    the engine, verified against render/templates.py."""
  +    assert "never drop an entry" in COMPOSE_RULES.lower()
  +    assert "attribution phrase keeps one bullet" in COMPOSE_RULES
  ```

- [ ] **Step 2: Run the compose tests**

  Run: `cd apps/api && uv run pytest tests/unit/test_compose.py -q`
  Expected: all pass, including the new test.

- [ ] **Step 3: Fix the dead click in `GuardrailPanel.tsx`, and test it**

  A `completeness` violation's `path` (`selection.block_ids['role-e']`) addresses no node in `ResumeDocument` (`parsePath` returns `{ kind: "unknown" }`), so on the review page a click does nothing. On the job page the same click navigates to the package, which the "Review →" link directly below the panel already does. Only the `selection.` prefix loses the button. Leave the inner spans exactly as they are; only the wrapper changes.

  ```diff
  diff --git a/apps/web/src/components/review/GuardrailPanel.test.tsx b/apps/web/src/components/review/GuardrailPanel.test.tsx
  index 97d1221..5ff5a90 100644
  --- a/apps/web/src/components/review/GuardrailPanel.test.tsx
  +++ b/apps/web/src/components/review/GuardrailPanel.test.tsx
  @@ -108,3 +108,48 @@ describe("GuardrailPanel, what to do about it", () => {
     });
   });

  +
  +describe("GuardrailPanel, a violation that names something absent from the document", () => {
  +  const COMPLETENESS = {
  +    rule: "completeness",
  +    severity: "error" as const,
  +    message: "role block 'role-e' (Vertex Robotics — Founder, 2023-Present) was selected but does not appear in Experience",
  +    path: "selection.block_ids['role-e']",
  +    block_id: "role-e",
  +  };
  +  const COMPLETENESS_REMEDY = "A role, project or credential your profile selected for this job is missing from the resume.";
  +
  +  it("renders a plain row, not a dead button, and keeps the block id and remedy", () => {
  +    render(
  +      <GuardrailPanel
  +        report={{ passed: false, rules_run: ["provenance", "completeness"], violations: [COMPLETENESS] }}
  +        remedies={{ completeness: COMPLETENESS_REMEDY }}
  +        onSelect={vi.fn()}
  +      />,
  +    );
  +    expect(screen.getByText(/does not appear in Experience/i)).toBeInTheDocument();
  +    expect(screen.queryByRole("button", { name: /does not appear in Experience/i })).not.toBeInTheDocument();
  +    expect(screen.getByText("role-e")).toBeInTheDocument();
  +    expect(screen.getByText(COMPLETENESS_REMEDY)).toBeInTheDocument();
  +  });
  +
  +  it("does not take the button away from the paths that do address something", async () => {
  +    // The regression a blanket `startsWith("sections[")` rule would have caused: tune-mode
  +    // violations are `edits[i]`, and both pages route them through onSelect.
  +    const onSelect = vi.fn();
  +    const at = (path: string) => ({ ...ERROR_VIOLATION, message: `problem at ${path}`, path });
  +    render(
  +      <GuardrailPanel
  +        report={{
  +          passed: false,
  +          rules_run: ["tune-scope"],
  +          violations: [at("edits[0]"), at("summary[0]"), at("cover_note"), COMPLETENESS],
  +        }}
  +        onSelect={onSelect}
  +      />,
  +    );
  +    expect(screen.getAllByRole("button")).toHaveLength(3);
  +    await userEvent.setup().click(screen.getByRole("button", { name: /problem at edits\[0\]/ }));
  +    expect(onSelect).toHaveBeenCalledWith("edits[0]");
  +  });
  +});
  diff --git a/apps/web/src/components/review/GuardrailPanel.tsx b/apps/web/src/components/review/GuardrailPanel.tsx
  index eeb3d8d..b7bbb3c 100644
  --- a/apps/web/src/components/review/GuardrailPanel.tsx
  +++ b/apps/web/src/components/review/GuardrailPanel.tsx
  @@ -3,6 +3,15 @@
   import { StatusBadge } from "@/components/ui/StatusBadge";
   import type { GuardrailReport } from "@/lib/api/queries";

  +/**
  + * A `completeness` violation names a block that is ABSENT from the document, so its `path` is
  + * `selection.block_ids['<id>']`: it addresses no node, and a click on it would do nothing on the
  + * review page. Only this prefix is treated as node-less. Every other path stays a button --
  + * `sections[..]`, `summary[..]`, `cover_note`, and a tune-mode `edits[..]`, which the review
  + * page's `scrollToChange` and the job page's `?path=` link both depend on.
  + */
  +const NODELESS_PATH_PREFIX = "selection.";
  +
   /**
    * `remedies` is keyed by rule id and comes from `PackageOut.guardrail_remedies`.
    *
  @@ -36,15 +45,12 @@ export function GuardrailPanel({
               // A warning does not block the package, so it must not be dressed as the thing that did.
               const isError = v.severity === "error";
               const remedy = remedies[v.rule];
  -            return (
  -              <li key={`${v.path}-${i}`}>
  -                <button
  -                  type="button"
  -                  onClick={() => onSelect(v.path)}
  -                  className={`hover-lift w-full rounded-control border border-border border-l-4 bg-surface px-3 py-2.5 text-left text-sm ${
  -                    isError ? "border-l-destructive" : "border-l-fit-mid"
  -                  }`}
  -                >
  +            const hasNode = !v.path.startsWith(NODELESS_PATH_PREFIX);
  +            const rowClass = `w-full rounded-control border border-border border-l-4 bg-surface px-3 py-2.5 text-left text-sm ${
  +              isError ? "border-l-destructive" : "border-l-fit-mid"
  +            }`;
  +            const body = (
  +              <>
                     <span className="flex flex-wrap items-center gap-1.5">
                       <span
                         className={`inline-flex items-center rounded-chip px-2 py-0.5 font-mono text-xs font-medium ${
  @@ -61,7 +67,17 @@ export function GuardrailPanel({
                     <span className="mt-1.5 block text-foreground">{v.message}</span>
                     <span className="mt-0.5 block font-mono text-xs text-muted-foreground">{v.path}</span>
                     {remedy ? <span className="mt-1.5 block text-xs text-muted-foreground">{remedy}</span> : null}
  -                </button>
  +              </>
  +            );
  +            return (
  +              <li key={`${v.path}-${i}`}>
  +                {hasNode ? (
  +                  <button type="button" onClick={() => onSelect(v.path)} className={`hover-lift ${rowClass}`}>
  +                    {body}
  +                  </button>
  +                ) : (
  +                  <div className={rowClass}>{body}</div>
  +                )}
                 </li>
               );
             })}
  ```

  The two new tests: a `completeness` row renders as text (severity, `role-e`, remedy visible) with no button; and `edits[0]`, `summary[0]` and `cover_note` rows are **still buttons** and `edits[0]` still calls `onSelect` — the regression a blanket prefix rule would have caused. The three pre-existing test groups are unchanged and still pass.

- [ ] **Step 4: Run the web tests, typecheck, lint**

  Run, from `apps/web`:
  ```
  pnpm test -- GuardrailPanel
  pnpm typecheck
  pnpm lint
  ```
  Expected: all clean (verified: 8 passed for that file; `tsc --noEmit` and `eslint` clean). CI's `web` job runs the whole `pnpm test`; run it once here too and report the count.

- [ ] **Step 5: Format and gate (API side)**

  ```
  cd apps/api
  uv run ruff format .        # commit whatever it changes (review I-2)
  uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
  ```
  Report per "CI facts". Suites run locally: `tests/unit/test_compose.py`; web `pnpm test`, `pnpm typecheck`, `pnpm lint`. **CI-only:** the API's DB suites (unaffected by this task, but CI is the gate).

- [ ] **Step 6: Commit**

  ```bash
  git add apps/api/src/rhapto/engine/prompts/compose.py apps/api/tests/unit/test_compose.py \
          apps/web/src/components/review/GuardrailPanel.tsx \
          apps/web/src/components/review/GuardrailPanel.test.tsx
  git commit -m "feat: prevent entry drops at compose time; no dead click on node-less violation paths (Phase 3)"
  ```

---

### Task 4: No DOCX for a failing report, in any mode (Phase 5)

**Advances AC:** 5; review I-5; plan-review-2 I-1 (stored files).

**Files:**
- Modify: `apps/api/src/rhapto/engine/pipeline.py` (blocks-mode render step in `tailor()`)
- Modify: `apps/api/src/rhapto/api/routers/packages.py` (`_edited_blocks_version`; **serve-time gate** in `package_file` and `download_package`; the zip's blocked-note wording)
- Modify: `apps/api/src/rhapto/services/storage.py` (`build_zip(..., include_documents: bool = True)`)
- Modify: `apps/api/src/rhapto/cli/main.py` (the "PDF skipped" message — **review I-5**)
- Modify: `apps/api/tests/unit/test_pipeline.py` (flip `test_unrepairable_output_is_blocked`; extend two tests)
- Modify: `apps/api/tests/api/test_packages_api.py` (flip `test_patch_with_invented_metric_is_blocked`; **rewrite `test_blocked_package_download_is_unmistakable`**; **DB tests, CI-only**)
- Create: `apps/api/tests/unit/test_package_serving.py` (the serve-time gate, no database)
- Modify: `apps/api/tests/unit/test_cli.py` (`test_tailor_blocked_exits_3`)

**Interfaces:**
- Consumes: `GuardrailReport.passed: bool`; `render_docx(resume, blocks, style) -> bytes`; `OrphanBulletError`. No signature changes.
- Produces: `TailorResult.docx: bytes` and `EditedVersion.docx: bytes` are `b""` whenever the corresponding `GuardrailReport.passed` is `False`, in blocks mode as well as tune mode. `cli/main.py:write_package` (`if result.docx:`), `services/packaging.py:save_package` (`if docx:`) and `worker/tasks.py`'s `render_package_pdf` (returns early when `docx_path is None`) already treat empty bytes as "nothing to write" and need no change — re-verified at `d96015a`, and unchanged on `main` `2026039` (`git diff --stat d96015a..2026039 -- apps/api` is empty). `PackageStorage.build_zip` gains `include_documents` (default `True`, so every existing caller is unchanged).

**The fourth site.** The architecture describes the bug as living in "pipeline, CLI, worker". CLI and worker already gate on non-empty bytes, but `_edited_blocks_version` (backing `PATCH /packages/{id}` for a hand-edited blocks-mode resume) has the identical unconditional-render bug, pinned by `test_packages_api.py:102-111`. Without it AC5 is false: a reviewer could get a real DOCX for a blocked package by round-tripping one hand edit. Every other DOCX-asserting test was audited (`git grep -n "has_docx\|docx\[:2\]\|docx_path" -- apps/api/tests`): the sites that assert a non-empty DOCX are all `draft` packages (`test_packages_api.py:42,90,255`, `test_worker_tasks.py:139,529`, `test_pipeline.py:82,282`); the two `blocked` ones (`test_packages_api.py:120,292`) already assert `False`; the pinned ones are the three flipped here **plus a fourth both reviews missed**: `test_blocked_package_download_is_unmistakable` (`test_packages_api.py:192-212`) builds a blocked package by the same hand edit and asserts `GET .../files/resume.docx` is `200`. After this task that package has no file (404), so the test would fail in CI; it is rewritten below around the serve-time gate.

**The stored-file gap (plan-review-2, I-1).** Phase 5 stops *new* blocked packages from writing a DOCX. Every blocked blocks-mode package written before it has a real DOCX (and possibly PDF) on disk, on the deployed server too, and two paths serve any file that exists: `package_file` and `download_package` → `build_zip`. The owner's rule ("a failing report must not persist a DOCX") and AC5 are only true of the filesystem if those refuse too. Decision: **refuse at serve time, delete nothing.** `package_file` returns 409 with a `detail` for a blocked package whose file exists; `download_package` still returns the zip (a tested, deliberate behaviour: the unmistakable blocked download) but `include_documents=passed` leaves the documents out. 409 rather than 404 and *after* the existence check, so an absent file still answers 404 (see Revision 2 for the reasoning and the web client's handling). `has_docx` on `PackageOut` is left as is (it reports what is stored), so for a legacy blocked row the buttons stay enabled and the click shows the 409's `detail` as a toast. A cleanup that deletes the files is a Delivery-step decision for the owner and is not in this plan.

**Behaviour note (U-4):** the message change is needed because the CLI's `PDF skipped: ... (provenance violation; ...)` fires on *any* empty DOCX, so after this task it would blame provenance for a `completeness` or `no-unverified-metrics` failure.

- [ ] **Step 1: Flip the pinned tests and add the new assertions first**

  ```diff
  diff --git a/apps/api/tests/api/test_packages_api.py b/apps/api/tests/api/test_packages_api.py
  index 63ec77c..772fb99 100644
  --- a/apps/api/tests/api/test_packages_api.py
  +++ b/apps/api/tests/api/test_packages_api.py
  @@ -9,6 +9,7 @@ from helpers_docx import build_fixture_docx

   from rhapto.engine.compose import AnswerItem, ComposeOutput
   from rhapto.engine.tune import ProposedEdit, TuneOutput
  +from rhapto.services.storage import PackageStorage

   JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3

  @@ -108,7 +109,7 @@ async def test_patch_with_invented_metric_is_blocked(client: httpx.AsyncClient,
       new = (await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})).json()
       assert new["status"] == "blocked"
       assert {v["rule"] for v in new["guardrail_report"]["violations"]} == {"no-unverified-metrics"}
  -    assert new["has_docx"] is True  # rendered for review; only orphan bullets suppress the DOCX
  +    assert new["has_docx"] is False  # owner, 2026-09-25: a failing report never persists a DOCX


   @pytest.mark.usefixtures("imported_profile")
  @@ -190,9 +191,9 @@ async def test_package_list_and_named_downloads(client: httpx.AsyncClient, fake_

   @pytest.mark.usefixtures("imported_profile")
   async def test_blocked_package_download_is_unmistakable(
  -    client: httpx.AsyncClient, fake_llm
  +    client: httpx.AsyncClient, fake_llm, storage: PackageStorage
   ) -> None:  # type: ignore[no-untyped-def]
  -    """A blocked package stays downloadable, but the transport and the zip both say so."""
  +    """A blocked package's zip says so, and no resume document leaves the server for it."""
       _, package_id = await _tailored(client, fake_llm)
       resume = (await client.get(f"/api/v1/packages/{package_id}")).json()["resume"]
       resume["sections"][0]["entries"][0]["bullets"][1] = bullet(
  @@ -200,16 +201,20 @@ async def test_blocked_package_download_is_unmistakable(
       ).model_dump()
       new = (await client.patch(f"/api/v1/packages/{package_id}", json={"resume": resume})).json()
       assert new["status"] == "blocked"
  +    # A row stored before Phase 5 has a DOCX on disk (rendered "for review"). Put one there:
  +    # the serving paths must refuse it themselves, not rely on the writer having skipped it.
  +    storage.write_docx(new["id"], b"PK legacy docx")

       download = await client.get(f"/api/v1/packages/{new['id']}/download")
       assert download.status_code == 200
       assert download.headers["x-rhapto-guardrails"] == "blocked"
       with zipfile.ZipFile(io.BytesIO(download.content)) as zf:
           assert "GUARDRAILS-BLOCKED.md" in zf.namelist()
  +        assert "resume.docx" not in zf.namelist()
           note = zf.read("GUARDRAILS-BLOCKED.md").decode()
       assert "no-unverified-metrics" in note and "25%" in note
       docx = await client.get(f"/api/v1/packages/{new['id']}/files/resume.docx")
  -    assert docx.status_code == 200 and docx.headers["x-rhapto-guardrails"] == "blocked"
  +    assert docx.status_code == 409 and "guardrails" in docx.json()["detail"]


   # --- tune mode ---------------------------------------------------------------------------------
  diff --git a/apps/api/tests/unit/test_cli.py b/apps/api/tests/unit/test_cli.py
  index dd128d5..9c48f71 100644
  --- a/apps/api/tests/unit/test_cli.py
  +++ b/apps/api/tests/unit/test_cli.py
  @@ -102,7 +102,11 @@ def test_tailor_blocked_exits_3(workspace: Path, monkeypatch: pytest.MonkeyPatch
       )
       assert result.exit_code == 3, result.output
       assert "no-unverified-metrics" in result.output and "25%" in result.output
  -    assert (workspace / "out" / "exampleco-data-platform-program-manager" / "package.json").exists()
  +    target = workspace / "out" / "exampleco-data-platform-program-manager"
  +    assert (target / "package.json").exists()
  +    assert not (target / "resume.docx").exists()
  +    # I-5: this failure is not a provenance one, and the message must not say so.
  +    assert "guardrails failed" in result.output and "provenance violation" not in result.output


   def test_tailor_with_track_and_feedback(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
  diff --git a/apps/api/tests/unit/test_package_serving.py b/apps/api/tests/unit/test_package_serving.py
  new file mode 100644
  index 0000000..d74e5a3
  --- /dev/null
  +++ b/apps/api/tests/unit/test_package_serving.py
  @@ -0,0 +1,102 @@
  +"""No file leaves the server for a package whose guardrail report failed (plan-review-2, I-1).
  +
  +Phase 5 stops NEW blocked packages from writing a DOCX. Rows stored before it were rendered "for
  +review" and still have the file on disk, so the serving paths refuse independently of the writer.
  +`package_file` is called directly with its two lookups stubbed, so this runs without Postgres;
  +the same behaviour over HTTP is `test_blocked_package_download_is_unmistakable` (CI).
  +"""
  +
  +import uuid
  +import zipfile
  +from pathlib import Path
  +from types import SimpleNamespace
  +from typing import Any
  +
  +import pytest
  +from fastapi import HTTPException
  +from fastapi.responses import FileResponse
  +
  +from rhapto.api.routers import packages as router
  +from rhapto.services.storage import PackageStorage
  +
  +BLOCKED = {"passed": False, "rules_run": ["completeness"], "violations": []}
  +PASSED = {"passed": True, "rules_run": ["completeness"], "violations": []}
  +
  +
  +def _stub_lookups(monkeypatch: pytest.MonkeyPatch, report: dict[str, Any]) -> None:
  +    async def get_package(session: object, user_id: object, package_id: uuid.UUID) -> Any:
  +        return SimpleNamespace(id=package_id, guardrail_report_json=report)
  +
  +    async def basename(session: object, user_id: object) -> str:
  +        return "Maya_Chen"
  +
  +    monkeypatch.setattr(router, "_get_package", get_package)
  +    monkeypatch.setattr(router, "_basename", basename)
  +
  +
  +def _store_with_files(tmp_path: Path, package_id: uuid.UUID) -> PackageStorage:
  +    store = PackageStorage(tmp_path)
  +    store.write_docx(str(package_id), b"PK legacy docx")
  +    (store.dir_for(str(package_id)) / "resume.pdf").write_bytes(b"%PDF legacy")
  +    return store
  +
  +
  +@pytest.mark.parametrize("name", ["resume.docx", "resume.pdf"])
  +async def test_a_blocked_package_with_a_file_on_disk_is_not_served(
  +    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
  +) -> None:
  +    """The known-bad input: the file IS there, exactly as it is for a pre-Phase-5 blocked row."""
  +    package_id = uuid.uuid4()
  +    store = _store_with_files(tmp_path, package_id)
  +    assert store.path_for(str(package_id), name) is not None
  +    _stub_lookups(monkeypatch, BLOCKED)
  +    with pytest.raises(HTTPException) as caught:
  +        await router.package_file(package_id, name, uuid.uuid4(), None, store)  # type: ignore[arg-type]
  +    assert caught.value.status_code == 409 and "guardrails" in str(caught.value.detail)
  +
  +
  +async def test_a_passed_package_is_still_served(
  +    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  +) -> None:
  +    package_id = uuid.uuid4()
  +    store = _store_with_files(tmp_path, package_id)
  +    _stub_lookups(monkeypatch, PASSED)
  +    response = await router.package_file(
  +        package_id,
  +        "resume.docx",
  +        uuid.uuid4(),
  +        None,
  +        store,  # type: ignore[arg-type]
  +    )
  +    assert isinstance(response, FileResponse)
  +
  +
  +async def test_a_blocked_package_with_no_file_is_still_a_404(
  +    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
  +) -> None:
  +    """Nothing was rendered (every blocked package since Phase 5): 404, as before, not 409."""
  +    _stub_lookups(monkeypatch, BLOCKED)
  +    with pytest.raises(HTTPException) as caught:
  +        await router.package_file(
  +            uuid.uuid4(),
  +            "resume.docx",
  +            uuid.uuid4(),
  +            None,
  +            PackageStorage(tmp_path),  # type: ignore[arg-type]
  +        )
  +    assert caught.value.status_code == 404
  +
  +
  +def test_the_zip_leaves_the_documents_out_when_asked_even_if_they_are_on_disk(
  +    tmp_path: Path,
  +) -> None:
  +    package_id = uuid.uuid4()
  +    store = _store_with_files(tmp_path, package_id)
  +    withheld = store.build_zip(
  +        str(package_id), "note", "{}", {"GUARDRAILS-BLOCKED.md": "x"}, include_documents=False
  +    )
  +    with zipfile.ZipFile(__import__("io").BytesIO(withheld)) as zf:
  +        assert sorted(zf.namelist()) == ["GUARDRAILS-BLOCKED.md", "cover-note.md", "package.json"]
  +    included = store.build_zip(str(package_id), "note", "{}")
  +    with zipfile.ZipFile(__import__("io").BytesIO(included)) as zf:
  +        assert {"resume.docx", "resume.pdf"} <= set(zf.namelist())
  diff --git a/apps/api/tests/unit/test_pipeline.py b/apps/api/tests/unit/test_pipeline.py
  index 570c0e2..4c22a03 100644
  --- a/apps/api/tests/unit/test_pipeline.py
  +++ b/apps/api/tests/unit/test_pipeline.py
  @@ -169,9 +169,7 @@ async def test_unrepairable_output_is_blocked(profile: Profile) -> None:
       result = await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider())
       assert result.package.status == "blocked" and result.package.llm_calls == 3
       assert {v.rule for v in result.package.guardrail_report.violations} == {"no-unverified-metrics"}
  -    assert (
  -        result.docx[:2] == b"PK"
  -    )  # still rendered for review; the orphan check is the only hard stop
  +    assert result.docx == b""  # owner, 2026-09-25: a failing report never persists a DOCX


   async def test_budget_exceeded_during_repair_yields_a_blocked_package_not_a_crash(
  @@ -243,6 +241,7 @@ async def test_cover_note_metric_blocks_even_when_the_resume_is_clean(profile: P
       assert [v.path for v in violations] == ["cover_note"]
       assert violations[0].rule == "no-unverified-metrics" and violations[0].block_id is None
       assert "37%" in violations[0].message
  +    assert result.docx == b""  # the resume is clean; only the cover note failed


   async def test_missing_role_block_triggers_repair_and_restoring_it_passes(
  @@ -271,6 +270,7 @@ async def test_repair_that_drops_a_different_block_is_blocked_with_the_post_repa
       violations = result.package.guardrail_report.violations
       assert any(v.rule == "completeness" and v.block_id == "cred-pmp" for v in violations)
       assert not any(v.block_id == "acme-data-pm" for v in violations)  # the role was restored
  +    assert result.docx == b""  # a failing report never persists a DOCX, whatever rule failed


   # --- tune mode -------------------------------------------------------------------------------
  ```

  The new file `test_package_serving.py` holds the serve-time tests: the known-bad input (a blocked package whose DOCX and PDF **are on disk**) must be refused with 409, a passed package is still served, a blocked package with no file is still 404, and `build_zip(..., include_documents=False)` leaves the documents out even though they are on disk. It calls `package_file` directly with `_get_package`/`_basename` stubbed, so it runs here without Postgres. `test_blocked_package_download_is_unmistakable` (CI-only) is the same behaviour over HTTP.

  Two of the pipeline tests are direct tests of the new gate rather than just flipped assertions: `test_cover_note_metric_blocks_even_when_the_resume_is_clean` (the resume itself is clean, so before this task the render succeeded), and the `completeness` case (a `completeness` failure, not a metrics one, still leaves `docx == b""`).

- [ ] **Step 2: Run them and confirm they fail**

  Run: `cd apps/api && uv run pytest tests/unit/test_pipeline.py -q` and, for the CLI test, with a temporary `apps/api/.env` holding `RHAPTO_SECRET_KEY=<Fernet key>` (see "Local baseline"; delete it afterwards): `uv run pytest tests/unit/test_cli.py::test_tailor_blocked_exits_3 -q`
  Also run `uv run pytest tests/unit/test_package_serving.py -q`. Expected: the flipped/added pipeline assertions FAIL (a non-empty `docx`), `test_tailor_blocked_exits_3` FAILS on the message, and `test_package_serving.py` FAILS (the known-bad package is served instead of raising; `build_zip` rejects the unknown `include_documents` keyword). `tests/api/test_packages_api.py` skips here (no Postgres).

- [ ] **Step 3: Apply the source changes**

  ```diff
  diff --git a/apps/api/src/rhapto/api/routers/packages.py b/apps/api/src/rhapto/api/routers/packages.py
  index 79bdd90..53e99ff 100644
  --- a/apps/api/src/rhapto/api/routers/packages.py
  +++ b/apps/api/src/rhapto/api/routers/packages.py
  @@ -100,8 +100,9 @@ def blocked_note(report: GuardrailReport) -> str:
       lines = [
           "# Guardrails blocked this package",
           "",
  -        "Rhapto's guardrails rejected this draft. The files are still here so you can see why,",
  -        "but do not send this resume until every violation below is resolved.",
  +        "Rhapto's guardrails rejected this draft, so no resume document is included.",
  +        "The violations below say why; do not send a resume built from this draft until every",
  +        "error is resolved.",
           "",
       ]
       for violation in report.violations:
  @@ -217,12 +218,14 @@ async def _edited_blocks_version(
       report = run_guardrails(
           resume, profile, parent.selection_block_ids, extract, cover_note=parent.cover_note
       )
  -    try:
  -        # python-docx builds a zip in memory; keep it off the event loop with the rest of the IO.
  -        base = profile.base_for(profile.get_track(parent.track_id))
  -        docx = await asyncio.to_thread(render_docx, resume, profile.block_map(), base.style)
  -    except OrphanBulletError:
  -        docx = b""
  +    docx = b""
  +    if report.passed:
  +        try:
  +            # python-docx builds a zip in memory; keep it off the event loop with the rest of the IO.
  +            base = profile.base_for(profile.get_track(parent.track_id))
  +            docx = await asyncio.to_thread(render_docx, resume, profile.block_map(), base.style)
  +        except OrphanBulletError:
  +            docx = b""
       return EditedVersion({"resume": resume}, docx, report)


  @@ -451,6 +454,7 @@ async def download_package(
           row.cover_note,
           model.model_dump_json(indent=2),
           extra_files,
  +        include_documents=passed,
       )
       filename = f"{await _basename(session, user_id)}_Package.zip"
       return Response(
  @@ -476,6 +480,16 @@ async def package_file(
       ext = "docx" if name == "resume.docx" else "pdf"
       media = DOCX_MEDIA if name == "resume.docx" else PDF_MEDIA
       report = GuardrailReport.model_validate(row.guardrail_report_json)
  +    if not report.passed:
  +        # 409, not 404: the file exists, it is being withheld. An absent file (every blocked
  +        # package written since Phase 5) already answered 404 above, so 404 stays "nothing was
  +        # rendered" and 409 means "rendered before the rule existed, and refused now". The web
  +        # client turns any non-2xx into a toast carrying this `detail`.
  +        raise HTTPException(
  +            status_code=409,
  +            detail="guardrails blocked this package, so its resume documents are not served; "
  +            "fix the violations and regenerate",
  +        )
       stem = await _basename(session, user_id)
       return FileResponse(
           path,
  diff --git a/apps/api/src/rhapto/cli/main.py b/apps/api/src/rhapto/cli/main.py
  index e259e05..c772d45 100644
  --- a/apps/api/src/rhapto/cli/main.py
  +++ b/apps/api/src/rhapto/cli/main.py
  @@ -181,7 +181,7 @@ def tailor_cmd(
       write_package(result, target)

       if not result.docx:
  -        typer.echo("PDF skipped: no DOCX was rendered (provenance violation; see guardrail report)")
  +        typer.echo("PDF skipped: no DOCX was rendered (guardrails failed; see the report)")
       elif no_pdf:
           typer.echo("PDF skipped")
       elif not soffice_available(settings.rhapto_soffice_binary):
  diff --git a/apps/api/src/rhapto/engine/pipeline.py b/apps/api/src/rhapto/engine/pipeline.py
  index a67e50e..47092f7 100644
  --- a/apps/api/src/rhapto/engine/pipeline.py
  +++ b/apps/api/src/rhapto/engine/pipeline.py
  @@ -206,10 +206,12 @@ async def tailor(
                   )

       await _notify(on_step, "render")
  -    try:
  -        docx = render_docx(resume, profile.block_map(), profile.base_for(track).style)
  -    except OrphanBulletError:
  -        docx = b""  # provenance violation is already in the report; nothing safe to render
  +    docx = b""
  +    if report.passed:
  +        try:
  +            docx = render_docx(resume, profile.block_map(), profile.base_for(track).style)
  +        except OrphanBulletError:
  +            docx = b""  # provenance violation is already in the report; nothing safe to render

       package = _build_package(
           request,
  diff --git a/apps/api/src/rhapto/services/storage.py b/apps/api/src/rhapto/services/storage.py
  index 7a49a52..0c87e7a 100644
  --- a/apps/api/src/rhapto/services/storage.py
  +++ b/apps/api/src/rhapto/services/storage.py
  @@ -58,12 +58,16 @@ class PackageStorage:
           cover_note: str,
           package_json: str,
           extra_files: dict[str, str] | None = None,
  +        include_documents: bool = True,
       ) -> bytes:
           """Zip the package files. `extra_files` maps archive name to text content (e.g. a
  -        guardrail-blocked notice) and is written last."""
  +        guardrail-blocked notice) and is written last. `include_documents=False` leaves
  +        `resume.docx` and `resume.pdf` out even when they are on disk: the caller passes it for
  +        a package whose guardrail report failed, so a file rendered before that rule existed
  +        is not handed out."""
           buffer = io.BytesIO()
           with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
  -            for name in ("resume.docx", "resume.pdf"):
  +            for name in ("resume.docx", "resume.pdf") if include_documents else ():
                   path = self.path_for(package_id, name)
                   if path is not None:
                       zf.write(path, name)
  ```

- [ ] **Step 4: Run the affected tests**

  Run: `cd apps/api && uv run pytest tests/unit/test_pipeline.py tests/unit/test_package_serving.py tests/unit/test_storage.py tests/guardrails tests/golden -q`; the CLI file with the temporary `.env`: `uv run pytest tests/unit/test_cli.py -q` (23 pass with it, verified; delete the `.env` afterwards); and note that `tests/api/test_packages_api.py` **could not run locally**.
  Expected: all pass. Then prove the gate bites: temporarily change `if not report.passed:` in `package_file` to `if False:`, re-run `tests/unit/test_package_serving.py`, and confirm both parametrised known-bad cases fail (verified); then change `for name in (...) if include_documents else ():` in `build_zip` back to a plain loop and confirm the zip test fails (verified). Restore both.

- [ ] **Step 5: Format and gate**

  ```
  cd apps/api
  uv run ruff format .        # commit whatever it changes (review I-2)
  uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
  ```
  Report per "CI facts": suites run locally = `tests/unit/test_pipeline.py`, `tests/unit/test_package_serving.py`, `tests/unit/test_storage.py`, `tests/unit/test_cli.py` (with the temporary key), `tests/guardrails`, `tests/golden`. **Not run locally, CI-only: `tests/api/test_packages_api.py::test_patch_with_invented_metric_is_blocked` and `::test_blocked_package_download_is_unmistakable` — the HTTP behaviour of the fourth-site fix and of the serve-time gate has only the direct-call unit tests as local evidence**; say so plainly in the report.

- [ ] **Step 6: Commit**

  ```bash
  git add apps/api/src/rhapto/engine/pipeline.py apps/api/src/rhapto/api/routers/packages.py \
          apps/api/src/rhapto/cli/main.py apps/api/src/rhapto/services/storage.py \
          apps/api/tests/unit/test_pipeline.py apps/api/tests/unit/test_package_serving.py \
          apps/api/tests/api/test_packages_api.py apps/api/tests/unit/test_cli.py
  git commit -m "fix: never persist or serve a DOCX for a failing guardrail report, in any mode (Phase 5, AC5)"
  ```

---

### Task 5: Phase 4 measurement helper and script

**Advances:** architecture condition C6 (Phase 4 measurement is a deliverable). Not an acceptance criterion itself; it produces the evidence Phase 6's go/no-go decision needs.

**Files:**
- Create: `apps/api/src/rhapto/engine/measurement.py`
- Create: `apps/api/tests/unit/test_measurement.py`
- Create: `scripts/measure_completeness.py`

**Interfaces:**
- Consumes: `TailorResult` (`.pre_repair_report`, `.repaired`, `.package`) from Task 2; the script also consumes `tailor(request, profile, llm, embedder)`, `build_providers(settings, provider, model) -> Providers` (`rhapto.cli.main`, checked: `provider`/`model` are optional and unknown providers raise `typer.BadParameter`), `load_profile(path)`, `get_settings()`.
- Produces: `first_pass_rules(result) -> list[str]`, `final_rules(result) -> list[str]`, `summarize_result(result) -> str`, and `invented_project_titles(result, blocks) -> list[str]` (plan-review-2 I-2) — pure functions over one result.

**What changed and why (review I-3).** The draft's `summarize_run(status, llm_calls, violation_rules)` mis-measured the one number C6 exists to produce: it called `llm_calls == 3 and status == "draft"` a repair, but `_structured_call` also spends a third call on a malformed-output retry (`test_malformed_compose_is_retried_within_the_budget` is exactly that shape); and `tailor()` returned only the **post-repair** report, so per-model "completeness violations" and "repair success" were unobservable. Task 2 plumbs `pre_repair_report`/`repaired`; this task reads them and never reads `llm_calls`. **U-1's instrument (plan-review-2, I-2):** the measurement also records `invented_project_titles`, because the risk the plan says it watches (a composer inventing a title for a project block with no `role`; no rule validates `title`) was invisible to every other field: such a run is a clean `draft`. The helper lists project entries whose `title`/`role` text is not made of words from the cited block's role, org and content. It is an upper bound and does not block; its known-bad test builds exactly the invisible case and fails without the helper. So Task 5 **does** satisfy C6's instrumentation; the numbers themselves remain Phase 4's job, run by the owner with real keys.

**Why the script itself is outside the `pytest`/`ruff`/`mypy` gate:** `scripts/` sits outside `apps/api`'s `testpaths`/`packages` scope (precedent: `scripts/check-no-personal-data.py`, `scripts/discovery-fixture-server.py`), and it makes real network calls to paid LLM providers, so it cannot run in CI. The aggregation logic is factored into `rhapto.engine.measurement` so it *is* covered. `rhapto.engine.measurement` imports only `rhapto.engine.pipeline`, so the `engine-is-pure` import-linter contract is unaffected (verified: 6 contracts kept).

- [ ] **Step 1: Write the failing tests for the helper**

  Create `apps/api/tests/unit/test_measurement.py`. These run the real `tailor()` with scripted providers (the same fixtures as `test_pipeline.py`), so the helper is tested against the result shape it will really see, including the malformed-retry case:

  ```python
  from pathlib import Path
  from typing import Any

  import pytest
  from helpers import demo_extract, good_output

  from rhapto.engine.measurement import (
      final_rules,
      first_pass_rules,
      invented_project_titles,
      summarize_result,
  )
  from rhapto.engine.pipeline import CallBudget, tailor
  from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
  from rhapto.engine.types import Profile, TailorRequest
  from rhapto.profile.loader import load_profile

  JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration."
  MALFORMED = {"$PARAMETER_NAME": "$PARAMETER_VALUE"}


  @pytest.fixture
  def profile(demo_profile_dir: Path) -> Profile:
      return load_profile(demo_profile_dir)


  def missing_role_output() -> dict[str, Any]:
      output = good_output()
      output["sections"][0]["entries"] = []
      return output


  async def _run(profile: Profile, script: list[dict[str, Any]], **kwargs: Any):  # type: ignore[no-untyped-def]
      llm = FakeLLMProvider(script)
      return await tailor(TailorRequest(jd_text=JD), profile, llm, FakeEmbeddingProvider(), **kwargs)


  async def test_a_run_that_passed_first_time_is_clean(profile: Profile) -> None:
      result = await _run(profile, [demo_extract(), good_output()])
      assert summarize_result(result) == "passed clean"
      assert first_pass_rules(result) == [] and final_rules(result) == []


  async def test_a_malformed_output_retry_is_not_read_as_a_repair(profile: Profile) -> None:
      """I-3. Three calls and a draft -- exactly the shape a repair success has -- but the third call
      was a retry after malformed output. Counting calls would report a repair that never happened."""
      result = await _run(profile, [demo_extract(), MALFORMED, good_output()])
      assert result.package.llm_calls == 3 and result.package.status == "draft"
      assert summarize_result(result) == "passed clean"


  async def test_a_dropped_role_that_repair_restored_is_reported_with_its_rule(
      profile: Profile,
  ) -> None:
      """The C6 number: the final report is clean, yet the first pass failed `completeness`."""
      result = await _run(profile, [demo_extract(), missing_role_output(), good_output()])
      assert result.package.guardrail_report.passed
      assert first_pass_rules(result) == ["completeness"] and final_rules(result) == []
      assert summarize_result(result) == "repaired (first pass failed: completeness)"


  async def test_a_dropped_role_that_repair_did_not_restore_is_blocked_after_repair(
      profile: Profile,
  ) -> None:
      script = [demo_extract(), missing_role_output(), missing_role_output()]
      result = await _run(profile, script)
      assert summarize_result(result) == (
          "blocked after repair (completeness); first pass failed: completeness"
      )


  async def test_an_exhausted_budget_is_blocked_with_no_repair_run(profile: Profile) -> None:
      script = [demo_extract(), missing_role_output(), good_output()]
      result = await _run(profile, script, budget=CallBudget(max_calls=2))
      assert result.package.llm_calls == 2
      assert summarize_result(result) == "blocked, no repair ran (completeness)"


  async def test_a_project_title_copied_from_its_block_is_not_invented(profile: Profile) -> None:
      result = await _run(profile, [demo_extract(), good_output()])
      assert invented_project_titles(result, profile.block_map()) == []


  async def test_an_invented_project_title_passes_every_guardrail_and_is_still_recorded(
      profile: Profile,
  ) -> None:
      """U-1, the known-bad input. No rule validates an entry's title, so this run is a clean
      `draft` -- which is exactly why `invented_project_titles` has to exist. Without it the assertion
      below cannot be written, and the measurement is blind to the risk it is meant to watch."""
      output = good_output()
      output["sections"][1]["entries"][0]["title"] = "Award-winning evaluation platform"
      result = await _run(profile, [demo_extract(), output])
      assert result.package.status == "draft" and summarize_result(result) == "passed clean"
      assert invented_project_titles(result, profile.block_map()) == [
          "side-llm-tool: Award-winning evaluation platform"
      ]
  ```

- [ ] **Step 2: Run it and confirm it fails**

  Run: `cd apps/api && uv run pytest tests/unit/test_measurement.py -v`
  Expected: FAIL with `ModuleNotFoundError: No module named 'rhapto.engine.measurement'`.

- [ ] **Step 3: Write `measurement.py`**

  ```python
  """Phase 4 measurement (completeness guardrail): pure aggregation over one `tailor()` result.

  The live part of Phase 4 -- calling real providers with real API keys for a fixed JD -- lives in
  `scripts/measure_completeness.py`, outside this package's mypy/ruff/pytest gate because it makes
  network calls. This module holds the part worth a unit test: reading what a run actually did.

  It reads `TailorResult.pre_repair_report` and `TailorResult.repaired`, never `llm_calls`. A third
  call is not evidence of a repair: `_structured_call` spends one on a malformed-output retry, which
  leaves a `draft` package with three calls and nothing repaired. And `package.guardrail_report` is
  the POST-repair report, so on its own it cannot tell a model that dropped a role and was repaired
  from one that never dropped anything -- which is the number architecture condition C6 exists to get.
  """

  from __future__ import annotations

  import re
  from collections.abc import Mapping

  from rhapto.engine.pipeline import TailorResult
  from rhapto.models.profile.blocks import Block

  _TOKEN = re.compile(r"[a-z0-9]+")


  def first_pass_rules(result: TailorResult) -> list[str]:
      """Distinct rule names the FIRST compose failed, sorted; empty when it passed."""
      if result.pre_repair_report is None:
          return []
      return sorted({v.rule for v in result.pre_repair_report.violations if v.severity == "error"})


  def final_rules(result: TailorResult) -> list[str]:
      """Distinct rule names still failing in the package that was actually stored, sorted."""
      report = result.package.guardrail_report
      return sorted({v.rule for v in report.violations if v.severity == "error"})


  def summarize_result(result: TailorResult) -> str:
      """One-line verdict for a Phase 4 ledger row."""
      if result.pre_repair_report is None:
          return "passed clean"
      first = ", ".join(first_pass_rules(result))
      if result.package.status == "draft":
          return f"repaired (first pass failed: {first})"
      final = ", ".join(final_rules(result))
      if result.repaired:
          return f"blocked after repair ({final}); first pass failed: {first}"
      return f"blocked, no repair ran ({final})"


  def invented_project_titles(result: TailorResult, blocks: Mapping[str, Block]) -> list[str]:
      """Project entries whose `title` or `role` text does not come from the block they cite.

      This is the instrument for U-1. The project clause of `completeness` needs a `title` or `role`
      on the entry, no rule validates `title` (`no-invented-entities` checks org, role and period),
      and a project block with no `role` leaves a composer nothing to copy. So an invented title
      passes every guardrail and is invisible to `first_pass_rules`/`final_rules`. "Comes from the
      block" is deliberately loose: every word of the text appears among the words of the block's
      role, org and content. That makes this an upper bound (a paraphrase is counted) and never a
      miss for a title that adds a word the block does not have. Each hit is `"<block id>: <text>"`.
      """
      found: list[str] = []
      for section in result.package.resume.sections:
          if section.kind != "projects":
              continue
          for entry in section.entries:
              block = blocks.get(entry.source_block_id)
              if block is None:
                  continue
              sourced = set(
                  _TOKEN.findall(
                      " ".join(filter(None, [block.role, block.org, block.content])).casefold()
                  )
              )
              for text in (entry.title, entry.role):
                  if text and text.strip() and not set(_TOKEN.findall(text.casefold())) <= sourced:
                      found.append(f"{entry.source_block_id}: {text}")
      return found
  ```

- [ ] **Step 4: Run the test and confirm it passes**

  Run: `cd apps/api && uv run pytest tests/unit/test_measurement.py -v`
  Expected: 7 pass.

- [ ] **Step 5: Write the measurement script**

  Create `scripts/measure_completeness.py`. Versus the draft: it records the first-pass rules and `repaired` per model, validates `--provider` with `parser.error` (review M-4: `tuple(t.split(":", 1))` raised `ValueError` on `--provider anthropic`), and its docstring says the profile may need to be a scratch copy.

  ```python
  #!/usr/bin/env python3
  """Phase 4 measurement (completeness guardrail): run one JD through `tailor()` once per configured
  model and record, per model, which rules the FIRST compose failed, whether repair ran and fixed it,
  and the final outcome, call count and token usage, to a JSON ledger.

  Manual, not part of CI: needs real provider API keys in the environment/.env. Run from the repo
  root with:

      uv run --project apps/api python scripts/measure_completeness.py \\
          --jd path/to/jd.txt --profile ./profile \\
          --provider anthropic:claude-haiku-5 --provider anthropic:claude-sonnet-5

  `--profile` takes any profile directory. The owner's real profile may fail the strict schema on
  load (see the scratch-copy note in the owner's memory); point it at the scratch copy in that case.
  The ledger holds rule names, ids and counts only -- never block content -- but do not commit it
  if it was produced from a real profile.

  Reading the output: `first pass failed: completeness` is a model that dropped a selected block.
  `repaired (...)` means the one repair call restored it; `blocked after repair (...)` means it did
  not. Both read `TailorResult.pre_repair_report`, not `llm_calls`, so a malformed-output retry is
  never mistaken for a repair. `invented_project_titles` counts project entries whose title or role
  text is not made of words from the block they cite: no guardrail validates a title, so this is the
  only place the U-1 risk (models inventing a title for a project block with no role) shows up.
  That repair-success rate, per model, is the number architecture
  condition C6 says decides whether the deterministic entry skeleton (Phase 6) is needed.
  """

  from __future__ import annotations

  import argparse
  import asyncio
  import json
  from dataclasses import asdict, dataclass
  from pathlib import Path

  from rhapto.cli.main import build_providers
  from rhapto.config import get_settings
  from rhapto.engine.measurement import (
      final_rules,
      first_pass_rules,
      invented_project_titles,
      summarize_result,
  )
  from rhapto.engine.pipeline import tailor
  from rhapto.engine.types import TailorRequest
  from rhapto.profile.loader import load_profile


  @dataclass
  class MeasurementRow:
      provider: str
      model: str
      verdict: str
      first_pass_rules: list[str]
      repaired: bool
      final_rules: list[str]
      invented_project_titles: list[str]
      status: str
      llm_calls: int
      input_tokens: int
      output_tokens: int


  async def _run_one(jd_text: str, profile_dir: Path, provider: str, model: str) -> MeasurementRow:
      providers = build_providers(get_settings(), provider, model)
      profile = load_profile(profile_dir)
      result = await tailor(
          TailorRequest(jd_text=jd_text), profile, providers.llm, providers.embedder
      )
      package = result.package
      return MeasurementRow(
          provider=provider,
          model=model,
          verdict=summarize_result(result),
          first_pass_rules=first_pass_rules(result),
          repaired=result.repaired,
          final_rules=final_rules(result),
          invented_project_titles=invented_project_titles(result, profile.block_map()),
          status=package.status,
          llm_calls=package.llm_calls,
          input_tokens=package.usage.input_tokens,
          output_tokens=package.usage.output_tokens,
      )


  async def _run_all(
      jd_text: str, profile_dir: Path, targets: list[tuple[str, str]]
  ) -> list[MeasurementRow]:
      rows: list[MeasurementRow] = []
      for provider, model in targets:
          try:
              rows.append(await _run_one(jd_text, profile_dir, provider, model))
          except Exception as exc:
              print(f"{provider}:{model}  FAILED: {exc}")
      return rows


  def _parse_target(parser: argparse.ArgumentParser, raw: str) -> tuple[str, str]:
      provider, sep, model = raw.partition(":")
      if not sep or not provider or not model:
          parser.error(
              f"--provider expects PROVIDER:MODEL (for example anthropic:claude-haiku-5), got {raw!r}"
          )
      return provider, model


  def main() -> None:
      parser = argparse.ArgumentParser(description=__doc__)
      parser.add_argument("--jd", type=Path, required=True)
      parser.add_argument("--profile", type=Path, default=Path("./profile"))
      parser.add_argument(
          "--provider",
          action="append",
          required=True,
          dest="targets",
          metavar="PROVIDER:MODEL",
          help="repeatable, e.g. --provider anthropic:claude-haiku-5",
      )
      parser.add_argument("--out", type=Path, default=Path("completeness-measurement.json"))
      args = parser.parse_args()

      targets = [_parse_target(parser, raw) for raw in args.targets]
      jd_text = args.jd.read_text(encoding="utf-8")
      rows = asyncio.run(_run_all(jd_text, args.profile, targets))

      for row in rows:
          print(
              f"{row.provider}:{row.model}  {row.verdict}  calls={row.llm_calls} "
              f"in={row.input_tokens} out={row.output_tokens} "
              f"invented_project_titles={len(row.invented_project_titles)}"
          )

      args.out.write_text(json.dumps([asdict(r) for r in rows], indent=2), encoding="utf-8")
      print(f"wrote {args.out}")


  if __name__ == "__main__":
      main()
  ```

- [ ] **Step 6: Sanity-check the script imports and parses arguments cleanly**

  Run: `uv run --project apps/api python scripts/measure_completeness.py --help`
  Expected: prints the argparse help (every import resolves; no network call; the ledger row now includes `invented_project_titles`). Then `uv run --project apps/api python scripts/measure_completeness.py --jd x --provider anthropic` must exit with `error: --provider expects PROVIDER:MODEL ...` (verified), not a traceback.

- [ ] **Step 7: Format and gate, then the one whole-suite run**

  ```
  cd apps/api
  uv run ruff format .        # commit whatever it changes (review I-2)
  uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run lint-imports
  uv run ruff format --config pyproject.toml --check ../../scripts/measure_completeness.py
  uv run pytest -q
  ```
  The script is outside the gate; the last `ruff format` line just keeps it formatted (it was, verified, with `apps/api`'s config; the repo root has no ruff config, so run it *with* this one). The whole-suite `uv run pytest -q` is the once-per-project full run before hand-over. Expected locally: everything passes **except the failures listed under "Local baseline"** (the nine `test_cli.py` tests unless a temporary `.env` key is set — in which case `test_config`'s secret-key test fails instead — and the two Postgres-less migration tests), with the DB suites skipped. Verified on the final commit with a temporary `.env`: 708 passed, 494 skipped, and exactly those environment failures.
  Report per "CI facts". **Hand the branch over to QA only after CI is green on it** — this is the one task where the local run cannot be the last word, because every DB-dependent test in Tasks 1, 2 and 4 has run only there.

- [ ] **Step 8: Commit**

  ```bash
  git add apps/api/src/rhapto/engine/measurement.py apps/api/tests/unit/test_measurement.py \
          scripts/measure_completeness.py
  git commit -m "chore: Phase 4 measurement helper and manual measurement script (C6)"
  ```

---

## Self-Review

**Acceptance-criteria coverage:**

| AC | Covered by | Notes |
|---|---|---|
| 1 (role blocks certain) | Task 1 (`MANDATORY_KINDS["role"] = "experience"`, all rule-level tests) | |
| 2 (project/credential also mandatory) | Task 1 (`MANDATORY_KINDS["project"/"credential"]`, `test_project_entry_with_blank_title_and_role_is_flagged`, `test_credential_*`); Task 1b (the demo profile's project and credential are placeable) | |
| 3 (skill/achievement never checked) | Task 1 (`test_skill_and_achievement_never_checked`) | |
| 4 (message shape, block id + fields) | Task 1 (`_describe`, `test_measured_case_one_role_missing_of_five`, remedy in `REMEDIES`); Task 3 (a node-less row is readable text, still showing block id and remedy) | |
| 5 (no persisted DOCX on a failing report, any mode) | Task 4 (pipeline blocks branch + PATCH hand-edit path + CLI message; four pinned tests changed; the `completeness` case asserted; **serve-time gate** so already-stored blocked rows are not handed out) | Owner confirmation 2026-09-25. The HTTP behaviour is CI-only evidence; the gate also has local direct-call tests. |
| 6 (runs before `run_guardrails` returns; rides the existing repair call) | Task 1 (wiring in `registry.run_guardrails`); Task 2 (repair prompt usable for it; pipeline tests prove one retry happens and that the violation text reaches the model) | |
| 7 (bullet/wording/order variation stays clean) | Task 1 (`test_clean_variation_with_reworded_bullets_passes`) | |
| 8 (merge/substitution caught, one violation not two) | Task 1 (`test_merge_fold_produces_one_violation_naming_the_entry`, `test_substitution_same_org_sibling_present`; `test_attribution_missing_from_a_bulleted_entry_is_left_to_the_attribution_rule` for the doubled-report edge) | |
| 9 (no new LLM call, no new deterministic step) | Task 1 (pure function of existing `GuardrailContext` fields); Task 2 (no call added; the guard only *removes* a crash) | |
| 10 (5-role/4-present adversarial test + merge test + bullet-only-change test) | Task 1 (`test_measured_case_one_role_missing_of_five`, `test_merge_fold_...`, `test_clean_variation_...`) | |

**Architecture conditions:** C1 Task 2 (`REPAIR_INSTRUCTIONS`); C2 Task 2 (blocks and tune); C3 Task 4 (owner-confirmed, in scope); C4 Task 1 (`test_completeness_is_unconditional_and_rejected_as_a_configured_rule`, `test_tune_guardrails_never_emit_completeness`); C5 Task 1 (`DEFAULT_FUZZY_THRESHOLD` constant, no `ctx.config` read); C6 Task 5 with Task 2's plumbing (instrumentation only, now including `invented_project_titles`; the measurement is the owner's run); C7 Task 1 (one violation per defect).

**Phases vs. tasks:** Phase 1 → Task 1 (+ Task 1b, required by review C-2). Phase 2 → Task 2. Phase 3 → Task 3. Phase 5 → Task 4. Phase 4 → Task 5 (instrumentation and script; the live run needs real keys and belongs to the owner). **Phase 6 (deterministic entry skeleton) is out of scope**, and nothing here builds toward it beyond what already exists.

**Placeholder scan:** every code step is a complete, applied-and-verified file or unified diff. Every "Run" step names the command and the expected outcome. No task says "similar to Task N" in place of code.

**Cross-task consistency check (re-verified against the applied commits):**
- `RULE_NAME = "completeness"` is the exact string used in Task 1's tests, Task 2's pipeline tests (`v.rule == "completeness"`, the `[completeness]` violation line), Task 4's docx assertion, Task 5's measurement tests, and the `REMEDIES` key. `rules_run == ["provenance", "no-unverified-metrics", "completeness"]` is asserted in exactly `test_registry.py` (twice) and `test_completeness.py`.
- `check_completeness(ctx) -> list[Violation]` is called directly only by Task 1's tests and `registry.py`; Tasks 2–5 observe it through `run_guardrails`/`tailor`.
- `MANDATORY_KINDS` values match `ResumeSection.kind`'s `Literal["experience", "projects", "skills", "credentials"]`.
- `fuzzy_entity_match(candidate, source, threshold)` is called with the same argument order in `completeness.py` (`_org_matches`) and `entities.py`.
- `TailorResult.pre_repair_report`/`.repaired` (Task 2) are read only by Task 5 and by Task 2's own tests; both default, so no other constructor or consumer changes.
- `TailorResult.docx` and `EditedVersion.docx` are both `b""` on a failing report via the identical `docx = b""; if report.passed: ...` shape.
- Task order is load-bearing: 1b before 1 (the fake), 2 before 5 (the result fields), and Task 4's `docx == b""` assertion on the `completeness` case is added in Task 4, not Task 2, because it cannot pass earlier.
