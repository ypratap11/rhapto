# Stage 3 follow-ups (parked during review, for stage 4)

Items the stage 3 reviews raised that were deliberately not fixed on the stage 3 branch. None blocks
merging; each is small and scoped. The 0.3 pollers plan comes before stage 4 (decision 2026-09-10).

## Web

- Split `apps/web/src/lib/api/queries.ts` by resource (`jobs`, `packages`, `applications`, `profile`)
  with one shared `keys` root; `packageKeys.blocks` and `packageKeys.applications` no longer describe
  their contents.
- Remove create-next-app scaffold: `apps/web/README.md` boilerplate, unused `public/*.svg`; add the
  planned `public/favicon.svg`.
- `Board.tsx`: closing the sheet leaves `selectedId` set (a refetch that re-adds the row reopens it);
  two quick drags can have the first completion clear the second's optimistic override.
- `ApplicationCard.tsx`: dnd-kit `attributes` (role=button, tabIndex) spread on a container that wraps
  a `Link` and a `Button`; document that the keyboard path across columns is the sheet's Status select.
- `settings/page.tsx` `disconnect()` toasts "Disconnected" even when the localStorage write fails.
- `globals.css` still declares `@custom-variant dark`; dark mode is out of scope.
- Track filter on the queue lands with 0.3 classification (`GET /jobs` has only `search` today).
- Documented deviation: `RHAPTO_PUBLIC_API_URL` (root `.env`) feeds the `NEXT_PUBLIC_API_URL` build
  arg; spec section 10 named `NEXT_PUBLIC_API_URL` directly.

## API / engine

- `apps/api/tests/unit/test_enqueue_arq.py`: two tests error on Windows hosts with
  `redis.exceptions.TimeoutError` inside arq's `create_pool()` while redis itself answers; look at
  arq's pool under Windows' default asyncio event-loop policy. Pre-dates stage 3.
- Pipeline budget: add a test for a retry consumed by an earlier step followed by a malformed later
  step (traced by hand: `LLMBudgetExceeded`, never a fourth call).
- Strict tool mode was tried with claude-sonnet-5 and rejected (output split across two tool_use
  blocks, empty sections); revisit if a later model handles it, since it would replace the
  wrapper-unwrap heuristic in `parse_tool_input`.
- Profile schema: support a free-text `notes` field on blocks (real profiles use it; the strict schema
  rejects it today).

## Repo hygiene before publishing

- Rewrite history to drop the real employer name committed in a9838fb (the file was corrected later,
  the history was not).
- CI: regenerate `packages/schemas/openapi.json`, `schema.d.ts`, and the Pydantic models and fail on
  diff; run the personal-data check; run web and api suites.
- Web test suite: `testTimeout` is 20s repo-wide because jsdom + Base UI + `userEvent.type` is slow;
  consider `delay: null` in the remaining typing tests and fewer parallel workers instead.

## Phase 0.3 follow-ups (from the whole-branch review, 2026-09-11)

- `GET /jobs` still runs `latest_package` and `application_for_job` per job and has no `limit`/`offset`; with
  polling the table grows unboundedly. Fold both lookups into the listing query and add pagination (cursor vs
  offset is a design decision).
- Spec section 13 weak-score signal: an empty-description posting falls back to the title only, not title plus
  location, and the rationale carries no `weak` flag.
- The worker publishes `discovery` events but nothing subscribes; a cron poll gives an open Queue page no
  signal. Add an SSE consumer (and align the channel/event names with spec section 7) or defer to 0.4.
- `AggregatorsSection`'s shared keyword field seeds from the first row and writes to every row, so divergent
  per-source keywords (as in `profile.example`) are clobbered on save; seed from the union or block Save.
- `scripts/discovery-fixture-server.py` binds `0.0.0.0` and flattens all fixtures into one namespace.
- Migration `0002` creates the partial unique index `uq_jobs_user_source_external` but the ORM declares no
  matching `Index`; autogenerate would propose dropping it.
- `tests/unit` on pytest's `pythonpath` (for the shared `fake_http_for` helper) invites module-name collisions;
  move the helper to `tests/helpers/`.
- `delete_all_profile_rows` omits `Aggregator` (harmless today).
- `test_track_put_rescores` passes without rescoring (bucket is derived in `job_to_out`); `score_cmd` lacks the
  `ProfileError` handler `discover_cmd` has; CLI track-keyword union is not deduped.
- `assert_public_host` resolves DNS separately from httpx (rebinding TOCTOU); pre-existing.
- Live poll 2026-09-11: the task summary reported `new:222` while the per-source `poll_runs.new` values summed
  to 15; verify how `finish_run` and `latest_runs` account for new jobs (possibly runs from an earlier poll of
  the same source shadowing, or reposts counted differently).
- A renamed board slug leaves the old `(source, board)` run row in the runs drawer forever; consider pruning
  runs whose entry no longer exists.

## Stage 4 feature request (user, 2026-09-11): named downloads

- Package downloads should be named after the candidate and role, not `rhapto-package-v1.zip`: e.g.
  `<First>_<Last>_Resume.pdf`, `<First>_<Last>_Resume.docx`, `<First>_<Last>_Cover_Note.md`, using the
  `name` answer from the profile (fallback `Resume`), with the company or role as an optional suffix.
- The review page should offer the PDF and DOCX as direct downloads (one click each) in addition to the zip;
  the API sets the `Content-Disposition` filename accordingly on `/packages/{id}/files/*` and `/download`.
- Keep the blocked-package marker (`X-Rhapto-Guardrails`, `GUARDRAILS-BLOCKED.md`) on every variant.

## Stage 4 feature request (user, 2026-09-11): render into the user's own resume template

- Let the user upload a `.docx` template (gitignored, stored with the profile) and pour every package into
  it: copy paragraph and run formatting from exemplar paragraphs (name, contact line, section heading with
  its bottom border, role line with right-tab date, org line, bullet with the template's numbering, skills
  and credentials lines) exactly as the one-off `render_template.py` did for the Shield AI package.
- Section title mapping is user-configurable (e.g. Projects -> "SELECTED PROGRAMS & PROJECTS"); provenance and
  guardrails are unchanged because only presentation changes.
- Fall back to the built-in ATS-safe layout when no template is set; the PDF is produced from the templated
  DOCX by the worker as today.
