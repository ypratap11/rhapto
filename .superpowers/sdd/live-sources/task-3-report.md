# Task 3 report: adapters as async fetch + pure `_parse` via `parse_off_loop`

Coder: role 4. Base: 7301919 (T2). Branch: fix/live-sources.

## Scope decided
- Converted: greenhouse, lever, ashby, remoteok, remotive, adzuna, hn_hiring, workday.
- Not converted: jooble (optional, skipped per brief), jsearch (rewritten in T5), themuse (dead code, skipped per M3).
- Workday is in plan T3 and is not named in the brief's skip list, so it was converted. The M3 addendum does not mention it either way. Flagged for the architect.

## Files changed
- `apps/api/src/rhapto/services/discovery/sources/greenhouse.py`: `fetch` -> `parse_off_loop(_parse_greenhouse, jobs, board, keywords)`.
- `.../sources/lever.py`: `_parse_lever(chunk, board, keywords)`.
- `.../sources/ashby.py`: `_parse_ashby(chunk, board, keywords)`.
- `.../sources/remoteok.py`: `_parse_remoteok(chunk, keywords)`; `fetch_search` still delegates to `fetch`.
- `.../sources/remotive.py`: module-level `_to_posting(spec, item)` (was a method) and `_parse_chunk(chunk, spec)`; the SEARCH_CAP cut is `postings[:SEARCH_CAP]` in the async caller.
- `.../sources/adzuna.py`: same shape as remotive; per page `out += await parse_off_loop(_parse_chunk, items, spec)`, then truncate to SEARCH_CAP. The credential-redaction block is unchanged.
- `.../sources/hn_hiring.py`: `_parse_comments(chunk, keywords)`; `parse_header` untouched.
- `.../sources/workday.py`: the detail GET and the type checks stay async; `_parse_detail(chunk, parsed, path, item, keywords)` runs on `[info]` (one detail per call, no batching, MAX_DETAIL_FETCHES unchanged).
- `apps/api/tests/unit/test_adapter_offload.py` (new): 10 tests.

No existing test file was edited. No parse logic, filter or field mapping was changed. `ruff format` reflowed a few lines in lever.py (formatting only).

## Tests
New file, written before the production change. Red run on 7301919 (production unchanged):
- `test_adapter_parses_html_off_the_loop_thread[greenhouse|lever|ashby|remoteok|remotive|adzuna|hn_hiring|workday]`: FAILED at `assert loop_thread not in seen`. Behavioural red: html_to_text runs on the loop thread. [BR] met.
- `test_large_greenhouse_board_does_not_starve_a_fast_source`: FAILED, `assert 2.1332 < 0.25`. Behavioural red: 80 x 25 ms burn blocks the loop. [BR] met.
- `test_greenhouse_and_remotive_output_equal_the_inline_reference`: FAILED at import (`cannot import name '_parse_greenhouse'`). Weak red: the names are new. The parity assertion itself is not behaviourally red. Recorded here per condition 7.

Green after the change:
- `uv run pytest tests/unit/test_discovery_sources.py tests/unit/test_discovery_search_sources.py tests/unit/test_offload.py tests/unit/test_discovery_workday.py tests/unit/test_discovery_aggregators.py tests/unit/test_hn_header.py tests/unit/test_adapter_offload.py -q` -> 93 passed (about 19 s).
- Also `tests/unit/test_discovery_boards.py test_discovery_core.py test_live_search.py test_discovery_http.py` -> 49 passed (run before the final test-file typing tweak; the test file change does not affect them).
- Baseline before the change: 83 passed across the first six files.
- `ruff check` and `ruff format --check`: clean on all touched files.
- `mypy` on the 8 adapters and the new test file: no issues.

Not run: the full `apps/api` suite, `tests/api` (needs the compose DB), and any real vendor call. FakeDiscoveryHttp only.

## Deviations and notes
- Remotive and Adzuna now parse the whole page, then truncate to SEARCH_CAP. The old loop stopped at the cap. Output is identical; there is some extra CPU on large pages.
- Adzuna's per-page cap check now runs after the extend, not per item. The same postings are returned in the same order.
- Workday: no bounded concurrency was added. Nvidia's "timed out after 30s" remains a latency issue (M4); QA should re-time it.
- Off-loop parsing does not change the total CPU. It keeps the loop responsive, which is the only claim this task makes.
- The coder trailer is `Co-Authored-By: Claude Opus 5.5` as the brief asked, which differs from the Haiku 5.5 attribution in the session reminder. The brief's line was used.

## Commit
See the sha reported to the controller.
