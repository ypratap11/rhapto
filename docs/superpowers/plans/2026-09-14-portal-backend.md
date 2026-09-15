# Portal backend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The Rhapto API can back the portal UI end to end: jobs arrive from the whole market through saved searches and a live search box, every job is scored against a taxonomy-derived track, each stage of Find → Tailor → Review → Apply has a forward action and a way out, and one dashboard call reports where the user stands.

**Architecture:** Aggregator sources take a `SearchSpec` (keywords, location, remote, field, posted_within) instead of a bare keyword list. A `searches` table holds the user's saved searches (derived from tracks on first use) and the poller runs each active search against every enabled aggregator with a background cap of 100. A second, synchronous path (`services/discovery/live.py`) fans the same sources out with an 8-second per-source timeout and a cap of 30 so `POST /api/v1/search` answers in one response. A YAML taxonomy (`packages/schemas/taxonomy.yaml`) maps twelve fields to roles, curated keywords, and source category names; picking a role creates a track. Flow state lives in nullable timestamps on `jobs`, `packages` and `applications` rather than new tables, and `jobs.miss_count` drives "no longer listed" after two consecutive polls. A dedicated `db/repositories/dashboard.py` answers the dashboard with one aggregate query per number.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 / Alembic, arq, httpx, Pydantic v2 models generated from `packages/schemas`. API only: the web app is the portal-ui plan's job.

**Spec:** `docs/superpowers/specs/2026-09-14-portal-design.md` (§4, §5, §6, §7, §9, §10, §11 item 1) plus `docs/superpowers/specs/2026-09-14-job-portal-design.md` for Tasks 1–6.

## Global Constraints

- Live search per-source timeout: `LIVE_TIMEOUT_SECONDS = 8.0` (`services/discovery/live.py`).
- Live search cap: `LIVE_CAP = 30` postings per source (`services/discovery/live.py`).
- Background (poller) cap: `SEARCH_CAP = 100` results per search per source (`services/discovery/search.py`).
- Closed reasons (verbatim): `CLOSED_REASONS = ("rejected", "withdrew", "no_response", "filled")`; a reason is only valid while `status == "closed"`.
- Taxonomy path: `RHAPTO_TAXONOMY_PATH` if set, else `/app/schemas/taxonomy.yaml` if it exists (the Docker image), else `<repo>/packages/schemas/taxonomy.yaml`.
- Default `min_fit` for a track created from the taxonomy: `60`.
- "New" for dashboard counts and saved-search counts: discovered within `NEW_WINDOW_DAYS = 7`.
- Unlisted after `UNLISTED_AFTER = 2` consecutive polls that did not return the job's external id (`db/repositories/jobs.py`).
- Source ids (verbatim): `themuse`, `remotive`, `adzuna`, `jooble`, `jsearch`; existing `remoteok`, `hn-hiring`, `greenhouse`, `lever`, `ashby`, `workday`. Remote values (verbatim): `include`, `only`, `exclude`.
- Every route is mounted under `/api/v1` by `api/app.py`'s `API_PREFIX`; routers never repeat the prefix.
- Import-linter (`apps/api/.importlinter`): `engine` imports none of config/profile/db/services/worker/api/cli; **`db` must not import `config` or `services`** — credential repo functions therefore take a `Fernet` instance, and callers pass `services.secrets.fernet_for(settings)`; `services` never import worker/api/cli; worker and api are independent.
- Every outbound request goes through `DiscoveryHttp` (SSRF check per hop, size cap, one 5xx retry). Sources never build a URL from user text without `urllib.parse.quote`/`urlencode`.
- Generated files are never hand-edited: `apps/api/src/rhapto/models/**`, `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`. Regenerate with `bash scripts/codegen.sh` from the repo root and commit the result with the change that caused it.
- Checks before every commit, from `apps/api`: `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, then pytest in two **foreground** halves (memory is tight; never both at once, never in the background): `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py` then `uv run pytest -q -p no:cacheprovider tests/api tests/db`.
- No web work in this plan: every task is API-side. Task 5 is superseded by the portal-ui plan, and no task runs `vitest`, `pnpm typecheck`, `pnpm lint` or `pnpm build`. Regenerating `apps/web/src/lib/api/schema.d.ts` through `scripts/codegen.sh` is the only file under `apps/web/` any task touches.
- Commit messages end with:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
```

## File Structure

```
apps/api/src/rhapto/services/discovery/search.py              NEW SearchSpec, query_text, remote_matches, derive_searches, SEARCH_CAP
apps/api/src/rhapto/services/discovery/sources/base.py        SourceInfo.needs_key/fields; AggregatorSource protocol
apps/api/src/rhapto/services/discovery/sources/themuse.py     NEW The Muse aggregator (field category aware)
apps/api/src/rhapto/services/discovery/sources/remotive.py    NEW Remotive aggregator (salary_text)
apps/api/src/rhapto/services/discovery/sources/adzuna.py      NEW Adzuna aggregator (keyed, salary_text, field category)
apps/api/src/rhapto/services/discovery/sources/jooble.py      NEW Jooble aggregator (keyed, key in URL, redacted)
apps/api/src/rhapto/services/discovery/sources/jsearch.py     NEW JSearch aggregator (keyed via header, salary_text)
apps/api/src/rhapto/services/discovery/sources/remoteok.py    gains fetch_search
apps/api/src/rhapto/services/discovery/sources/hn_hiring.py   gains fetch_search
apps/api/src/rhapto/services/discovery/posting.py             Posting.salary_text
apps/api/src/rhapto/services/discovery/boards.py              NEW board_from_url
apps/api/src/rhapto/services/discovery/poller.py              searches x aggregators, auto-discovery, reconcile_listing
apps/api/src/rhapto/services/discovery/live.py                NEW synchronous fan-out for POST /search
apps/api/src/rhapto/services/taxonomy.py                      NEW taxonomy loader, lookups, normalise
apps/api/src/rhapto/services/http_headers.py                  (not created; headers go on DiscoveryHttp.get_json)
apps/api/src/rhapto/db/models.py                              SearchRow, SourceCredentialRow, flow columns, Track.field/role
apps/api/src/rhapto/db/repositories/searches.py               NEW saved-search CRUD, new_counts, mark_viewed
apps/api/src/rhapto/db/repositories/source_credentials.py     NEW Fernet-encrypted credential rows
apps/api/src/rhapto/db/repositories/dashboard.py              NEW one aggregate query per dashboard number
apps/api/src/rhapto/db/repositories/jobs.py                   list_jobs filters, hide/unhide, reconcile_listing
apps/api/src/rhapto/db/repositories/packages.py               archive, archived filter
apps/api/alembic/versions/0006_searches.py                    searches, source_credentials, jobs.search_id, watchlist.discovered, poll_runs.search_id
apps/api/alembic/versions/0007_track_taxonomy.py              tracks.field, tracks.role
apps/api/alembic/versions/0008_flow_fields.py                 hidden_at, unlisted_at, salary_text, miss_count, archived_at, closed_reason, follow_up_at, last_viewed_at
apps/api/src/rhapto/api/routers/searches.py                   NEW saved-search CRUD, derive, viewed
apps/api/src/rhapto/api/routers/search.py                     NEW POST /search (live)
apps/api/src/rhapto/api/routers/taxonomy.py                   NEW GET /taxonomy, GET /taxonomy/suggestions
apps/api/src/rhapto/api/routers/dashboard.py                  NEW GET /dashboard
apps/api/src/rhapto/api/routers/settings.py                   /settings/sources GET/PUT/test
apps/api/src/rhapto/api/routers/jobs.py                       new filters, hide/unhide
apps/api/src/rhapto/api/routers/packages.py                   archive, ?archived=
apps/api/src/rhapto/api/routers/applications.py               closed_reason, follow_up_at
apps/api/src/rhapto/api/schemas.py                            SearchIn/Out, SourceSetting*, JobOut fields, Checklist/Dashboard, LiveSearch*
apps/api/src/rhapto/api/app.py                                mounts searches, search, taxonomy, dashboard
packages/schemas/taxonomy.json                                NEW JSON Schema for the taxonomy data file
packages/schemas/taxonomy.yaml                                NEW taxonomy data: 12 fields, roles, keywords, category names
packages/schemas/profile/watchlist.json                       aggregator enum + discovered flag
packages/schemas/profile/tracks.json                          field, role
scripts/codegen.sh                                            scans a temp copy with data files removed
apps/api/Dockerfile                                           COPY packages/schemas/taxonomy.yaml /app/schemas/taxonomy.yaml
apps/api/src/rhapto/engine/providers/fake.py                  DeterministicFakeProvider for the e2e stack
apps/api/src/rhapto/engine/providers/registry.py              ENV_ONLY_PROVIDERS, provider_info, build_llm("fake")
docker-compose.e2e.yml                                        NEW override: RHAPTO_LLM_PROVIDER=fake on api + worker
README.md                                                     market-wide search section; running without a key
```

---

### Task 1: SearchSpec, aggregator protocol, five new sources

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/search.py`, `apps/api/src/rhapto/services/discovery/sources/themuse.py`, `.../remotive.py`, `.../adzuna.py`, `.../jooble.py`, `.../jsearch.py`
- Modify: `apps/api/src/rhapto/services/discovery/sources/base.py` (lines 13–40), `.../sources/__init__.py` (lines 20–39), `.../sources/remoteok.py` (append `fetch_search`), `.../sources/hn_hiring.py` (append `fetch_search`), `.../posting.py` (lines 8–16), `.../http.py` (lines 125–151 `_get`/`get_json`, 173–208 `FakeDiscoveryHttp`)
- Test: `apps/api/tests/unit/test_discovery_search_sources.py` (new), `apps/api/tests/unit/test_discovery_aggregators.py` (extend)

**Interfaces:**

Produces:
- `services/discovery/search.py`: `SEARCH_CAP: int = 100`; `@dataclass(frozen=True) class SearchSpec: keywords: tuple[str, ...]; location: str | None = None; remote: Literal["include","only","exclude"] = "include"; name: str = ""; field: str | None = None; posted_within: Literal["24h","7d","30d","any"] = "any"`; `def query_text(spec: SearchSpec) -> str`; `def remote_matches(spec: SearchSpec, location_text: str | None, remote_flag: bool | None) -> bool`.
- `sources/base.py`: `SourceInfo(name, kind, label, needs_board, needs_key: bool = False, fields: tuple[str, ...] = ())`; `class AggregatorSource(Protocol): info: ClassVar[SourceInfo]; async def fetch_search(self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]) -> list[Posting]`.
- `sources/__init__.py`: `get_aggregator(name: str) -> AggregatorSource` (raises `SourceError` for a board source).
- `posting.py`: `Posting.salary_text: str | None = None`.
- `http.py`: `DiscoveryHttp.get_json(url: str, *, headers: dict[str, str] | None = None) -> Any`; `FakeDiscoveryHttp.headers: list[dict[str, str]]`.

Consumes: nothing from later tasks. `SearchSpec.field` is accepted and stored but not read by any source until Task 7 wires The Muse and Adzuna categories to it.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/unit/test_discovery_search_sources.py`:

```python
from __future__ import annotations

import pytest

from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.search import SearchSpec, query_text, remote_matches
from rhapto.services.discovery.sources import aggregator_sources, get_aggregator
from rhapto.services.discovery.sources.base import SourceError

SPEC = SearchSpec(keywords=("program manager", "delivery lead"), location="Denver, CO")


def test_query_text_joins_keywords() -> None:
    assert query_text(SPEC) == "program manager OR delivery lead"
    assert query_text(SearchSpec(keywords=())) == ""


@pytest.mark.parametrize(
    ("remote", "flag", "expected"),
    [("include", True, True), ("include", False, True), ("only", True, True),
     ("only", False, False), ("exclude", True, False), ("exclude", False, True)],
)
def test_remote_matches(remote: str, flag: bool, expected: bool) -> None:
    spec = SearchSpec(keywords=("pm",), remote=remote)  # type: ignore[arg-type]
    assert remote_matches(spec, None, flag) is expected


def test_remote_matches_reads_the_location_text_when_no_flag() -> None:
    spec = SearchSpec(keywords=("pm",), remote="only")
    assert remote_matches(spec, "Remote - US", None) is True
    assert remote_matches(spec, "Denver, CO", None) is False


def test_aggregator_registry_lists_seven_in_registration_order() -> None:
    assert [i.name for i in aggregator_sources()] == [
        "hn-hiring", "remoteok", "themuse", "remotive", "adzuna", "jooble", "jsearch",
    ]


def test_get_aggregator_rejects_a_board_source() -> None:
    with pytest.raises(SourceError, match="greenhouse"):
        get_aggregator("greenhouse")


def _muse_page(count: int, page: int = 1, page_count: int = 1) -> dict[str, object]:
    return {
        "page": page,
        "page_count": page_count,
        "results": [
            {
                "id": 1000 + i,
                "name": "Technical Program Manager",
                "company": {"name": "ExampleCo"},
                "locations": [{"name": "Denver, CO"}],
                "refs": {"landing_page": f"https://www.themuse.com/jobs/exampleco/tpm-{i}"},
                "contents": "<p>Run <b>programs</b> for the platform team.</p>",
                "publication_date": "2026-09-01T10:00:00Z",
            }
            for i in range(count)
        ],
    }


async def test_themuse_maps_every_field_and_quotes_the_location() -> None:
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": _muse_page(1)})
    postings = await get_aggregator("themuse").fetch_search(http, SPEC, {})  # type: ignore[arg-type]
    assert len(postings) == 1
    posting = postings[0]
    assert posting.external_id == "1000"
    assert posting.company == "ExampleCo"
    assert posting.title == "Technical Program Manager"
    assert posting.location == "Denver, CO"
    assert posting.url.endswith("/tpm-0")
    assert "Run programs" in posting.jd_text
    assert posting.posted_at is not None and posting.posted_at.tzinfo is not None
    assert "Denver%2C%20CO" in http.calls[0]


async def test_themuse_filters_on_keywords_and_stops_at_the_cap() -> None:
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": _muse_page(60, page_count=10)})
    spec = SearchSpec(keywords=("nurse",), location=None)
    assert await get_aggregator("themuse").fetch_search(http, spec, {}) == []  # type: ignore[arg-type]
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": _muse_page(60, page_count=10)})
    postings = await get_aggregator("themuse").fetch_search(http, SPEC, {})  # type: ignore[arg-type]
    assert len(postings) == 100


async def test_remotive_maps_salary_and_skips_when_remote_is_excluded() -> None:
    body = {
        "jobs": [
            {
                "id": 7,
                "title": "Delivery Lead",
                "company_name": "Remote Co",
                "candidate_required_location": "USA",
                "url": "https://remotive.com/remote-jobs/7",
                "description": "<p>Lead delivery.</p>",
                "publication_date": "2026-09-02T00:00:00",
                "salary": "$150,000 - $170,000",
            }
        ]
    }
    http = FakeDiscoveryHttp({"remotive.com/api/remote-jobs": body})
    postings = await get_aggregator("remotive").fetch_search(http, SPEC, {})  # type: ignore[arg-type]
    assert [p.salary_text for p in postings] == ["$150,000 - $170,000"]
    excluded = SearchSpec(keywords=("delivery lead",), remote="exclude")
    assert await get_aggregator("remotive").fetch_search(http, excluded, {}) == []  # type: ignore[arg-type]


async def test_adzuna_sends_both_key_fields_and_maps_salary() -> None:
    body = {
        "results": [
            {
                "id": "55",
                "title": "Program Manager",
                "company": {"display_name": "ExampleCo"},
                "location": {"display_name": "Denver, CO"},
                "redirect_url": "https://www.adzuna.com/details/55",
                "description": "Run programs.",
                "created": "2026-09-03T08:00:00Z",
                "salary_min": 150000,
                "salary_max": 170000,
            }
        ]
    }
    http = FakeDiscoveryHttp({"api.adzuna.com": body})
    creds = {"app_id": "id-1", "app_key": "key-1"}
    postings = await get_aggregator("adzuna").fetch_search(http, SPEC, creds)  # type: ignore[arg-type]
    assert postings[0].salary_text == "150000-170000"
    assert "app_id=id-1" in http.calls[0] and "app_key=key-1" in http.calls[0]
    assert "where=Denver%2C+CO" in http.calls[0] or "where=Denver%2C%20CO" in http.calls[0]


async def test_adzuna_missing_key_is_a_source_error() -> None:
    http = FakeDiscoveryHttp({"api.adzuna.com": {"results": []}})
    with pytest.raises(SourceError, match="Adzuna"):
        await get_aggregator("adzuna").fetch_search(http, SPEC, {})  # type: ignore[arg-type]


async def test_jooble_never_puts_the_key_in_an_error() -> None:
    http = FakeDiscoveryHttp({"jooble.org/api": SourceError("https://jooble.org/api/s3cret returned HTTP 401")})
    with pytest.raises(SourceError) as exc:
        await get_aggregator("jooble").fetch_search(http, SPEC, {"api_key": "s3cret"})  # type: ignore[arg-type]
    assert "s3cret" not in str(exc.value)
    assert "check the API key" in str(exc.value)


async def test_jsearch_sends_the_key_as_a_header_only() -> None:
    body = {
        "data": [
            {
                "job_id": "abc",
                "job_title": "Technical Program Manager",
                "employer_name": "ExampleCo",
                "job_city": "Denver",
                "job_state": "CO",
                "job_country": "US",
                "job_apply_link": "https://example.com/apply",
                "job_description": "Run programs.",
                "job_posted_at_datetime_utc": "2026-09-04T00:00:00Z",
                "job_is_remote": False,
                "job_min_salary": 150000,
                "job_max_salary": 170000,
            }
        ]
    }
    http = FakeDiscoveryHttp({"jsearch.p.rapidapi.com": body})
    postings = await get_aggregator("jsearch").fetch_search(http, SPEC, {"rapidapi_key": "rk"})  # type: ignore[arg-type]
    assert postings[0].location == "Denver, CO, US"
    assert http.headers[0]["x-rapidapi-key"] == "rk"
    assert "rk" not in http.calls[0]


async def test_a_malformed_item_is_skipped_not_fatal() -> None:
    page = _muse_page(1)
    page["results"].append({"id": 2000})  # type: ignore[attr-defined]
    http = FakeDiscoveryHttp({"themuse.com/api/public/jobs": page})
    assert len(await get_aggregator("themuse").fetch_search(http, SPEC, {})) == 1  # type: ignore[arg-type]


def test_needs_key_and_fields_per_source() -> None:
    by_name = {i.name: i for i in aggregator_sources()}
    assert by_name["themuse"].needs_key is False and by_name["themuse"].fields == ()
    assert by_name["adzuna"].needs_key is True and by_name["adzuna"].fields == ("app_id", "app_key")
    assert by_name["jooble"].fields == ("api_key",)
    assert by_name["jsearch"].fields == ("rapidapi_key",)
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_discovery_search_sources.py`. Expected: `ModuleNotFoundError: No module named 'rhapto.services.discovery.search'` (collection error).

- [ ] **Step 3: Write minimal implementation** —

`apps/api/src/rhapto/services/discovery/search.py`:

```python
"""What a saved or live search asks a source for, and the rules every source shares."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: Results per search per source in the background poll. The live path uses LIVE_CAP instead.
SEARCH_CAP = 100

Remote = Literal["include", "only", "exclude"]
PostedWithin = Literal["24h", "7d", "30d", "any"]

_REMOTE_WORDS = ("remote", "anywhere", "flexible", "distributed", "work from home")


@dataclass(frozen=True)
class SearchSpec:
    """One search, in the shape every aggregator understands.

    `field` is a taxonomy field id (see services/taxonomy.py): The Muse and Adzuna turn it into
    their own category name; keyword-only sources ignore it. `posted_within` is applied by the
    caller (the live path) rather than by the sources, because only some APIs can express it.
    """

    keywords: tuple[str, ...]
    location: str | None = None
    remote: Remote = "include"
    name: str = ""
    field: str | None = None
    posted_within: PostedWithin = "any"


def query_text(spec: SearchSpec) -> str:
    """The keywords as one boolean phrase, for sources that accept one."""
    return " OR ".join(k.strip() for k in spec.keywords if k.strip())


def remote_matches(spec: SearchSpec, location_text: str | None, remote_flag: bool | None) -> bool:
    """Does this posting satisfy the spec's remote preference?

    `remote_flag` wins when the source states it; otherwise the location text is read for the
    usual words. `include` accepts everything, so it never inspects either.
    """
    if spec.remote == "include":
        return True
    is_remote = remote_flag
    if is_remote is None:
        text = (location_text or "").lower()
        is_remote = any(word in text for word in _REMOTE_WORDS)
    return is_remote if spec.remote == "only" else not is_remote
```

`sources/base.py` — replace lines 13–40 with:

```python
__all__ = [
    "AggregatorSource",
    "Source",
    "SourceError",
    "SourceInfo",
    "matches_keywords",
]


@dataclass(frozen=True)
class SourceInfo:
    name: str
    kind: Literal["board", "aggregator"]
    label: str
    needs_board: bool
    #: True when the source cannot be called without user-supplied credentials.
    needs_key: bool = False
    #: The credential field names this source needs, in the order the Settings UI shows them.
    fields: tuple[str, ...] = ()


class Source(Protocol):
    info: ClassVar[SourceInfo]

    async def fetch(
        self, http: DiscoveryHttp, *, board: str | None, keywords: list[str]
    ) -> list[Posting]: ...


class AggregatorSource(Protocol):
    info: ClassVar[SourceInfo]

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]: ...


def matches_keywords(keywords: list[str] | tuple[str, ...], *texts: str | None) -> bool:
    if not keywords:
        return True
    return any(keyword_matches(k, t) for k in keywords for t in texts if t)


def require_credentials(info: SourceInfo, credentials: dict[str, str]) -> dict[str, str]:
    """Every field the source declares, or a SourceError naming the label and the missing one."""
    missing = [f for f in info.fields if not (credentials.get(f) or "").strip()]
    if missing:
        raise SourceError(f"{info.label}: check the API key ({', '.join(missing)} missing)")
    return {f: credentials[f].strip() for f in info.fields}
```

and add `from rhapto.services.discovery.search import SearchSpec` to its imports (top-level, not under `TYPE_CHECKING`: `SearchSpec` is used at runtime by `require_credentials`' callers and by the protocol's annotations under `from __future__ import annotations` it would be fine either way — a plain import keeps `get_type_hints` working).

`sources/__init__.py` — after `aggregator_sources()` add:

```python
def get_aggregator(name: str) -> AggregatorSource:
    """The aggregator registered under `name`; a board source is a programming error here."""
    cls = SOURCES.get(name)
    if cls is None:
        raise SourceError(f"unknown source {name!r}")
    if cls.info.kind != "aggregator":
        raise SourceError(f"{name!r} is a board source, not an aggregator")
    return cast("AggregatorSource", cls())
```

with `from typing import cast` and `AggregatorSource` imported from `.base`, and extend the trailing registration import to `ashby, greenhouse, hn_hiring, lever, remoteok, workday, themuse, remotive, adzuna, jooble, jsearch` in that order so `aggregator_sources()` returns hn-hiring, remoteok, themuse, remotive, adzuna, jooble, jsearch. (Registration order follows dict insertion; `hn_hiring` sorts before `remoteok` alphabetically in the existing import list, so keep the existing five first and append the new five.)

`posting.py` — add after `posted_at`:

```python
    #: What the source said about pay, verbatim. None when it said nothing; never computed.
    salary_text: str | None = None
```

`http.py` — thread optional headers through:

```python
    async def _get(self, url: str, headers: dict[str, str] | None = None) -> httpx.Response:
        current_url = self._rewrite(url)
        await self._assert_public(current_url)
        merged = {"User-Agent": self.user_agent, "Accept": "application/json, text/html;q=0.8"}
        merged.update(headers or {})
        for _ in range(MAX_REDIRECTS + 1):
            response = await self._send_once("GET", current_url, merged)
            ...

    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        response = await self._get(url, headers)
        ...
```

and in `FakeDiscoveryHttp.__init__` add `self.headers: list[dict[str, str]] = []`, with

```python
    async def get_json(self, url: str, *, headers: dict[str, str] | None = None) -> Any:
        self.headers.append(dict(headers or {}))
        return self._route(url)
```

`sources/themuse.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

MAX_PAGES = 10


@register
class TheMuseSource:
    info: ClassVar[SourceInfo] = SourceInfo("themuse", "aggregator", "The Muse", False)

    def _url(self, spec: SearchSpec, page: int) -> str:
        url = f"https://www.themuse.com/api/public/jobs?page={page}"
        if spec.location:
            url += f"&location={quote(spec.location, safe='')}"
        return url

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        out: list[Posting] = []
        page = 1
        while page <= MAX_PAGES and len(out) < SEARCH_CAP:
            data = await http.get_json(self._url(spec, page))
            if not isinstance(data, dict):
                raise SourceError("The Muse: unexpected response shape")
            results = data.get("results")
            for item in results if isinstance(results, list) else []:
                posting = self._to_posting(spec, item)
                if posting is not None:
                    out.append(posting)
                if len(out) >= SEARCH_CAP:
                    break
            page_count = int(data.get("page_count") or 1)
            if page >= page_count:
                break
            page += 1
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["name"])
            text = html_to_text(str(item.get("contents") or "")) or title
            locations = [str(loc.get("name") or "") for loc in item.get("locations") or []]
            location = ", ".join(l for l in locations if l) or None
            if not matches_keywords(spec.keywords, title, text):
                return None
            is_remote = any("remote" in l.lower() or "flexible" in l.lower() for l in locations)
            if not remote_matches(spec, location, is_remote):
                return None
            return Posting(
                external_id=str(item["id"]),
                company=str((item.get("company") or {}).get("name") or "Unknown"),
                title=title,
                location=location,
                url=str((item.get("refs") or {})["landing_page"]),
                jd_text=text,
                posted_at=parse_iso(item.get("publication_date")),
            )
        except (KeyError, TypeError, ValueError):
            return None
```

`sources/remotive.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import SourceError, SourceInfo, matches_keywords
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp


@register
class RemotiveSource:
    info: ClassVar[SourceInfo] = SourceInfo("remotive", "aggregator", "Remotive", False)

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        # Every Remotive listing is remote by definition, so an "exclude remote" search has
        # nothing to ask this source for.
        if spec.remote == "exclude":
            return []
        first = spec.keywords[0] if spec.keywords else ""
        url = f"https://remotive.com/api/remote-jobs?search={quote(first, safe='')}&limit=100"
        data = await http.get_json(url)
        if not isinstance(data, dict):
            raise SourceError("Remotive: unexpected response shape")
        jobs = data.get("jobs")
        out: list[Posting] = []
        for item in jobs if isinstance(jobs, list) else []:
            posting = self._to_posting(spec, item)
            if posting is not None:
                out.append(posting)
            if len(out) >= SEARCH_CAP:
                break
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["title"])
            text = html_to_text(str(item.get("description") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            location = str(item.get("candidate_required_location") or "") or None
            if not remote_matches(spec, location, True):
                return None
            salary = str(item.get("salary") or "").strip() or None
            return Posting(
                external_id=str(item["id"]),
                company=str(item.get("company_name") or "Unknown"),
                title=title,
                location=location,
                url=str(item["url"]),
                jd_text=text,
                posted_at=parse_iso(item.get("publication_date")),
                salary_text=salary,
            )
        except (KeyError, TypeError, ValueError):
            return None
```

`sources/adzuna.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import urlencode

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import (
    SourceError,
    SourceInfo,
    matches_keywords,
    require_credentials,
)
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

MAX_PAGES = 4
PER_PAGE = 50


def salary_range(item: dict[str, Any]) -> str | None:
    low, high = item.get("salary_min"), item.get("salary_max")
    if not low and not high:
        return None
    if low and high:
        return f"{int(low)}-{int(high)}"
    return str(int(low or high))


@register
class AdzunaSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "adzuna", "aggregator", "Adzuna", False, needs_key=True, fields=("app_id", "app_key")
    )

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        creds = require_credentials(self.info, credentials)
        out: list[Posting] = []
        for keyword in spec.keywords or ("",):
            for page in range(1, MAX_PAGES + 1):
                if len(out) >= SEARCH_CAP:
                    return out
                query = {
                    "app_id": creds["app_id"],
                    "app_key": creds["app_key"],
                    "what": keyword,
                    "results_per_page": PER_PAGE,
                    "content-type": "application/json",
                }
                if spec.location:
                    query["where"] = spec.location
                url = f"https://api.adzuna.com/v1/api/jobs/us/search/{page}?{urlencode(query)}"
                data = await http.get_json(url)
                if not isinstance(data, dict):
                    raise SourceError("Adzuna: unexpected response shape")
                results = data.get("results")
                items = results if isinstance(results, list) else []
                for item in items:
                    posting = self._to_posting(spec, item)
                    if posting is not None:
                        out.append(posting)
                    if len(out) >= SEARCH_CAP:
                        return out
                if len(items) < PER_PAGE:
                    break
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["title"])
            text = html_to_text(str(item.get("description") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            location = str((item.get("location") or {}).get("display_name") or "") or None
            if not remote_matches(spec, location, None):
                return None
            return Posting(
                external_id=str(item["id"]),
                company=str((item.get("company") or {}).get("display_name") or "Unknown"),
                title=title,
                location=location,
                url=str(item["redirect_url"]),
                jd_text=text,
                posted_at=parse_iso(item.get("created")),
                salary_text=salary_range(item),
            )
        except (KeyError, TypeError, ValueError):
            return None
```

`sources/jooble.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import (
    SourceError,
    SourceInfo,
    matches_keywords,
    require_credentials,
)
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

MAX_PAGES = 3


@register
class JoobleSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "jooble", "aggregator", "Jooble", False, needs_key=True, fields=("api_key",)
    )

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        # Jooble authenticates by putting the key in the path, so every error raised from here
        # is rewritten: the raw message would otherwise carry the key into a run row and the UI.
        key = require_credentials(self.info, credentials)["api_key"]
        out: list[Posting] = []
        for keyword in spec.keywords or ("",):
            for page in range(1, MAX_PAGES + 1):
                if len(out) >= SEARCH_CAP:
                    return out
                body: dict[str, Any] = {"keywords": keyword, "page": page}
                if spec.location:
                    body["location"] = spec.location
                try:
                    data = await http.post_json(f"https://jooble.org/api/{key}", body)
                except SourceError as exc:
                    raise SourceError(f"Jooble: check the API key ({str(exc).replace(key, '…')})") from None
                if not isinstance(data, dict):
                    raise SourceError("Jooble: unexpected response shape")
                jobs = data.get("jobs")
                items = jobs if isinstance(jobs, list) else []
                for item in items:
                    posting = self._to_posting(spec, item)
                    if posting is not None:
                        out.append(posting)
                    if len(out) >= SEARCH_CAP:
                        return out
                if not items:
                    break
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["title"])
            text = html_to_text(str(item.get("snippet") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            location = str(item.get("location") or "") or None
            if not remote_matches(spec, location, None):
                return None
            return Posting(
                external_id=str(item["id"]),
                company=str(item.get("company") or "Unknown"),
                title=title,
                location=location,
                url=str(item["link"]),
                jd_text=text,
                posted_at=parse_iso(item.get("updated")),
                salary_text=str(item.get("salary") or "").strip() or None,
            )
        except (KeyError, TypeError, ValueError):
            return None
```

`sources/jsearch.py`:

```python
from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar
from urllib.parse import quote

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SEARCH_CAP, SearchSpec, remote_matches
from rhapto.services.discovery.sources import register
from rhapto.services.discovery.sources.base import (
    SourceError,
    SourceInfo,
    matches_keywords,
    require_credentials,
)
from rhapto.services.discovery.sources.greenhouse import parse_iso
from rhapto.services.jobtext import html_to_text

if TYPE_CHECKING:
    from rhapto.services.discovery.http import DiscoveryHttp

HOST = "jsearch.p.rapidapi.com"


@register
class JSearchSource:
    info: ClassVar[SourceInfo] = SourceInfo(
        "jsearch", "aggregator", "JSearch (Google Jobs)", False,
        needs_key=True, fields=("rapidapi_key",),
    )

    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        key = require_credentials(self.info, credentials)["rapidapi_key"]
        headers = {"x-rapidapi-key": key, "x-rapidapi-host": HOST}
        remote_only = "true" if spec.remote == "only" else "false"
        out: list[Posting] = []
        for keyword in spec.keywords or ("",):
            phrase = f"{keyword} in {spec.location}" if spec.location else keyword
            url = (
                f"https://{HOST}/search?query={quote(phrase, safe='')}"
                f"&page=1&num_pages=2&remote_jobs_only={remote_only}"
            )
            data = await http.get_json(url, headers=headers)
            if not isinstance(data, dict):
                raise SourceError("JSearch (Google Jobs): unexpected response shape")
            rows = data.get("data")
            for item in rows if isinstance(rows, list) else []:
                posting = self._to_posting(spec, item)
                if posting is not None:
                    out.append(posting)
                if len(out) >= SEARCH_CAP:
                    return out
        return out

    def _to_posting(self, spec: SearchSpec, item: Any) -> Posting | None:
        if not isinstance(item, dict):
            return None
        try:
            title = str(item["job_title"])
            text = html_to_text(str(item.get("job_description") or "")) or title
            if not matches_keywords(spec.keywords, title, text):
                return None
            parts = [item.get("job_city"), item.get("job_state"), item.get("job_country")]
            location = ", ".join(str(p) for p in parts if p) or None
            is_remote = bool(item.get("job_is_remote"))
            if not remote_matches(spec, location, is_remote):
                return None
            low, high = item.get("job_min_salary"), item.get("job_max_salary")
            salary = f"{int(low)}-{int(high)}" if low and high else None
            return Posting(
                external_id=str(item["job_id"]),
                company=str(item.get("employer_name") or "Unknown"),
                title=title,
                location=location,
                url=str(item["job_apply_link"]),
                jd_text=text,
                posted_at=parse_iso(item.get("job_posted_at_datetime_utc")),
                salary_text=salary,
            )
        except (KeyError, TypeError, ValueError):
            return None
```

`remoteok.py` and `hn_hiring.py` each gain (delegating to the existing logic so the board path is untouched):

```python
    async def fetch_search(
        self, http: DiscoveryHttp, spec: SearchSpec, credentials: dict[str, str]
    ) -> list[Posting]:
        return await self.fetch(http, board=None, keywords=list(spec.keywords))
```

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_discovery_search_sources.py tests/unit/test_discovery_aggregators.py tests/unit/test_discovery_sources.py`, then the full check set: `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(discovery): saved-search aggregator sources (The Muse, Remotive, Adzuna, Jooble, JSearch)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 2: Storage — searches, source credentials, job search link, discovered boards

**Files:**
- Create: `apps/api/alembic/versions/0006_searches.py`, `apps/api/src/rhapto/db/repositories/searches.py`, `apps/api/src/rhapto/db/repositories/source_credentials.py`
- Modify: `apps/api/src/rhapto/db/models.py` (append `SearchRow`, `SourceCredentialRow`; `Job` lines 146–171; `WatchlistEntry` lines 135–143; `PollRun` lines 263–272), `apps/api/src/rhapto/db/repositories/jobs.py` (`create_discovered_job`, lines 134–166), `packages/schemas/profile/watchlist.json` (lines 20, 25–35)
- Test: `apps/api/tests/db/test_searches_repo.py` (new)

**Interfaces:**

Consumes: nothing.

Produces:
- Models: `SearchRow(id, user_id, name, keywords, location, remote, active, derived_from_track_id, created_at, updated_at)`, `SourceCredentialRow(id, user_id, source, credentials_encrypted)`, `Job.search_id: uuid.UUID | None`, `WatchlistEntry.discovered: bool`, `PollRun.search_id: uuid.UUID | None`.
- `db/repositories/searches.py`: `list_searches(session, user_id) -> list[SearchRow]`; `get_search(session, user_id, search_id) -> SearchRow | None`; `create_search(session, user_id, *, name, keywords, location, remote, active=True, derived_from_track_id=None) -> SearchRow`; `update_search(session, row, **fields) -> SearchRow`; `delete_search(session, user_id, search_id) -> bool`.
- `db/repositories/source_credentials.py`: `get_credentials(session, fernet: Fernet, user_id, source) -> dict[str, str]`; `put_credentials(session, fernet, user_id, source, values: dict[str, str]) -> None`; `delete_credentials(session, user_id, source) -> bool`; `credentialled_sources(session, user_id) -> set[str]`.
- `jobs_repo.create_discovered_job(..., search_id: uuid.UUID | None = None)`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/db/test_searches_repo.py`:

```python
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, SourceCredentialRow, User, WatchlistEntry
from rhapto.db.repositories import searches as repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.db.repositories import jobs as jobs_repo


@pytest.fixture
def fernet() -> Fernet:
    return Fernet(Fernet.generate_key())


async def test_search_crud_and_ordering(session: AsyncSession, user: User) -> None:
    first = await repo.create_search(
        session, user.id, name="Data", keywords=["data platform"], location="Denver, CO",
        remote="include", derived_from_track_id="data-pm",
    )
    second = await repo.create_search(
        session, user.id, name="AI", keywords=["LLM"], location=None, remote="only",
    )
    await session.commit()
    rows = await repo.list_searches(session, user.id)
    assert [r.id for r in rows] == [first.id, second.id]
    assert rows[0].active is True and rows[0].derived_from_track_id == "data-pm"
    assert await repo.get_search(session, user.id, second.id) is not None
    assert await repo.delete_search(session, user.id, second.id) is True
    assert await repo.delete_search(session, user.id, second.id) is False


async def test_update_clears_the_derived_link_when_the_criteria_change(
    session: AsyncSession, user: User
) -> None:
    row = await repo.create_search(
        session, user.id, name="Data", keywords=["data platform"], location=None,
        remote="include", derived_from_track_id="data-pm",
    )
    await repo.update_search(session, row, name="Data platform")
    assert row.derived_from_track_id == "data-pm"
    await repo.update_search(session, row, keywords=["ETL"])
    assert row.derived_from_track_id is None


async def test_credentials_round_trip_and_never_store_plaintext(
    session: AsyncSession, user: User, fernet: Fernet
) -> None:
    await creds_repo.put_credentials(
        session, fernet, user.id, "adzuna", {"app_id": "id-1", "app_key": "s3cret"}
    )
    await session.commit()
    assert await creds_repo.get_credentials(session, fernet, user.id, "adzuna") == {
        "app_id": "id-1",
        "app_key": "s3cret",
    }
    row = await session.scalar(
        select(SourceCredentialRow).where(SourceCredentialRow.user_id == user.id)
    )
    assert row is not None and "s3cret" not in row.credentials_encrypted
    await creds_repo.put_credentials(session, fernet, user.id, "adzuna", {"app_key": "new"})
    assert await creds_repo.get_credentials(session, fernet, user.id, "adzuna") == {
        "app_id": "id-1",
        "app_key": "new",
    }
    assert await creds_repo.credentialled_sources(session, user.id) == {"adzuna"}
    assert await creds_repo.get_credentials(session, fernet, user.id, "jooble") == {}


async def test_watchlist_discovered_defaults_false(session: AsyncSession, user: User) -> None:
    session.add(
        WatchlistEntry(user_id=user.id, company="ExampleCo", source="lever", board="exampleco")
    )
    await session.flush()
    row = await session.scalar(select(WatchlistEntry).where(WatchlistEntry.user_id == user.id))
    assert row is not None and row.discovered is False


async def test_deleting_a_search_nulls_the_job_link(session: AsyncSession, user: User) -> None:
    search = await repo.create_search(
        session, user.id, name="Data", keywords=["data"], location=None, remote="include"
    )
    job = await jobs_repo.create_discovered_job(
        session, user.id, source="themuse", external_id="1", company="ExampleCo",
        title="TPM", location=None, url="https://example.com/1", jd_text="x" * 60,
        posted_at=None, identity_hash="h", repost_of=None, search_id=search.id,
    )
    await session.commit()
    assert job.search_id == search.id
    await repo.delete_search(session, user.id, search.id)
    await session.commit()
    session.expire_all()
    refreshed = await session.get(Job, job.id)
    assert refreshed is not None and refreshed.search_id is None
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/db/test_searches_repo.py`. Expected: `ImportError: cannot import name 'SourceCredentialRow' from 'rhapto.db.models'`.

- [ ] **Step 3: Write minimal implementation** —

`apps/api/alembic/versions/0006_searches.py`:

```python
"""saved searches, source credentials, discovered boards

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "searches",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("keywords", JSONB, nullable=False, server_default="[]"),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("remote", sa.String(length=10), nullable=False, server_default="include"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("derived_from_track_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "source_credentials",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("credentials_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "source", name="uq_source_credentials_user_source"),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "search_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("searches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "poll_runs",
        sa.Column(
            "search_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("searches.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "watchlist",
        sa.Column("discovered", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("watchlist", "discovered")
    op.drop_column("poll_runs", "search_id")
    op.drop_column("jobs", "search_id")
    op.drop_table("source_credentials")
    op.drop_table("searches")
```

`db/models.py` — append the two rows and add the columns:

```python
REMOTE_VALUES = ("include", "only", "exclude")


class SearchRow(UserScopedMixin, TimestampMixin, Base):
    """One saved search: what to ask every enabled aggregator for, on the normal schedule."""

    __tablename__ = "searches"
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    keywords: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    location: Mapped[str | None] = mapped_column(String(200))
    remote: Mapped[str] = mapped_column(
        String(10), default="include", server_default="include", nullable=False
    )
    active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    #: The track this search was derived from, until the user edits its criteria.
    derived_from_track_id: Mapped[str | None] = mapped_column(String(100))


class SourceCredentialRow(UserScopedMixin, TimestampMixin, Base):
    """The user's key(s) for one keyed aggregator, Fernet-encrypted as one JSON object."""

    __tablename__ = "source_credentials"
    __table_args__ = (UniqueConstraint("user_id", "source"),)
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    credentials_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
```

On `Job`: `search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("searches.id", ondelete="SET NULL"))`. On `WatchlistEntry`: `discovered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)`. On `PollRun`: `search_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("searches.id", ondelete="SET NULL"))`.

`db/repositories/searches.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import SearchRow

#: Editing any of these makes the search the user's own, not the track's.
CRITERIA_FIELDS = ("keywords", "location", "remote")


async def list_searches(session: AsyncSession, user_id: uuid.UUID) -> list[SearchRow]:
    return list(
        await session.scalars(
            select(SearchRow).where(SearchRow.user_id == user_id).order_by(SearchRow.created_at)
        )
    )


async def get_search(
    session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID
) -> SearchRow | None:
    result: SearchRow | None = await session.scalar(
        select(SearchRow).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
    )
    return result


async def create_search(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    keywords: list[str],
    location: str | None,
    remote: str,
    active: bool = True,
    derived_from_track_id: str | None = None,
) -> SearchRow:
    row = SearchRow(
        user_id=user_id,
        name=name,
        keywords=list(keywords),
        location=location,
        remote=remote,
        active=active,
        derived_from_track_id=derived_from_track_id,
    )
    session.add(row)
    await session.flush()
    return row


async def update_search(session: AsyncSession, row: SearchRow, **fields: Any) -> SearchRow:
    """Apply the given fields. Touching the criteria unlinks the search from its track."""
    for key, value in fields.items():
        if value is None and key in ("name", "remote", "active"):
            continue
        setattr(row, key, list(value) if key == "keywords" else value)
        if key in CRITERIA_FIELDS:
            row.derived_from_track_id = None
    row.updated_at = datetime.now(UTC)
    await session.flush()
    return row


async def delete_search(
    session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID
) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(SearchRow).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
        ),
    )
    return bool(result.rowcount)
```

`db/repositories/source_credentials.py` — note the `Fernet` parameter: `db` may not import `config` or `services`, so the caller supplies the cipher.

```python
"""Encrypted per-source credentials.

The `Fernet` is a parameter, not an import: `db` is forbidden from importing `config` and
`services` (see .importlinter), so the API and worker pass `services.secrets.fernet_for(settings)`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, cast

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import CursorResult, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import SourceCredentialRow


async def get_credentials(
    session: AsyncSession, fernet: Fernet, user_id: uuid.UUID, source: str
) -> dict[str, str]:
    """The stored values, or `{}` when there is no row or it cannot be read.

    An unreadable row means the deployment's secret changed; returning `{}` makes the source
    report "check the API key", which is the action the user can actually take.
    """
    row = await session.scalar(
        select(SourceCredentialRow).where(
            SourceCredentialRow.user_id == user_id, SourceCredentialRow.source == source
        )
    )
    if row is None:
        return {}
    try:
        data = json.loads(fernet.decrypt(row.credentials_encrypted.encode()).decode())
    except (InvalidToken, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


async def put_credentials(
    session: AsyncSession,
    fernet: Fernet,
    user_id: uuid.UUID,
    source: str,
    values: dict[str, str],
) -> None:
    """Merge `values` into the stored object: an omitted field keeps what is already there."""
    merged = {**await get_credentials(session, fernet, user_id, source), **values}
    merged = {k: v for k, v in merged.items() if v}
    token = fernet.encrypt(json.dumps(merged, sort_keys=True).encode()).decode()
    row = await session.scalar(
        select(SourceCredentialRow).where(
            SourceCredentialRow.user_id == user_id, SourceCredentialRow.source == source
        )
    )
    if row is None:
        session.add(
            SourceCredentialRow(user_id=user_id, source=source, credentials_encrypted=token)
        )
    else:
        row.credentials_encrypted = token
    await session.flush()


async def delete_credentials(
    session: AsyncSession, user_id: uuid.UUID, source: str
) -> bool:
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            delete(SourceCredentialRow).where(
                SourceCredentialRow.user_id == user_id, SourceCredentialRow.source == source
            )
        ),
    )
    return bool(result.rowcount)


async def credentialled_sources(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """Which sources have a stored row at all (what the Settings UI shows as "key set")."""
    return set(
        await session.scalars(
            select(SourceCredentialRow.source).where(SourceCredentialRow.user_id == user_id)
        )
    )
```

`jobs_repo.create_discovered_job` gains `search_id: uuid.UUID | None = None` and passes it to `Job(...)`.

`packages/schemas/profile/watchlist.json`: the `AggregatorEntry.source` enum becomes `["remoteok", "hn-hiring", "themuse", "remotive", "adzuna", "jooble", "jsearch"]`, and `WatchlistEntry` gains `"discovered": { "type": "boolean", "default": false }`.

Then, from the repo root: `bash scripts/codegen.sh`; from `apps/api`: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/db/test_searches_repo.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(db): searches, source credentials, discovered boards

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 3: Poller — searches × aggregators, board auto-discovery, derivation

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/boards.py`, `apps/api/tests/unit/test_discovery_boards_autodiscover.py`
- Modify: `apps/api/src/rhapto/services/discovery/search.py` (append `derive_searches`), `apps/api/src/rhapto/services/discovery/poller.py` (`SourceSpec` lines 33–39, `build_specs` lines 58–83, `_ingest` lines 105–145, `poll_sources` lines 148–205), `apps/api/tests/unit/test_poller.py` (extend)
- Test: as above

**Interfaces:**

Consumes: `SearchSpec`, `get_aggregator`, `SEARCH_CAP` (Task 1); `searches` repo, `source_credentials.get_credentials(session, fernet, user_id, source)`, `Job.search_id`, `WatchlistEntry.discovered`, `PollRun.search_id` (Task 2).

Produces:
- `boards.py`: `def board_from_url(url: str) -> tuple[str, str] | None`.
- `search.py`: `async def derive_searches(session, user_id) -> list[SearchRow]`.
- `poller.py`: `SourceSpec(source, board, company, keywords=[], entry_updated_at=None, search=None, search_id=None, credentials=<dict>)`; `RunResult(source, board, found, new, error, search_id=None, unlisted=0)`; `poll_sources(session, user_id, *, http, embedder, specs=None, on_step=None, fernet=None)`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/unit/test_discovery_boards_autodiscover.py`:

```python
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.models.profile.tracks import Track
from rhapto.services.discovery.boards import board_from_url
from rhapto.services.discovery.search import derive_searches


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://boards.greenhouse.io/exampleco/jobs/1", ("greenhouse", "exampleco")),
        ("https://JOB-BOARDS.greenhouse.io/Example-Co/jobs/9", ("greenhouse", "Example-Co")),
        ("https://jobs.lever.co/exampleco/abc-123?utm=x", ("lever", "exampleco")),
        ("https://jobs.ashbyhq.com/example.co/xyz", ("ashby", "example.co")),
        ("https://acme.myworkdayjobs.com/en-US/External/job/1", ("workday", "acme/External")),
        ("https://acme.myworkdayjobs.com/wday/cxs/acme/External/jobs", ("workday", "acme/External")),
    ],
)
def test_board_from_url_matches_every_pattern(url: str, expected: tuple[str, str]) -> None:
    assert board_from_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "https://www.linkedin.com/jobs/view/1",
        "https://boards.greenhouse.io/",
        "https://evil.myworkdayjobs.com.attacker.net/en-US/External/job/1",
        "not a url",
        "https://jobs.lever.co/",
    ],
)
def test_board_from_url_rejects_non_boards(url: str) -> None:
    assert board_from_url(url) is None


async def test_derive_searches_is_idempotent(session: AsyncSession, user: User) -> None:
    await profile_repo.upsert_track(
        session,
        user.id,
        Track(
            id="tpm", name="TPM", resume_base="b", min_fit=60,
            keywords=["program manager", "roadmap", "delivery", "stakeholders", "risk", "okrs", "ignored"],
        ),
    )
    await profile_repo.set_answers(
        session,
        user.id,
        {"location_home": "Denver, CO", "location_preferred": "Boulder, CO", "remote_ok": "yes"},
    )
    await session.flush()
    created = await derive_searches(session, user.id)
    assert [c.name for c in created] == ["TPM"]
    assert created[0].keywords == [
        "program manager", "roadmap", "delivery", "stakeholders", "risk", "okrs"
    ]
    assert created[0].location == "Boulder, CO"
    assert created[0].remote == "include"
    assert created[0].derived_from_track_id == "tpm"
    assert await derive_searches(session, user.id) == []
    assert len(await searches_repo.list_searches(session, user.id)) == 1
```

and append to `apps/api/tests/unit/test_poller.py`:

```python
from cryptography.fernet import Fernet

from rhapto.db.models import WatchlistEntry
from rhapto.db.repositories import searches as searches_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceInfo


class FakeAggregator:
    """Registered under a throwaway id so a poll can be driven without any HTTP at all."""

    info = SourceInfo("fake-agg", "aggregator", "Fake", False)
    seen: list[SearchSpec] = []
    postings: list[Posting] = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        type(self).seen.append(spec)
        return list(type(self).postings)


class KeyedAggregator(FakeAggregator):
    info = SourceInfo("fake-keyed", "aggregator", "Fake keyed", False, needs_key=True, fields=("api_key",))


@pytest.fixture
def fake_aggregators() -> Iterator[None]:
    FakeAggregator.seen = []
    FakeAggregator.postings = []
    SOURCES["fake-agg"] = FakeAggregator  # type: ignore[assignment]
    SOURCES["fake-keyed"] = KeyedAggregator  # type: ignore[assignment]
    yield
    SOURCES.pop("fake-agg", None)
    SOURCES.pop("fake-keyed", None)


async def test_every_active_search_runs_against_every_enabled_aggregator(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    await searches_repo.create_search(
        session, user.id, name="A", keywords=["alpha"], location="Denver, CO", remote="include"
    )
    await searches_repo.create_search(
        session, user.id, name="B", keywords=["beta"], location=None, remote="only"
    )
    await profile_repo.replace_aggregators(
        session,
        user.id,
        [
            AggregatorEntry(source="fake-agg", enabled=True, keywords=[]),
            AggregatorEntry(source="fake-keyed", enabled=True, keywords=[]),
        ],
    )
    await session.flush()
    summary = await poll_sources(
        session,
        user.id,
        http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384),
        fernet=Fernet(Fernet.generate_key()),
    )
    assert [(s.name, s.keywords[0]) for s in FakeAggregator.seen] == [("A", "alpha"), ("B", "beta")]
    skipped = [r for r in summary.results if r.source == "fake-keyed"]
    assert len(skipped) == 2 and all(r.error == "no API key" for r in skipped)


async def test_a_result_on_a_lever_board_joins_the_watchlist_once(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["alpha"], location=None, remote="include"
    )
    await profile_repo.replace_aggregators(
        session, user.id, [AggregatorEntry(source="fake-agg", enabled=True, keywords=[])]
    )
    FakeAggregator.postings = [
        Posting(
            external_id="1", company="ExampleCo", title="Alpha Engineer", location="Denver, CO",
            url="https://jobs.lever.co/exampleco/abc", jd_text="alpha " * 20,
        )
    ]
    await session.flush()
    fernet = Fernet(Fernet.generate_key())
    await poll_sources(
        session, user.id, http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384), fernet=fernet,
    )
    rows = list(await session.scalars(select(WatchlistEntry).where(WatchlistEntry.user_id == user.id)))
    assert [(r.source, r.board, r.discovered) for r in rows] == [("lever", "exampleco", True)]
    jobs = list(await session.scalars(select(Job).where(Job.user_id == user.id)))
    assert [j.search_id for j in jobs] == [search.id]
    await poll_sources(
        session, user.id, http=FakeDiscoveryHttp({}),
        embedder=FakeEmbeddingProvider(dimensions=384), fernet=fernet,
    )
    rows = list(await session.scalars(select(WatchlistEntry).where(WatchlistEntry.user_id == user.id)))
    assert len(rows) == 1
```

(add `from collections.abc import Iterator` and `from rhapto.db.models import Job` to the file's imports if not already present).

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_discovery_boards_autodiscover.py tests/unit/test_poller.py`. Expected: `ModuleNotFoundError: No module named 'rhapto.services.discovery.boards'`.

- [ ] **Step 3: Write minimal implementation** —

`services/discovery/boards.py`:

```python
"""Recognising an ATS board from a job URL, so a result can add its company to the watchlist."""

from __future__ import annotations

import re
from urllib.parse import urlparse

SLUG = re.compile(r"^[A-Za-z0-9._-]+$")
WORKDAY_HOST = ".myworkdayjobs.com"

_GREENHOUSE_HOSTS = ("boards.greenhouse.io", "job-boards.greenhouse.io")


def board_from_url(url: str) -> tuple[str, str] | None:
    """`(source, board)` for a recognised ATS posting URL, else None.

    Hosts are compared in full and lower-cased, so `evil.myworkdayjobs.com.attacker.net` is not a
    Workday tenant; slugs must be a single path segment of `[A-Za-z0-9._-]`.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    segments = [s for s in parsed.path.split("/") if s]
    if not host:
        return None
    if host in _GREENHOUSE_HOSTS and segments and SLUG.match(segments[0]):
        return ("greenhouse", segments[0])
    if host == "jobs.lever.co" and segments and SLUG.match(segments[0]):
        return ("lever", segments[0])
    if host == "jobs.ashbyhq.com" and segments and SLUG.match(segments[0]):
        return ("ashby", segments[0])
    if host.endswith(WORKDAY_HOST):
        prefix = host[: -len(WORKDAY_HOST)]
        if not prefix or not SLUG.match(prefix):
            return None
        # /wday/cxs/<tenant>/<site>/... is the JSON API; /<lang>/<site>/... is the human page.
        if len(segments) >= 4 and segments[0] == "wday" and segments[1] == "cxs":
            tenant, site = segments[2], segments[3]
        elif len(segments) >= 2:
            tenant, site = prefix, segments[1]
        else:
            return None
        if SLUG.match(tenant) and SLUG.match(site):
            return ("workday", f"{tenant}/{site}")
    return None
```

`services/discovery/search.py` — append:

```python
async def derive_searches(session: AsyncSession, user_id: uuid.UUID) -> list[SearchRow]:
    """One saved search per track, created only when the user has none at all.

    Returns the rows it created, so an empty list means "the user already has searches" and the
    caller should leave them alone.
    """
    if await searches_repo.list_searches(session, user_id):
        return []
    answers = await profile_repo.get_answers(session, user_id)
    preferred = [p.strip() for p in (answers.get("location_preferred") or "").split(",") if p.strip()]
    # The preferred list is "Town, ST, Town, ST"; the first town and its state are the first two
    # entries, and a single entry with no state is used as-is.
    location = ", ".join(preferred[:2]) if preferred else (answers.get("location_home") or None)
    remote: Remote = "exclude" if (answers.get("remote_ok") or "").strip().lower() in _FALSEY else "include"
    created: list[SearchRow] = []
    for track in await profile_repo.list_tracks(session, user_id):
        created.append(
            await searches_repo.create_search(
                session,
                user_id,
                name=track.name[:100],
                keywords=list(track.keywords)[:6],
                location=location,
                remote=remote,
                derived_from_track_id=track.track_id,
            )
        )
    return created
```

with the module's imports extended by `import uuid`, `from sqlalchemy.ext.asyncio import AsyncSession`, `from rhapto.db.models import SearchRow`, `from rhapto.db.repositories import profile as profile_repo`, `from rhapto.db.repositories import searches as searches_repo`, and `_FALSEY = frozenset({"no", "false", "0", "never"})`.

`services/discovery/poller.py`:

```python
@dataclass
class SourceSpec:
    source: str
    board: str | None
    company: str | None
    keywords: list[str] = field(default_factory=list)
    entry_updated_at: datetime | None = None
    #: Set for aggregator specs driven by a saved search; None for board specs.
    search: SearchSpec | None = None
    search_id: uuid.UUID | None = None
    credentials: dict[str, str] = field(default_factory=dict)


@dataclass
class RunResult:
    source: str
    board: str | None
    found: int
    new: int
    error: str | None
    search_id: uuid.UUID | None = None
    unlisted: int = 0
```

`build_specs` gains a `fernet` parameter and the saved-search fan-out:

```python
async def build_specs(
    session: AsyncSession, user_id: uuid.UUID, *, fernet: Fernet | None = None
) -> list[SourceSpec]:
    specs = [
        SourceSpec(
            source=row.source,
            board=row.board,
            company=row.company,
            keywords=list(row.keywords),
            entry_updated_at=row.updated_at,
        )
        for row in await profile_repo.list_watchlist(session, user_id)
    ]
    track_keywords: list[str] = []
    for track in await profile_repo.list_tracks(session, user_id):
        track_keywords.extend(k for k in track.keywords if k not in track_keywords)
    enabled = [a for a in await profile_repo.list_aggregators(session, user_id) if a.enabled]
    if not enabled:
        return specs
    # A user who has never opened the Searches tab still gets the market: derive on first poll.
    await derive_searches(session, user_id)
    searches = [s for s in await searches_repo.list_searches(session, user_id) if s.active]
    for search in searches:
        for agg in enabled:
            info = SOURCES[agg.source].info if agg.source in SOURCES else None
            credentials: dict[str, str] = {}
            if info is not None and info.needs_key:
                credentials = (
                    await creds_repo.get_credentials(session, fernet, user_id, agg.source)
                    if fernet is not None
                    else {}
                )
            specs.append(
                SourceSpec(
                    source=agg.source,
                    board=None,
                    company=None,
                    keywords=list(search.keywords),
                    entry_updated_at=agg.updated_at,
                    search=SearchSpec(
                        keywords=tuple(search.keywords),
                        location=search.location,
                        remote=cast("Remote", search.remote),
                        name=search.name,
                    ),
                    search_id=search.id,
                    credentials=credentials,
                )
            )
    if not searches:
        # Legacy path: no tracks and no searches, so fall back to the aggregator row's own
        # keywords exactly as before saved searches existed.
        for agg in enabled:
            specs.append(
                SourceSpec(
                    source=agg.source,
                    board=None,
                    company=None,
                    keywords=list(agg.keywords) or track_keywords,
                    entry_updated_at=agg.updated_at,
                )
            )
    return specs
```

`_ingest` sets `search_id` and `salary_text` (the latter lands with Task 9's column; until then pass nothing) and returns the created rows:

```python
        job = await jobs_repo.create_discovered_job(
            session,
            user_id,
            source=spec.source,
            external_id=posting.external_id,
            company=company,
            title=posting.title,
            location=posting.location,
            url=posting.url,
            jd_text=posting.jd_text,
            posted_at=posting.posted_at,
            identity_hash=ident,
            repost_of=repost_source.id if repost_source else None,
            search_id=spec.search_id,
        )
```

After `_ingest`, inside `poll_sources`' success branch, add auto-discovery:

```python
async def _discover_boards(
    session: AsyncSession, user_id: uuid.UUID, spec: SourceSpec, created: list[Job]
) -> None:
    """Add a watchlist row for every ATS board a new job's URL points at."""
    existing = {
        (row.source, row.board) for row in await profile_repo.list_watchlist(session, user_id)
    }
    for job in created:
        match = board_from_url(job.url or "")
        if match is None or match in existing:
            continue
        existing.add(match)
        session.add(
            WatchlistEntry(
                user_id=user_id,
                company=job.company or match[1],
                source=match[0],
                board=match[1],
                keywords=list(spec.keywords),
                discovered=True,
            )
        )
    await session.flush()
```

and in the fetch call, branch on the spec:

```python
            if spec.search is not None:
                postings = await get_aggregator(spec.source).fetch_search(
                    cast("DiscoveryHttp", http), spec.search, spec.credentials
                )
            else:
                postings = await get_source(spec.source).fetch(
                    cast("DiscoveryHttp", http), board=spec.board, keywords=spec.keywords
                )
```

Before the fetch, skip keyed sources with no credentials:

```python
        info = SOURCES[spec.source].info if spec.source in SOURCES else None
        if spec.search is not None and info is not None and info.needs_key and not spec.credentials:
            run = await disc_repo.start_run(session, user_id, spec.source, spec.board)
            run.search_id = spec.search_id
            disc_repo.finish_run(run, found=0, new=0, error="no API key")
            await session.commit()
            results.append(RunResult(spec.source, spec.board, 0, 0, "no API key", spec.search_id))
            continue
```

Every `start_run` in this function sets `run.search_id = spec.search_id`, and every `RunResult` carries `spec.search_id`. `poll_sources` gains `fernet: Fernet | None = None` and passes it to `build_specs`. The worker's `poll_now`/`poll_all_sources` pass `fernet=fernet_for(get_settings())` guarded by `try/except SecretsError` (a deployment with no secret still polls its keyless sources).

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_discovery_boards_autodiscover.py tests/unit/test_poller.py tests/unit/test_worker_discovery.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(discovery): saved searches drive aggregators; boards discovered from results

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 4: API — saved searches CRUD, source settings, search name on jobs

**Files:**
- Create: `apps/api/src/rhapto/api/routers/searches.py`, `apps/api/tests/api/test_searches_api.py`, `apps/api/tests/api/test_source_settings_api.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (append `SearchIn/SearchOut/SourceSettingOut/SourceSettingIn/SourceTestOut`; `JobOut` lines 117–136), `apps/api/src/rhapto/api/routers/settings.py` (append the sources endpoints), `apps/api/src/rhapto/api/app.py` (line 13 imports, line 93 mounts), `apps/api/src/rhapto/api/routers/jobs.py` (`job_to_out` lines 34–81, `_out`/`_outs` lines 93–119), `apps/api/src/rhapto/db/repositories/jobs.py` (`list_jobs`), `packages/schemas/openapi.json` + `apps/web/src/lib/api/schema.d.ts` via codegen
- Test: as above

**Interfaces:**

Consumes: `searches` repo and `source_credentials` repo (Task 2); `aggregator_sources()`, `get_aggregator`, `SourceInfo.needs_key/fields`, `SearchSpec` (Task 1).

Produces:
- `SearchIn(name: str, keywords: list[str], location: str | None, remote, active: bool)`, `SearchOut(id, name, keywords, location, remote, active, derived_from_track_id, created_at)`.
- `SourceSettingOut(id, label, needs_key, fields: list[str], enabled, key_set)`, `SourceSettingIn(enabled: bool, credentials: dict[str,str] | None)`, `SourceTestOut(ok, found: int | None, error: str | None)`.
- `JobOut.search_name: str | None`.
- Routes: `GET/POST /searches`, `PUT/DELETE /searches/{id}`, `POST /searches/derive`, `GET /settings/sources`, `PUT /settings/sources/{source}`, `POST /settings/sources/{source}/test`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/api/test_searches_api.py`:

```python
from __future__ import annotations

import httpx


async def test_search_crud(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/searches",
        json={"name": "Data", "keywords": ["data platform"], "location": "Denver, CO", "remote": "include"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["keywords"] == ["data platform"] and body["active"] is True
    listed = await client.get("/api/v1/searches")
    assert [s["id"] for s in listed.json()] == [body["id"]]
    updated = await client.put(
        f"/api/v1/searches/{body['id']}",
        json={"name": "Data", "keywords": ["ETL"], "location": None, "remote": "only", "active": False},
    )
    assert updated.status_code == 200 and updated.json()["remote"] == "only"
    assert (await client.delete(f"/api/v1/searches/{body['id']}")).status_code == 204
    assert (await client.delete(f"/api/v1/searches/{body['id']}")).status_code == 404


async def test_empty_keywords_are_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/v1/searches", json={"name": "x", "keywords": []})
    assert response.status_code == 422


async def test_derive_creates_one_search_per_track_then_nothing(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    first = await client.post("/api/v1/searches/derive")
    assert first.status_code == 200 and len(first.json()) >= 1
    assert (await client.post("/api/v1/searches/derive")).json() == []


async def test_an_unknown_search_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.get(f"/api/v1/searches")).status_code == 200
    assert (await client.put(f"/api/v1/searches/{missing}", json={"name": "x", "keywords": ["y"]})).status_code == 404
```

and `apps/api/tests/api/test_source_settings_api.py`:

```python
from __future__ import annotations

import httpx
import pytest

from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo


class ProbeSource:
    info = SourceInfo("fake-probe", "aggregator", "Fake probe", False)
    result: list[Posting] | Exception = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        if isinstance(type(self).result, Exception):
            raise type(self).result
        return list(type(self).result)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def probe_source():  # type: ignore[no-untyped-def]
    SOURCES["fake-probe"] = ProbeSource  # type: ignore[assignment]
    yield
    SOURCES.pop("fake-probe", None)
    ProbeSource.result = []


async def test_sources_list_reports_key_requirements(client: httpx.AsyncClient) -> None:
    rows = (await client.get("/api/v1/settings/sources")).json()
    by_id = {r["id"]: r for r in rows}
    assert by_id["themuse"]["needs_key"] is False and by_id["themuse"]["enabled"] is True
    assert by_id["adzuna"]["needs_key"] is True and by_id["adzuna"]["fields"] == ["app_id", "app_key"]
    assert by_id["adzuna"]["enabled"] is False and by_id["adzuna"]["key_set"] is False


async def test_enabling_a_keyed_source_without_keys_is_422(client: httpx.AsyncClient) -> None:
    response = await client.put("/api/v1/settings/sources/adzuna", json={"enabled": True})
    assert response.status_code == 422 and "app_id" in response.text


async def test_keys_are_stored_and_never_echoed(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/v1/settings/sources/adzuna",
        json={"enabled": True, "credentials": {"app_id": "id-1", "app_key": "s3cret"}},
    )
    assert response.status_code == 200
    assert "s3cret" not in response.text
    assert response.json()["key_set"] is True and response.json()["enabled"] is True


async def test_test_endpoint_reports_both_outcomes(client: httpx.AsyncClient) -> None:
    ProbeSource.result = [
        Posting(external_id="1", company="C", title="T", url="https://e.com/1", jd_text="x" * 60)
    ]
    ok = await client.post("/api/v1/settings/sources/fake-probe/test")
    assert ok.json() == {"ok": True, "found": 1, "error": None}
    ProbeSource.result = SourceError("Fake probe: check the API key")
    bad = await client.post("/api/v1/settings/sources/fake-probe/test")
    assert bad.status_code == 200 and bad.json()["ok"] is False
    assert "check the API key" in bad.json()["error"]
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_searches_api.py tests/api/test_source_settings_api.py`. Expected: `assert 404 == 201` on the first POST (the router is not mounted).

- [ ] **Step 3: Write minimal implementation** —

`api/schemas.py` — append:

```python
RemoteValue = Literal["include", "only", "exclude"]


class SearchIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    keywords: list[str] = Field(min_length=1, max_length=10)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    active: bool = True

    @field_validator("keywords")
    @classmethod
    def _non_empty(cls, value: list[str]) -> list[str]:
        cleaned = [k.strip() for k in value if k.strip()]
        if not cleaned or any(len(k) > 60 for k in cleaned):
            raise ValueError("each keyword must be 1-60 characters")
        return cleaned


class SearchOut(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    location: str | None
    remote: RemoteValue
    active: bool
    derived_from_track_id: str | None
    created_at: datetime


class SourceSettingOut(BaseModel):
    id: str
    label: str
    needs_key: bool
    fields: list[str]
    enabled: bool
    key_set: bool


class SourceSettingIn(BaseModel):
    enabled: bool
    #: Omitted fields keep whatever is stored; the values never come back out.
    credentials: dict[str, str] | None = None


class SourceTestOut(BaseModel):
    ok: bool
    found: int | None = None
    error: str | None = None
```

`JobOut` gains `search_name: str | None = None` and `salary_text: str | None = None` (the latter stays None until Task 9 adds the column; declare both now so the generated TypeScript settles once).

`db/repositories/jobs.py` — `list_jobs` left-joins `SearchRow` and returns pairs:

```python
async def list_jobs(...) -> list[tuple[Job, str | None]]:
    ...
    query = (
        select(Job, SearchRow.name)
        .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
        .outerjoin(SearchRow, SearchRow.id == Job.search_id)
        .where(Job.user_id == user_id)
    )
    ...
    return [(job, name) for job, name in (await session.execute(query)).all()]


async def search_name_for(
    session: AsyncSession, user_id: uuid.UUID, search_id: uuid.UUID | None
) -> str | None:
    if search_id is None:
        return None
    return await session.scalar(
        select(SearchRow.name).where(SearchRow.user_id == user_id, SearchRow.id == search_id)
    )
```

`api/routers/jobs.py` — `job_to_out` takes `search_name: str | None`, sets `search_name=search_name`; `_out` calls `repo.search_name_for(session, user_id, job.search_id)`; `_outs` iterates the `(job, name)` pairs.

`api/routers/searches.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.errors import not_found
from rhapto.api.schemas import SearchIn, SearchOut
from rhapto.db.models import SearchRow
from rhapto.db.repositories import searches as repo
from rhapto.services.discovery.search import derive_searches

router = APIRouter(prefix="/searches")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def search_to_out(row: SearchRow) -> SearchOut:
    return SearchOut(
        id=row.id,
        name=row.name,
        keywords=list(row.keywords),
        location=row.location,
        remote=row.remote,  # type: ignore[arg-type]
        active=row.active,
        derived_from_track_id=row.derived_from_track_id,
        created_at=row.created_at,
    )


@router.get("", response_model=list[SearchOut])
async def list_searches(user_id: UserDep, session: SessionDep) -> list[SearchOut]:
    return [search_to_out(r) for r in await repo.list_searches(session, user_id)]


@router.post("", response_model=SearchOut, status_code=201)
async def create_search(body: SearchIn, user_id: UserDep, session: SessionDep) -> SearchOut:
    row = await repo.create_search(
        session,
        user_id,
        name=body.name,
        keywords=body.keywords,
        location=body.location,
        remote=body.remote,
        active=body.active,
    )
    await session.commit()
    return search_to_out(row)


@router.post("/derive", response_model=list[SearchOut])
async def derive(user_id: UserDep, session: SessionDep) -> list[SearchOut]:
    created = await derive_searches(session, user_id)
    await session.commit()
    return [search_to_out(r) for r in created]


@router.put("/{search_id}", response_model=SearchOut)
async def update_search(
    search_id: uuid.UUID, body: SearchIn, user_id: UserDep, session: SessionDep
) -> SearchOut:
    row = await repo.get_search(session, user_id, search_id)
    if row is None:
        raise not_found("search", search_id)
    await repo.update_search(
        session,
        row,
        name=body.name,
        keywords=body.keywords,
        location=body.location,
        remote=body.remote,
        active=body.active,
    )
    await session.commit()
    return search_to_out(row)


@router.delete("/{search_id}", status_code=204)
async def delete_search(
    search_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> Response:
    if not await repo.delete_search(session, user_id, search_id):
        raise not_found("search", search_id)
    await session.commit()
    return Response(status_code=204)
```

`api/routers/settings.py` — append:

```python
KEYLESS_DEFAULT_ENABLED = True


async def _source_rows(session: AsyncSession, user_id: uuid.UUID) -> dict[str, Aggregator]:
    return {row.source: row for row in await profile_repo.list_aggregators(session, user_id)}


@router.get("/settings/sources", response_model=list[SourceSettingOut])
async def list_source_settings(
    user_id: UserDep, session: SessionDep
) -> list[SourceSettingOut]:
    rows = await _source_rows(session, user_id)
    stored = await creds_repo.credentialled_sources(session, user_id)
    out: list[SourceSettingOut] = []
    for info in aggregator_sources():
        row = rows.get(info.name)
        enabled = row.enabled if row is not None else (KEYLESS_DEFAULT_ENABLED and not info.needs_key)
        out.append(
            SourceSettingOut(
                id=info.name,
                label=info.label,
                needs_key=info.needs_key,
                fields=list(info.fields),
                enabled=enabled,
                key_set=info.name in stored,
            )
        )
    return out


@router.put("/settings/sources/{source}", response_model=SourceSettingOut)
async def put_source_setting(
    source: str, body: SourceSettingIn, user_id: UserDep, session: SessionDep, settings: SettingsDep
) -> SourceSettingOut:
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    fernet = fernet_for(settings)
    if body.credentials:
        await creds_repo.put_credentials(session, fernet, user_id, source, body.credentials)
    if body.enabled and info.needs_key:
        stored = await creds_repo.get_credentials(session, fernet, user_id, source)
        missing = [f for f in info.fields if not stored.get(f)]
        if missing:
            # Enabling a source we cannot call would show up later as a failed poll run with no
            # explanation; say which field is missing while the user is looking at the form.
            raise HTTPException(
                status_code=422, detail=f"{info.label} needs {', '.join(missing)}"
            )
    rows = await _source_rows(session, user_id)
    row = rows.get(source)
    if row is None:
        row = Aggregator(user_id=user_id, source=source, enabled=body.enabled, keywords=[])
        session.add(row)
    else:
        row.enabled = body.enabled
    row.updated_at = datetime.now(UTC)
    await session.commit()
    stored_sources = await creds_repo.credentialled_sources(session, user_id)
    return SourceSettingOut(
        id=info.name,
        label=info.label,
        needs_key=info.needs_key,
        fields=list(info.fields),
        enabled=body.enabled,
        key_set=info.name in stored_sources,
    )


@router.post("/settings/sources/{source}/test", response_model=SourceTestOut)
async def test_source(
    source: str, user_id: UserDep, session: SessionDep, settings: SettingsDep, request: Request
) -> SourceTestOut:
    """One tiny search against the source. Never a 500: a failure is this endpoint's answer."""
    info = next((i for i in aggregator_sources() if i.name == source), None)
    if info is None:
        raise HTTPException(status_code=404, detail=f"unknown source {source!r}")
    credentials = await creds_repo.get_credentials(session, fernet_for(settings), user_id, source)
    http = get_state(request).discovery_http
    try:
        postings = await get_aggregator(source).fetch_search(
            http, SearchSpec(keywords=("program manager",)), credentials
        )
    except Exception as exc:
        return SourceTestOut(ok=False, error=redact(str(exc), *credentials.values())[:300])
    return SourceTestOut(ok=True, found=len(postings))
```

`AppState` gains `discovery_http: DiscoveryHttp` (built in `create_app` as `DiscoveryHttp(user_agent=settings.rhapto_discovery_user_agent, base_override=settings.rhapto_discovery_base_override)` and closed in the lifespan's `finally`, alongside the enqueuer and event bus); the api conftest's `app` fixture passes `discovery_http=FakeDiscoveryHttp({})` through a new `create_app(..., discovery_http=...)` keyword so no test reaches the network.

`api/app.py` mounts `searches.router` with `tags=["searches"]`.

Then from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_searches_api.py tests/api/test_source_settings_api.py tests/api/test_jobs_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): saved searches, job source settings, search name on jobs

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 5: Web — Searches tab, Job sources settings, source chips

**Superseded.** The web side of saved searches and job sources is delivered by `docs/superpowers/plans/2026-09-14-portal-ui.md` (Settings additions task) on the new information architecture. Nothing to implement here; do not commit anything for this task.

---

### Task 6: README and end-to-end smoke

**Files:** Modify `README.md`. No tests (this task's verification is the manual run in Step 3).

**Interfaces:** Consumes Tasks 1–4 (sources, storage, poller, API). Nothing here consumes Task 5, which is superseded: the walkthrough drives the API with `curl`, not the web app.

Prerequisite for Step 3: `RHAPTO_API_TOKEN` from the repo's `.env`, exported as `$TOKEN`.

- [ ] **Step 1: Write the failing test** — not applicable: this task ships prose plus a manual run. Instead, write down the expected outcome first, in `README.md`, as the section below — the run in Step 3 either matches it or the section is wrong.

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api tests/db` to confirm the branch is green before the manual run (nothing here should change it).

- [ ] **Step 3: Write minimal implementation** — add to `README.md`, after the discovery section:

```markdown
## Find jobs across the whole market

Rhapto polls two kinds of source: **company boards** on your watchlist (Greenhouse, Lever, Ashby,
Workday) and **aggregators** that search the market. Aggregators are driven by your *saved
searches*, which are derived from your tracks the first time you poll — one search per track,
using the track's first six keywords, your preferred location, and your `remote_ok` answer. Edit
them through `GET/POST/PUT/DELETE /api/v1/searches` (the Searches screen arrives with the
portal UI).

Zero-setup sources are on by default: **The Muse**, **Remotive**, **RemoteOK**, **HN Who's
Hiring**. Three more need a free key, saved with `PUT /api/v1/settings/sources/{source}`
(keys are encrypted at rest and never returned by the API):

| Source | Where the key comes from | Fields |
|---|---|---|
| Adzuna | developer.adzuna.com | `app_id`, `app_key` |
| Jooble | jooble.org/api/about | `api_key` |
| JSearch (Google Jobs) | rapidapi.com/letscrape-6bRBa3QguO5/api/jsearch | `rapidapi_key` |

When a result points at a company's own ATS board, Rhapto adds that board to your watchlist
automatically and marks it *discovered*; remove it from your watchlist if you are not
interested.

Everything then enters the usual flow: **Tailor → Review → download → apply on the employer's own
site → Mark applied.** Rhapto never submits an application for you.
```

Then rebuild and run the API side one service at a time and drive it with `curl` — the web app is
not part of this plan, so nothing here depends on a page existing:

```bash
docker compose build api && docker compose build worker && docker compose up -d db redis api worker
export TOKEN="$(grep -E '^RHAPTO_API_TOKEN=' .env | cut -d= -f2-)"
API=http://localhost:8000/api/v1
AUTH="Authorization: Bearer $TOKEN"

# 1. Every registered aggregator, with which ones need a key and which have one saved.
curl -sS -H "$AUTH" "$API/settings/sources" | python -m json.tool

# 2. Create a saved search by hand (or POST /searches/derive to get one per track).
curl -sS -X POST -H "$AUTH" -H 'Content-Type: application/json'   -d '{"name":"Platform","keywords":["technical program manager"],"location":"Denver, CO","remote":"include"}'   "$API/searches" | python -m json.tool

# 3. Poll: the existing endpoint returns a task; watch the worker log for the run rows.
curl -sS -X POST -H "$AUTH" "$API/discovery/poll" | python -m json.tool
docker compose logs --tail 40 worker
curl -sS -H "$AUTH" "$API/discovery/runs" | python -m json.tool

# 4. What arrived, newest first, with its source and the search it came from.
curl -sS -H "$AUTH" "$API/jobs?sort=newest"   | python -c 'import json,sys; [print(j["source"], "|", j["search_name"], "|", j["title"]) for j in json.load(sys.stdin)]'

# 5. The boards discovered from those results.
curl -sS -H "$AUTH" "$API/profile/watchlist" | python -m json.tool
```

Confirm: step 1 lists seven aggregators; step 3's runs include `themuse` and `remotive` with a
non-zero `found`; step 4 prints jobs carrying those source ids and `Platform` as the search name;
step 5 shows at least one entry with `"discovered": true`. Then tailor one of those job ids through
`POST /jobs/{id}/tailor` and confirm a package comes back from `GET /jobs/{id}/packages`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run ruff check src tests && uv run ruff format src tests && uv run mypy src && uv run lint-imports`, then `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py` and `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
docs: market-wide search and the apply flow

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 7: Taxonomy data file, schema, loader, codegen and image

**Files:**
- Create: `packages/schemas/taxonomy.json`, `packages/schemas/taxonomy.yaml`, `apps/api/src/rhapto/services/taxonomy.py`, `apps/api/tests/unit/test_taxonomy.py`
- Modify: `scripts/codegen.sh` (lines 6–27), `apps/api/Dockerfile` (after line 10), `apps/api/src/rhapto/services/discovery/sources/themuse.py` (`_url`), `apps/api/src/rhapto/services/discovery/sources/adzuna.py` (`fetch_search` query dict)
- Generated (never hand-edited): `apps/api/src/rhapto/models/taxonomy.py`
- Test: `apps/api/tests/unit/test_taxonomy.py`

**Interfaces:**

Consumes: `SearchSpec.field` (Task 1).

Produces:
- `models/taxonomy.py` (generated): `TaxonomyFile(fields: list[TaxonomyField])`, `TaxonomyField(id: str, name: str, themuse_category: str, adzuna_category: str, roles: list[TaxonomyRole])`, `TaxonomyRole(id: str, name: str, keywords: list[str])`.
- `services/taxonomy.py`: `class TaxonomyError(Exception)`; `def taxonomy_path() -> Path`; `def load_taxonomy(path: Path) -> TaxonomyFile`; `def taxonomy() -> TaxonomyFile` (lru_cached); `def find_field(field_id: str | None) -> TaxonomyField | None`; `def find_role(field_id: str, role_id: str) -> TaxonomyRole | None`; `def roles_by_name() -> dict[str, tuple[TaxonomyField, TaxonomyRole]]`; `def normalise(text: str) -> str`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/unit/test_taxonomy.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from rhapto.services import taxonomy as tax

SPEC_FIELDS = [
    "engineering", "data-science", "product", "program-project-management", "design",
    "marketing", "sales", "finance", "operations", "people", "customer-success", "other",
]


def test_the_shipped_file_has_the_twelve_fields_from_the_spec() -> None:
    assert [f.id for f in tax.taxonomy().fields] == SPEC_FIELDS


def test_every_role_has_between_six_and_ten_keywords() -> None:
    for field in tax.taxonomy().fields:
        assert field.roles, f"{field.id} has no roles"
        assert field.themuse_category and field.adzuna_category
        for role in field.roles:
            assert 6 <= len(role.keywords) <= 10, f"{field.id}/{role.id}: {len(role.keywords)}"


def test_role_ids_are_unique_within_a_field() -> None:
    for field in tax.taxonomy().fields:
        ids = [r.id for r in field.roles]
        assert len(ids) == len(set(ids))


def test_the_roles_named_in_the_spec_are_present() -> None:
    engineering = tax.find_field("engineering")
    assert engineering is not None
    assert {
        "Backend", "Frontend", "Full stack", "Mobile", "ML Engineering", "DevOps and SRE",
        "Security", "QA",
    } <= {r.name for r in engineering.roles}
    science = tax.find_field("data-science")
    assert science is not None
    assert {
        "Data Scientist", "Data Analyst", "Data Engineer", "Analytics Engineer", "ML Research",
    } <= {r.name for r in science.roles}
    ppm = tax.find_field("program-project-management")
    assert ppm is not None
    assert {
        "Technical Program Manager", "Program Manager", "Project Manager", "Delivery Lead",
        "Scrum Master",
    } <= {r.name for r in ppm.roles}


def test_lookups() -> None:
    assert tax.find_field(None) is None
    assert tax.find_field("nope") is None
    role = tax.find_role("engineering", "backend")
    assert role is not None and role.name == "Backend"
    assert tax.find_role("engineering", "nope") is None
    assert tax.find_role("nope", "backend") is None
    field, tpm = tax.roles_by_name()["technical program manager"]
    assert field.id == "program-project-management"
    assert tpm.id == "technical-program-manager"


def test_roles_by_name_puts_the_longest_name_first() -> None:
    names = list(tax.roles_by_name())
    assert names.index("technical program manager") < names.index("program manager")


def test_normalise_strips_punctuation_and_case() -> None:
    assert tax.normalise("  Sr. Technical  Program-Manager, II ") == "sr technical program manager ii"


def test_the_env_override_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    override = tmp_path / "taxonomy.yaml"
    override.write_text(
        "fields:\n"
        "  - id: only\n"
        "    name: Only\n"
        "    themuse_category: Engineering\n"
        "    adzuna_category: IT Jobs\n"
        "    roles:\n"
        "      - id: one\n"
        "        name: One\n"
        "        keywords: [aa, bb, cc, dd, ee, ff]\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("RHAPTO_TAXONOMY_PATH", str(override))
    tax.taxonomy.cache_clear()
    try:
        assert [f.id for f in tax.taxonomy().fields] == ["only"]
    finally:
        tax.taxonomy.cache_clear()


def test_a_broken_or_missing_file_raises_taxonomy_error(tmp_path: Path) -> None:
    bad = tmp_path / "taxonomy.yaml"
    bad.write_text("fields: [{id: x}]", encoding="utf-8")
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(bad)
    with pytest.raises(tax.TaxonomyError):
        tax.load_taxonomy(tmp_path / "missing.yaml")
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_taxonomy.py`. Expected: `ModuleNotFoundError: No module named 'rhapto.services.taxonomy'` (collection error).

- [ ] **Step 3: Write minimal implementation** —

`packages/schemas/taxonomy.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://rhapto.dev/schemas/taxonomy.json",
  "title": "TaxonomyFile",
  "description": "taxonomy.yaml: career fields, the roles inside them, the keywords a track starts from, and the category name each aggregator uses for the field.",
  "type": "object",
  "additionalProperties": false,
  "required": ["fields"],
  "properties": {
    "fields": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/TaxonomyField" } }
  },
  "$defs": {
    "TaxonomyField": {
      "title": "TaxonomyField",
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "themuse_category", "adzuna_category", "roles"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
        "name": { "type": "string" },
        "themuse_category": { "type": "string" },
        "adzuna_category": { "type": "string" },
        "roles": { "type": "array", "minItems": 1, "items": { "$ref": "#/$defs/TaxonomyRole" } }
      }
    },
    "TaxonomyRole": {
      "title": "TaxonomyRole",
      "type": "object",
      "additionalProperties": false,
      "required": ["id", "name", "keywords"],
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$" },
        "name": { "type": "string" },
        "keywords": {
          "type": "array",
          "minItems": 6,
          "maxItems": 10,
          "items": { "type": "string", "minLength": 2, "maxLength": 60 }
        }
      }
    }
  }
}
```

`packages/schemas/taxonomy.yaml`:

```yaml
# The field -> role taxonomy behind the Tracks picker (spec 2026-09-14-portal-design.md, §5).
# Picking a role creates a track named after it, with these keywords and min_fit 60.
# `themuse_category` and `adzuna_category` are the category names those two APIs use for the
# field; keyword-only sources get the track's keywords instead.
fields:
  - id: engineering
    name: Engineering
    themuse_category: Engineering
    adzuna_category: IT Jobs
    roles:
      - id: backend
        name: Backend
        keywords: [backend engineer, backend developer, API design, microservices, distributed systems, server side, databases]
      - id: frontend
        name: Frontend
        keywords: [frontend engineer, frontend developer, React, TypeScript, web UI, accessibility, design systems]
      - id: full-stack
        name: Full stack
        keywords: [full stack engineer, full stack developer, web application, REST API, React, Node, end to end]
      - id: mobile
        name: Mobile
        keywords: [mobile engineer, iOS engineer, Android engineer, Swift, Kotlin, React Native, mobile application]
      - id: ml-engineering
        name: ML Engineering
        keywords: [machine learning engineer, ML infrastructure, model serving, feature store, MLOps, PyTorch, inference]
      - id: devops-sre
        name: DevOps and SRE
        keywords: [site reliability engineer, DevOps engineer, Kubernetes, Terraform, CI CD, observability, incident response]
      - id: security
        name: Security
        keywords: [security engineer, application security, threat modeling, incident response, penetration testing, identity and access, compliance]
      - id: qa
        name: QA
        keywords: [QA engineer, test automation, quality engineering, end to end testing, regression testing, test strategy, defect triage]
  - id: data-science
    name: Data Science
    themuse_category: Data Science
    adzuna_category: Scientific & QA Jobs
    roles:
      - id: data-scientist
        name: Data Scientist
        keywords: [data scientist, statistical modeling, experimentation, A/B testing, Python, causal inference, predictive models]
      - id: data-analyst
        name: Data Analyst
        keywords: [data analyst, SQL, dashboards, business intelligence, reporting, Tableau, metrics]
      - id: data-engineer
        name: Data Engineer
        keywords: [data engineer, data pipelines, ETL, Spark, Airflow, data warehouse, streaming]
      - id: analytics-engineer
        name: Analytics Engineer
        keywords: [analytics engineer, dbt, data modeling, semantic layer, SQL, data quality, warehouse]
      - id: ml-research
        name: ML Research
        keywords: [machine learning researcher, research scientist, deep learning, publications, model architecture, benchmarks, PyTorch]
  - id: product
    name: Product
    themuse_category: Product Management
    adzuna_category: IT Jobs
    roles:
      - id: product-manager
        name: Product Manager
        keywords: [product manager, product roadmap, user research, requirements, prioritisation, stakeholder management, product strategy]
      - id: technical-product-manager
        name: Technical Product Manager
        keywords: [technical product manager, platform product, API product, developer experience, technical roadmap, architecture, integrations]
      - id: group-product-manager
        name: Group Product Manager
        keywords: [group product manager, principal product manager, product leadership, portfolio, mentoring, product strategy, org alignment]
      - id: product-operations
        name: Product Operations
        keywords: [product operations, product ops, release process, tooling, product analytics, launch readiness, cross functional]
  - id: program-project-management
    name: Program and Project Management
    themuse_category: Project Management
    adzuna_category: Consultancy Jobs
    roles:
      - id: technical-program-manager
        name: Technical Program Manager
        keywords: [technical program manager, TPM, cross functional programs, technical roadmap, dependency management, risk management, engineering delivery]
      - id: program-manager
        name: Program Manager
        keywords: [program manager, program governance, portfolio management, stakeholder management, roadmap, status reporting, OKRs]
      - id: project-manager
        name: Project Manager
        keywords: [project manager, project plan, schedule management, budget tracking, scope management, RAID log, PMP]
      - id: delivery-lead
        name: Delivery Lead
        keywords: [delivery lead, delivery manager, release management, agile delivery, throughput, team health, escalation]
      - id: scrum-master
        name: Scrum Master
        keywords: [scrum master, agile coach, sprint planning, retrospectives, backlog refinement, velocity, impediment removal]
  - id: design
    name: Design
    themuse_category: Design and UX
    adzuna_category: Creative & Design Jobs
    roles:
      - id: product-designer
        name: Product Designer
        keywords: [product designer, UX design, interaction design, wireframes, prototyping, Figma, design systems]
      - id: ux-researcher
        name: UX Researcher
        keywords: [UX researcher, user research, usability testing, interviews, research synthesis, personas, qualitative research]
      - id: ux-writer
        name: UX Writer
        keywords: [UX writer, content design, microcopy, content strategy, voice and tone, information architecture, localisation]
      - id: brand-designer
        name: Brand Designer
        keywords: [brand designer, visual design, identity system, typography, marketing design, illustration, art direction]
  - id: marketing
    name: Marketing
    themuse_category: Marketing
    adzuna_category: PR, Advertising & Marketing Jobs
    roles:
      - id: product-marketing-manager
        name: Product Marketing Manager
        keywords: [product marketing manager, positioning, messaging, go to market, launch, competitive analysis, sales enablement]
      - id: growth-marketing
        name: Growth Marketing
        keywords: [growth marketing, performance marketing, paid acquisition, conversion rate, funnel, lifecycle marketing, experimentation]
      - id: content-marketing
        name: Content Marketing
        keywords: [content marketing, editorial calendar, SEO, blog, thought leadership, copywriting, content strategy]
      - id: demand-generation
        name: Demand Generation
        keywords: [demand generation, pipeline generation, campaign management, marketing automation, Marketo, lead scoring, ABM]
  - id: sales
    name: Sales
    themuse_category: Sales
    adzuna_category: Sales Jobs
    roles:
      - id: account-executive
        name: Account Executive
        keywords: [account executive, quota, pipeline, enterprise sales, closing, negotiation, Salesforce]
      - id: sales-development
        name: Sales Development
        keywords: [sales development representative, SDR, outbound prospecting, lead qualification, cold outreach, cadences, discovery calls]
      - id: solutions-engineer
        name: Solutions Engineer
        keywords: [solutions engineer, sales engineer, technical demo, proof of concept, RFP, pre sales, solution design]
      - id: sales-manager
        name: Sales Manager
        keywords: [sales manager, team quota, forecasting, coaching, territory planning, pipeline review, sales process]
  - id: finance
    name: Finance
    themuse_category: Accounting and Finance
    adzuna_category: Accounting & Finance Jobs
    roles:
      - id: financial-analyst
        name: Financial Analyst
        keywords: [financial analyst, financial modeling, variance analysis, forecasting, budgeting, Excel, reporting]
      - id: fp-and-a
        name: FP and A
        keywords: [FP&A, financial planning and analysis, annual plan, headcount planning, scenario modeling, board reporting, KPIs]
      - id: accountant
        name: Accountant
        keywords: [accountant, general ledger, month end close, reconciliations, GAAP, accounts payable, audit support]
      - id: controller
        name: Controller
        keywords: [controller, financial controls, close process, technical accounting, audit, SOX, policy]
  - id: operations
    name: Operations
    themuse_category: Business Operations
    adzuna_category: Logistics & Warehouse Jobs
    roles:
      - id: business-operations
        name: Business Operations
        keywords: [business operations, process improvement, operating cadence, analytics, cross functional, planning, efficiency]
      - id: supply-chain
        name: Supply Chain
        keywords: [supply chain, logistics, inventory management, procurement, demand planning, vendor management, fulfilment]
      - id: technical-operations
        name: Technical Operations
        keywords: [technical operations, service operations, runbooks, capacity planning, vendor management, uptime, escalation]
      - id: strategy-operations
        name: Strategy and Operations
        keywords: [strategy and operations, strategic planning, market analysis, business case, executive reporting, OKRs, special projects]
  - id: people
    name: People
    themuse_category: HR
    adzuna_category: HR & Recruitment Jobs
    roles:
      - id: recruiter
        name: Recruiter
        keywords: [recruiter, technical recruiting, sourcing, candidate pipeline, interview process, offer negotiation, applicant tracking]
      - id: people-partner
        name: People Partner
        keywords: [people partner, HR business partner, employee relations, performance management, coaching, organisational design, retention]
      - id: people-operations
        name: People Operations
        keywords: [people operations, HR operations, onboarding, HRIS, benefits administration, compliance, policy]
      - id: learning-and-development
        name: Learning and Development
        keywords: [learning and development, training programs, enablement, curriculum design, facilitation, career development, coaching]
  - id: customer-success
    name: Customer Success
    themuse_category: Customer Service
    adzuna_category: Customer Services Jobs
    roles:
      - id: customer-success-manager
        name: Customer Success Manager
        keywords: [customer success manager, renewals, retention, onboarding, QBR, adoption, account health]
      - id: solutions-architect
        name: Solutions Architect
        keywords: [solutions architect, technical account manager, integration design, reference architecture, customer workshops, implementation, escalation]
      - id: support-engineer
        name: Support Engineer
        keywords: [support engineer, technical support, troubleshooting, ticket queue, SLA, root cause analysis, knowledge base]
      - id: implementation-manager
        name: Implementation Manager
        keywords: [implementation manager, onboarding projects, deployment, configuration, migration, go live, customer training]
  - id: other
    name: Other
    themuse_category: Other
    adzuna_category: Other/General Jobs
    roles:
      - id: generalist
        name: Generalist
        keywords: [generalist, cross functional, operations, analysis, project delivery, stakeholder management, communication]
```

`scripts/codegen.sh` — replace lines 6–27 (the `rm -rf`, the `rm -f openapi.json` and the `datamodel-codegen` invocation) with a scan of a temp copy, because `datamodel-codegen` rglobs every file under `--input`:

```bash
rm -rf "$OUT"
# datamodel-codegen rglobs every file under --input, so it is pointed at a COPY of
# packages/schemas with the two non-schema files removed: openapi.json (an OpenAPI document,
# regenerated below by export_openapi.py) and taxonomy.yaml (data validated *by* taxonomy.json).
SCAN="$(mktemp -d)"
trap 'rm -rf "$SCAN"' EXIT
cp -R "$ROOT/packages/schemas/." "$SCAN/"
rm -f "$SCAN/openapi.json" "$SCAN/taxonomy.yaml"
(cd "$ROOT/apps/api" && uv run datamodel-codegen \
  --input "$SCAN" \
  --input-file-type jsonschema \
  --output "$OUT" \
  --output-model-type pydantic_v2.BaseModel \
  --use-title-as-name \
  --strict-nullable \
  --use-annotated \
  --field-constraints \
  --enum-field-as-literal all \
  --use-standard-collections \
  --use-union-operator \
  --collapse-root-models \
  --use-schema-description \
  --use-field-description \
  --target-python-version 3.12 \
  --disable-timestamp)
```

`apps/api/Dockerfile` — after `COPY apps/api/alembic ./alembic`:

```dockerfile
# The taxonomy is data the API serves, not source: it lives in packages/schemas (not on the
# runtime path), so it is copied to the fixed location services/taxonomy.py looks for.
COPY packages/schemas/taxonomy.yaml /app/schemas/taxonomy.yaml
```

`apps/api/src/rhapto/services/taxonomy.py`:

```python
"""The field -> role taxonomy the Tracks picker and the Field filter are built from.

The data lives in `packages/schemas/taxonomy.yaml`, is validated by `packages/schemas/taxonomy.json`
and is read through the generated `models.taxonomy.TaxonomyFile`. `packages/` is not on the runtime
path, so the Docker image copies the file to `/app/schemas/taxonomy.yaml`; `RHAPTO_TAXONOMY_PATH`
overrides both, for tests and for anyone who wants their own list.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import ValidationError

from rhapto.models.taxonomy import TaxonomyField, TaxonomyFile, TaxonomyRole

#: Where the Docker image puts the file (see apps/api/Dockerfile).
IMAGE_PATH = Path("/app/schemas/taxonomy.yaml")
#: Where it lives in a source checkout: .../apps/api/src/rhapto/services/ -> repo root.
REPO_PATH = Path(__file__).resolve().parents[5] / "packages" / "schemas" / "taxonomy.yaml"

_PUNCT = re.compile(r"[^a-z0-9]+")


class TaxonomyError(Exception):
    """The taxonomy file is missing, unreadable, or does not match its schema."""


def taxonomy_path() -> Path:
    """The file this deployment reads: the env override, then the image, then the checkout."""
    override = os.environ.get("RHAPTO_TAXONOMY_PATH", "").strip()
    if override:
        return Path(override)
    return IMAGE_PATH if IMAGE_PATH.exists() else REPO_PATH


def load_taxonomy(path: Path) -> TaxonomyFile:
    """Parse and validate one taxonomy file. Every failure is a TaxonomyError naming the path."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TaxonomyError(f"cannot read the taxonomy at {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise TaxonomyError(f"{path} is not valid YAML: {exc}") from exc
    try:
        return TaxonomyFile.model_validate(raw)
    except ValidationError as exc:
        raise TaxonomyError(f"{path} does not match taxonomy.json: {exc}") from exc


@lru_cache(maxsize=1)
def taxonomy() -> TaxonomyFile:
    """The loaded taxonomy. Cached: the file cannot change while the process runs."""
    return load_taxonomy(taxonomy_path())


def find_field(field_id: str | None) -> TaxonomyField | None:
    if not field_id:
        return None
    return next((f for f in taxonomy().fields if f.id == field_id), None)


def find_role(field_id: str, role_id: str) -> TaxonomyRole | None:
    field = find_field(field_id)
    if field is None:
        return None
    return next((r for r in field.roles if r.id == role_id), None)


def roles_by_name() -> dict[str, tuple[TaxonomyField, TaxonomyRole]]:
    """Every role keyed by its normalised name, longest name first.

    The order matters to callers that match resume titles: "senior technical program manager"
    contains both "technical program manager" and "program manager", and the longer, more
    specific name is the right answer.
    """
    pairs = [
        (normalise(role.name), (field, role))
        for field in taxonomy().fields
        for role in field.roles
    ]
    pairs.sort(key=lambda pair: len(pair[0]), reverse=True)
    return dict(pairs)


def normalise(text: str) -> str:
    """Lower-cased, punctuation-free, single-spaced: the form both sides of a match use."""
    return _PUNCT.sub(" ", text.lower()).strip()
```

Wire the two category-aware sources. In `themuse.py`, `_url` becomes:

```python
    def _url(self, spec: SearchSpec, page: int) -> str:
        url = f"https://www.themuse.com/api/public/jobs?page={page}"
        if spec.location:
            url += f"&location={quote(spec.location, safe='')}"
        field = find_field(spec.field)
        if field is not None:
            url += f"&category={quote(field.themuse_category, safe='')}"
        return url
```

and in `adzuna.py`, inside the per-page loop right after `query` is built:

```python
                field = find_field(spec.field)
                if field is not None:
                    query["category"] = field.adzuna_category
```

both files importing `from rhapto.services.taxonomy import find_field`.

Finally, from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_taxonomy.py tests/unit/test_discovery_search_sources.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`. Then confirm the image carries the data file: `docker compose build api` and `docker compose run --rm api sh -c 'ls -l /app/schemas/taxonomy.yaml'`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(taxonomy): twelve career fields, their roles and curated keywords

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 8: Tracks gain field and role; GET /taxonomy and /taxonomy/suggestions

**Files:**
- Create: `apps/api/alembic/versions/0007_track_taxonomy.py`, `apps/api/src/rhapto/api/routers/taxonomy.py`, `apps/api/tests/api/test_taxonomy_api.py`
- Modify: `packages/schemas/profile/tracks.json` (`Track.properties`), `apps/api/src/rhapto/db/models.py` (`Track`, lines 69–80), `apps/api/src/rhapto/db/repositories/profile.py` (`upsert_track`, lines 164–196), `apps/api/src/rhapto/services/profile_sync.py` (`track_row_to_model`), `apps/api/src/rhapto/api/schemas.py` (append `TaxonomySuggestionOut`), `apps/api/src/rhapto/api/app.py` (line 13 imports, line 93 mounts)
- Generated (never hand-edited): `apps/api/src/rhapto/models/profile/tracks.py`, `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_taxonomy_api.py`

**Interfaces:**

Consumes: `taxonomy()`, `find_field`, `roles_by_name`, `normalise` (Task 7); `documents_repo.get_document(session, user_id)` and `SourceDocument` with `DocParagraph.role == "entry_title"` (existing).

Produces:
- `Track.field: str | None`, `Track.role: str | None` on the row, the generated Pydantic model, and the profile API round trip.
- `TaxonomySuggestionOut(field_id: str, field_name: str, role_id: str, role_name: str, matched_title: str)`.
- Routes: `GET /taxonomy` → `TaxonomyFile`; `GET /taxonomy/suggestions` → `list[TaxonomySuggestionOut]`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/api/test_taxonomy_api.py`:

```python
from __future__ import annotations

import uuid

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import documents as documents_repo


async def test_get_taxonomy_returns_the_twelve_fields(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/taxonomy")).json()
    assert [f["id"] for f in body["fields"]][:3] == ["engineering", "data-science", "product"]
    ppm = next(f for f in body["fields"] if f["id"] == "program-project-management")
    assert ppm["themuse_category"] == "Project Management"
    assert ppm["adzuna_category"] == "Consultancy Jobs"
    tpm = next(r for r in ppm["roles"] if r["id"] == "technical-program-manager")
    assert 6 <= len(tpm["keywords"]) <= 10


async def test_suggestions_are_empty_without_an_uploaded_resume(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/v1/taxonomy/suggestions")).json() == []


async def test_suggestions_match_the_parsed_entry_titles(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    parsed = {
        "filename": "resume.docx",
        "sections": [],
        "paragraphs": [
            {"id": "p1", "text": "Maya Chen", "role": "name"},
            {"id": "p2", "text": "Senior Technical Program Manager, Platform", "role": "entry_title"},
            {"id": "p3", "text": "Delivered three programs", "role": "bullet"},
            {"id": "p4", "text": "Data Analyst", "role": "entry_title"},
            {"id": "p5", "text": "Technical Program Manager II", "role": "entry_title"},
            {"id": "p6", "text": "Barista", "role": "entry_title"},
        ],
    }
    async with session_factory() as session:
        await documents_repo.upsert_document(
            session, user_id, filename="resume.docx", path="/tmp/resume.docx", parsed=parsed
        )
        await session.commit()
    body = (await client.get("/api/v1/taxonomy/suggestions")).json()
    # One entry per role, in document order; the second TPM title adds nothing and Barista
    # matches no role at all.
    assert [(s["role_id"], s["matched_title"]) for s in body] == [
        ("technical-program-manager", "Senior Technical Program Manager, Platform"),
        ("data-analyst", "Data Analyst"),
    ]
    assert body[0]["field_id"] == "program-project-management"
    assert body[0]["field_name"] == "Program and Project Management"
    assert body[0]["role_name"] == "Technical Program Manager"


async def test_a_track_round_trips_its_field_and_role(client: httpx.AsyncClient) -> None:
    created = await client.put(
        "/api/v1/profile/tracks/tpm",
        json={
            "id": "tpm",
            "name": "Technical Program Manager",
            "resume_base": "default",
            "min_fit": 60,
            "keywords": ["technical program manager", "TPM"],
            "field": "program-project-management",
            "role": "technical-program-manager",
        },
    )
    assert created.status_code == 201
    row = next(t for t in (await client.get("/api/v1/profile/tracks")).json() if t["id"] == "tpm")
    assert row["field"] == "program-project-management"
    assert row["role"] == "technical-program-manager"


async def test_a_track_without_a_field_still_round_trips(client: httpx.AsyncClient) -> None:
    created = await client.put(
        "/api/v1/profile/tracks/manual",
        json={"id": "manual", "name": "Manual", "resume_base": "default", "keywords": ["x"]},
    )
    assert created.status_code == 201
    assert created.json()["field"] is None and created.json()["role"] is None
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_taxonomy_api.py`. Expected: `assert 404 == 200` on `GET /api/v1/taxonomy` (the router is not mounted).

- [ ] **Step 3: Write minimal implementation** —

`apps/api/alembic/versions/0007_track_taxonomy.py`:

```python
"""tracks remember which taxonomy field and role created them

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tracks", sa.Column("field", sa.String(length=50), nullable=True))
    op.add_column("tracks", sa.Column("role", sa.String(length=50), nullable=True))


def downgrade() -> None:
    op.drop_column("tracks", "role")
    op.drop_column("tracks", "field")
```

`db/models.py` — on `Track`, after `min_fit`:

```python
    # Where this track came from in packages/schemas/taxonomy.yaml. NULL on tracks written by
    # hand or imported from a tracks.yaml that predates the picker, which is why the Field
    # filter treats NULL as "not in any field" rather than guessing.
    field: Mapped[str | None] = mapped_column(String(50))
    role: Mapped[str | None] = mapped_column(String(50))
```

`packages/schemas/profile/tracks.json` — inside `Track.properties`, after `min_fit`:

```json
        "field": { "type": ["string", "null"], "default": null },
        "role": { "type": ["string", "null"], "default": null }
```

`db/repositories/profile.py` — in `upsert_track`, alongside `row.min_fit = data.min_fit`:

```python
    row.field = data.field
    row.role = data.role
```

`services/profile_sync.py` — `track_row_to_model` builds the model with `field=row.field, role=row.role`.

`api/schemas.py` — append:

```python
class TaxonomySuggestionOut(BaseModel):
    """One role the uploaded resume's entry titles point at, for the picker's chip row."""

    field_id: str
    field_name: str
    role_id: str
    role_name: str
    matched_title: str
```

`apps/api/src/rhapto/api/routers/taxonomy.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.schemas import TaxonomySuggestionOut
from rhapto.db.repositories import documents as documents_repo
from rhapto.models.source_document import SourceDocument
from rhapto.models.taxonomy import TaxonomyFile
from rhapto.services.taxonomy import normalise, roles_by_name, taxonomy

router = APIRouter(prefix="/taxonomy")

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

#: The picker shows these as one-tap chips above the field list; more than a handful is noise.
MAX_SUGGESTIONS = 6


@router.get("", response_model=TaxonomyFile)
async def get_taxonomy(user_id: UserDep) -> TaxonomyFile:
    """The whole field -> role tree. Static data, but behind auth like every other route."""
    return taxonomy()


@router.get("/suggestions", response_model=list[TaxonomySuggestionOut])
async def suggestions(user_id: UserDep, session: SessionDep) -> list[TaxonomySuggestionOut]:
    """Roles whose name appears in one of the uploaded resume's entry titles.

    Matching is deliberately blunt -- normalised containment in either direction -- because entry
    titles carry seniority and team ("Senior Technical Program Manager, Platform"). Anything
    cleverer would need the LLM, and this has to answer while the picker is opening.
    """
    row = await documents_repo.get_document(session, user_id)
    if row is None:
        return []
    document = SourceDocument.model_validate(row.parsed_json)
    lookup = roles_by_name()  # longest role name first, so the specific match wins
    out: list[TaxonomySuggestionOut] = []
    seen: set[tuple[str, str]] = set()
    for paragraph in document.paragraphs:
        if paragraph.role != "entry_title":
            continue
        title = normalise(paragraph.text)
        if not title:
            continue
        for role_name, (field, role) in lookup.items():
            if role_name not in title and title not in role_name:
                continue
            key = (field.id, role.id)
            if key not in seen:
                seen.add(key)
                out.append(
                    TaxonomySuggestionOut(
                        field_id=field.id,
                        field_name=field.name,
                        role_id=role.id,
                        role_name=role.name,
                        matched_title=paragraph.text,
                    )
                )
            break  # one role per title
        if len(out) >= MAX_SUGGESTIONS:
            break
    return out
```

`api/app.py` — import `taxonomy` alongside the other routers and mount it: `app.include_router(taxonomy.router, prefix=API_PREFIX, tags=["taxonomy"])`.

Then from the repo root: `bash scripts/codegen.sh`; from `apps/api`: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_taxonomy_api.py tests/api/test_profile_api.py tests/db/test_profile_sync.py tests/unit/test_profile_loader.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): serve the taxonomy and suggest roles from the uploaded resume

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 9: Flow fields migration and models

**Files:**
- Create: `apps/api/alembic/versions/0008_flow_fields.py`, `apps/api/tests/db/test_flow_fields.py`
- Modify: `apps/api/src/rhapto/db/models.py` (`Job` lines 146–171, `Package` lines 174–206, `Application` lines 209–223, `SearchRow`, plus the `CLOSED_REASONS` constant near line 27), `apps/api/src/rhapto/db/repositories/jobs.py` (`create_discovered_job`, lines 134–166), `apps/api/src/rhapto/services/discovery/poller.py` (`_ingest`)
- Test: `apps/api/tests/db/test_flow_fields.py`

**Interfaces:**

Consumes: `SearchRow` (Task 2), `Posting.salary_text` (Task 1).

Produces: `CLOSED_REASONS = ("rejected", "withdrew", "no_response", "filled")`; `Job.hidden_at`, `Job.unlisted_at`, `Job.salary_text`, `Job.miss_count`; `Package.archived_at`; `Application.closed_reason`, `Application.follow_up_at`; `SearchRow.last_viewed_at`; `jobs_repo.create_discovered_job(..., salary_text: str | None = None)`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/db/test_flow_fields.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Application, Package, User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo


async def _job(session: AsyncSession, user: User, external_id: str, **kwargs: object):  # type: ignore[no-untyped-def]
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source="themuse",
        external_id=external_id,
        company="ExampleCo",
        title="Technical Program Manager",
        location=None,
        url=f"https://example.com/{external_id}",
        jd_text="x" * 60,
        posted_at=None,
        identity_hash=f"hash-{external_id}",
        repost_of=None,
        **kwargs,  # type: ignore[arg-type]
    )
    await session.flush()
    return job


async def test_flow_columns_start_empty(session: AsyncSession, user: User) -> None:
    job = await _job(session, user, "1", salary_text="$150,000 - $170,000")
    assert job.hidden_at is None
    assert job.unlisted_at is None
    assert job.miss_count == 0
    assert job.salary_text == "$150,000 - $170,000"
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["a"], location=None, remote="include"
    )
    assert search.last_viewed_at is None


async def test_a_closed_reason_requires_the_closed_status(
    session: AsyncSession, user: User
) -> None:
    job = await _job(session, user, "2")
    good = Application(
        user_id=user.id, job_id=job.id, status="closed", closed_reason="rejected",
        notes="", status_history_json=[],
    )
    session.add(good)
    await session.flush()
    assert good.closed_reason == "rejected"
    bad = Application(
        user_id=user.id, job_id=job.id, status="screen", closed_reason="filled",
        notes="", status_history_json=[],
    )
    session.add(bad)
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_follow_up_and_archived_are_plain_timestamps(
    session: AsyncSession, user: User
) -> None:
    job = await _job(session, user, "3")
    when = datetime.now(UTC)
    application = Application(
        user_id=user.id, job_id=job.id, status="applied", follow_up_at=when,
        notes="", status_history_json=[],
    )
    package = Package(
        user_id=user.id, job_id=job.id, track_id="t", version=1, status="draft",
        resume_json={}, cover_note="", change_log="", guardrail_report_json={},
        jd_extract_json={}, archived_at=when,
    )
    session.add_all([application, package])
    await session.flush()
    assert application.follow_up_at == when
    assert package.archived_at == when
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/db/test_flow_fields.py`. Expected: `TypeError: create_discovered_job() got an unexpected keyword argument 'salary_text'`.

- [ ] **Step 3: Write minimal implementation** —

`apps/api/alembic/versions/0008_flow_fields.py`:

```python
"""flow state: hidden, unlisted, archived, closed reasons, follow-ups, salary, last viewed

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLOSED_REASON_CHECK = "closed_reason IS NULL OR status = 'closed'"


def upgrade() -> None:
    op.add_column("jobs", sa.Column("hidden_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("unlisted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("salary_text", sa.String(length=200), nullable=True))
    op.add_column(
        "jobs", sa.Column("miss_count", sa.SmallInteger(), nullable=False, server_default="0")
    )
    op.add_column("packages", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("applications", sa.Column("closed_reason", sa.String(length=20), nullable=True))
    op.add_column(
        "applications", sa.Column("follow_up_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_applications_closed_reason", "applications", CLOSED_REASON_CHECK
    )
    op.add_column(
        "searches", sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("searches", "last_viewed_at")
    op.drop_constraint("ck_applications_closed_reason", "applications", type_="check")
    op.drop_column("applications", "follow_up_at")
    op.drop_column("applications", "closed_reason")
    op.drop_column("packages", "archived_at")
    op.drop_column("jobs", "miss_count")
    op.drop_column("jobs", "salary_text")
    op.drop_column("jobs", "unlisted_at")
    op.drop_column("jobs", "hidden_at")
```

`db/models.py` — add beside the other status tuples:

```python
CLOSED_REASONS = ("rejected", "withdrew", "no_response", "filled")
```

extend the SQLAlchemy imports with `CheckConstraint` and `SmallInteger`, and add the columns.

On `Job`:

```python
    # "Not interested": the job leaves the grid's default view, recommendations and the Resumes
    # queue. The row stays, so a later repost can still point at it.
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set once the source stopped returning this posting on UNLISTED_AFTER consecutive polls.
    unlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Whatever the source said about pay, verbatim; NULL when it said nothing. Never computed.
    salary_text: Mapped[str | None] = mapped_column(String(200))
    # Consecutive polls of this job's own source and scope that did not return its external id.
    # A smallint because it never exceeds UNLISTED_AFTER before the row is marked and reset.
    miss_count: Mapped[int] = mapped_column(
        SmallInteger, default=0, server_default="0", nullable=False
    )
```

On `Package`:

```python
    # "Skip": the draft leaves the Resumes queue. Kept, not deleted, so the change log survives.
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

On `Application` — add the table args and two columns:

```python
    __table_args__ = (
        # A reason only means something on a closed application; the router clears it when a
        # closed application is reopened, and this makes the invariant the database's.
        CheckConstraint(
            "closed_reason IS NULL OR status = 'closed'", name="ck_applications_closed_reason"
        ),
    )
    ...
    closed_reason: Mapped[str | None] = mapped_column(String(20))
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

On `SearchRow`:

```python
    # When the user last opened this search's results; "N new" counts jobs discovered after it.
    last_viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

`db/repositories/jobs.py` — `create_discovered_job` gains `salary_text: str | None = None` and passes `salary_text=salary_text` to `Job(...)`.

`services/discovery/poller.py` — `_ingest` passes `salary_text=posting.salary_text` to `create_discovered_job`.

Then from `apps/api`: `uv run alembic upgrade head`, `uv run alembic downgrade -1`, `uv run alembic upgrade head`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/db/test_flow_fields.py tests/db/test_models.py tests/unit/test_poller.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(db): flow state columns for hidden, unlisted, archived and closed

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 10: Flow endpoints — hide, unhide, archive, closed reason, follow-up

**Files:**
- Create: `apps/api/tests/api/test_flow_api.py`
- Modify: `apps/api/src/rhapto/api/routers/jobs.py` (`job_to_out` lines 34–81, append hide/unhide), `apps/api/src/rhapto/api/routers/packages.py` (`list_all_packages` lines 104–127, append archive), `apps/api/src/rhapto/api/routers/applications.py` (`application_to_out` lines 31–42, `patch_application` lines 106–122), `apps/api/src/rhapto/api/schemas.py` (`JobOut`, `PackageListItem` lines 196–207, `ApplicationPatch` lines 226–235, `ApplicationOut` lines 244–253), `apps/api/src/rhapto/db/repositories/jobs.py` (append `set_hidden`), `apps/api/src/rhapto/db/repositories/packages.py` (`list_packages` lines 81–111, append `set_archived`), `apps/api/tests/api/conftest.py` (append the `tailored_package` fixture)
- Generated (never hand-edited): `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_flow_api.py`

**Interfaces:**

Consumes: `CLOSED_REASONS`, `Job.hidden_at`, `Job.unlisted_at`, `Job.salary_text`, `Package.archived_at`, `Application.closed_reason`, `Application.follow_up_at` (Task 9).

Produces:
- `jobs_repo.set_hidden(job: Job, hidden: bool) -> None`.
- `packages_repo.set_archived(package: Package, archived: bool) -> None`; `packages_repo.list_packages(session, user_id, *, status=None, applied=None, archived: bool = False)`.
- Routes: `POST /jobs/{job_id}/hide` and `POST /jobs/{job_id}/unhide` → `JobOut`; `POST /packages/{package_id}/archive` → `PackageOut`; `GET /packages?archived=`; `PATCH /applications/{id}` accepting `closed_reason` and `follow_up_at`.
- `JobOut.hidden_at`, `JobOut.unlisted_at`; `PackageListItem.archived_at`; `ApplicationOut.closed_reason`, `ApplicationOut.follow_up_at`.

- [ ] **Step 1: Write the failing test** — first append a fixture to `apps/api/tests/api/conftest.py`:

```python
@pytest.fixture
async def tailored_package(
    client: httpx.AsyncClient, imported_profile: None, fake_llm: ScriptableLLM
) -> dict[str, Any]:
    """One job tailored end to end with the fake provider, for tests about what happens next.

    The inline enqueuer runs the worker task in-process, so the package exists by the time the
    tailor call returns.
    """
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "jd_text": "Technical program manager for the data platform team. " * 6,
                "company": "ExampleCo",
                "title": "Technical Program Manager",
            },
        )
    ).json()
    fake_llm.script(*default_tailor_script())
    response = await client.post(f"/api/v1/jobs/{job['id']}/tailor", json={})
    assert response.status_code in (200, 202), response.text
    packages = (await client.get(f"/api/v1/jobs/{job['id']}/packages")).json()
    assert packages, "the inline enqueuer should have produced a package"
    return dict(packages[-1])
```

`default_tailor_script()` is the LLM response sequence the existing tailor tests already build; lift it verbatim out of `tests/api/test_tailor_api.py` into `tests/helpers.py` as a module-level function and import it in both places (no behaviour change).

Then create `apps/api/tests/api/test_flow_api.py`:

```python
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


async def _job(client: httpx.AsyncClient, marker: str) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/jobs",
        json={
            "jd_text": f"We need a technical program manager for {marker}. " * 4,
            "company": "ExampleCo",
            "title": "Technical Program Manager",
        },
    )
    assert response.status_code == 201, response.text
    return dict(response.json())


async def test_hide_and_unhide_a_job(client: httpx.AsyncClient) -> None:
    job = await _job(client, "alpha")
    hidden = await client.post(f"/api/v1/jobs/{job['id']}/hide")
    assert hidden.status_code == 200 and hidden.json()["hidden_at"] is not None
    assert (await client.get("/api/v1/jobs")).json() == []
    assert [j["id"] for j in (await client.get("/api/v1/jobs?hidden=true")).json()] == [job["id"]]
    # Hiding twice is the same state, not an error: the Undo toast can fire late.
    again = await client.post(f"/api/v1/jobs/{job['id']}/hide")
    assert again.status_code == 200 and again.json()["hidden_at"] == hidden.json()["hidden_at"]
    back = await client.post(f"/api/v1/jobs/{job['id']}/unhide")
    assert back.json()["hidden_at"] is None
    assert [j["id"] for j in (await client.get("/api/v1/jobs")).json()] == [job["id"]]


async def test_hide_on_an_unknown_job_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/jobs/{missing}/hide")).status_code == 404
    assert (await client.post(f"/api/v1/jobs/{missing}/unhide")).status_code == 404


async def test_archiving_a_package_hides_its_job_and_empties_the_queue(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    package_id, job_id = tailored_package["id"], tailored_package["job_id"]
    assert [p["id"] for p in (await client.get("/api/v1/packages")).json()] == [package_id]
    archived = await client.post(f"/api/v1/packages/{package_id}/archive")
    assert archived.status_code == 200
    assert (await client.get("/api/v1/packages")).json() == []
    listed = (await client.get("/api/v1/packages?archived=true")).json()
    assert [p["id"] for p in listed] == [package_id]
    assert listed[0]["archived_at"] is not None
    assert (await client.get(f"/api/v1/jobs/{job_id}")).json()["hidden_at"] is not None


async def test_archiving_an_unknown_package_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/packages/{missing}/archive")).status_code == 404


async def test_closing_an_application_with_a_reason(client: httpx.AsyncClient) -> None:
    job = await _job(client, "beta")
    application_id = (
        await client.post("/api/v1/applications", json={"job_id": job["id"]})
    ).json()["id"]
    closed = await client.patch(
        f"/api/v1/applications/{application_id}",
        json={"status": "closed", "closed_reason": "no_response"},
    )
    assert closed.status_code == 200 and closed.json()["closed_reason"] == "no_response"
    bad = await client.patch(
        f"/api/v1/applications/{application_id}", json={"closed_reason": "ghosted"}
    )
    assert bad.status_code == 422
    # Reopening clears the reason rather than leaving a contradiction behind.
    reopened = await client.patch(
        f"/api/v1/applications/{application_id}", json={"status": "screen"}
    )
    assert reopened.json()["closed_reason"] is None


async def test_a_reason_without_the_closed_status_is_422(client: httpx.AsyncClient) -> None:
    job = await _job(client, "gamma")
    application_id = (
        await client.post("/api/v1/applications", json={"job_id": job["id"]})
    ).json()["id"]
    response = await client.patch(
        f"/api/v1/applications/{application_id}",
        json={"status": "screen", "closed_reason": "filled"},
    )
    assert response.status_code == 422


async def test_a_follow_up_date_can_be_set_and_cleared(client: httpx.AsyncClient) -> None:
    job = await _job(client, "delta")
    application_id = (
        await client.post("/api/v1/applications", json={"job_id": job["id"]})
    ).json()["id"]
    when = (datetime.now(UTC) + timedelta(days=3)).isoformat()
    set_date = await client.patch(
        f"/api/v1/applications/{application_id}", json={"follow_up_at": when}
    )
    assert set_date.json()["follow_up_at"] is not None
    # An omitted field is untouched; an explicit null clears it.
    untouched = await client.patch(
        f"/api/v1/applications/{application_id}", json={"notes": "called them"}
    )
    assert untouched.json()["follow_up_at"] is not None
    cleared = await client.patch(
        f"/api/v1/applications/{application_id}", json={"follow_up_at": None}
    )
    assert cleared.json()["follow_up_at"] is None
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_flow_api.py`. Expected: `assert 405 == 200` on `POST /api/v1/jobs/{id}/hide` (the route does not exist).

- [ ] **Step 3: Write minimal implementation** —

`db/repositories/jobs.py` — append:

```python
def set_hidden(job: Job, hidden: bool) -> None:
    """Idempotent: hiding an already-hidden job keeps its original timestamp."""
    if hidden:
        job.hidden_at = job.hidden_at or datetime.now(UTC)
    else:
        job.hidden_at = None
```

`db/repositories/packages.py` — append and extend:

```python
def set_archived(package: Package, archived: bool) -> None:
    if archived:
        package.archived_at = package.archived_at or datetime.now(UTC)
    else:
        package.archived_at = None


async def list_packages(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    applied: bool | None = None,
    archived: bool = False,
) -> list[tuple[Package, Job, Application | None]]:
    """Latest package per job, newest first, with its job and application (if any).

    `archived=False` is the Resumes queue: it drops archived packages and packages whose job the
    user hid or a source stopped listing, because none of those have a next step any more.
    `archived=True` is the archive view and shows only archived packages.
    """
    latest = (
        select(Package.job_id, func.max(Package.version).label("version"))
        .where(Package.user_id == user_id)
        .group_by(Package.job_id)
        .subquery()
    )
    query = (
        select(Package, Job, Application)
        .join(latest, and_(Package.job_id == latest.c.job_id, Package.version == latest.c.version))
        .join(Job, Job.id == Package.job_id)
        .outerjoin(Application, Application.job_id == Package.job_id)
        .where(Package.user_id == user_id)
        .order_by(Package.created_at.desc(), Package.id)
    )
    if archived:
        query = query.where(Package.archived_at.is_not(None))
    else:
        query = query.where(
            Package.archived_at.is_(None), Job.hidden_at.is_(None), Job.unlisted_at.is_(None)
        )
    if status:
        query = query.where(Package.status == status)
    if applied is True:
        query = query.where(Application.status.in_(APPLIED_STATUSES))
    elif applied is False:
        query = query.where(
            or_(Application.id.is_(None), Application.status.in_(NOT_APPLIED_STATUSES))
        )
    return [(p, j, a) for p, j, a in (await session.execute(query)).all()]
```

with `from datetime import UTC, datetime` added to the module's imports.

`api/schemas.py` — `JobOut` gains `hidden_at: datetime | None = None` and `unlisted_at: datetime | None = None` (`salary_text` and `search_name` were declared in Task 4); `PackageListItem` gains `archived_at: datetime | None = None`; `ApplicationOut` gains `closed_reason: str | None = None` and `follow_up_at: datetime | None = None`; and `ApplicationPatch` becomes:

```python
class ApplicationPatch(BaseModel):
    """A partial update. An omitted field is left alone; an explicit null clears it, which is
    why the router reads `model_dump(exclude_unset=True)` rather than testing for None."""

    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    notes: str | None = None
    closed_reason: str | None = None
    follow_up_at: datetime | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, value: str | None) -> str | None:
        if value is not None and value not in APPLICATION_STATUSES:
            raise ValueError(f"status must be one of {', '.join(APPLICATION_STATUSES)}")
        return value

    @field_validator("closed_reason")
    @classmethod
    def _known_reason(cls, value: str | None) -> str | None:
        if value is not None and value not in CLOSED_REASONS:
            raise ValueError(f"closed_reason must be one of {', '.join(CLOSED_REASONS)}")
        return value
```

with `ConfigDict` imported from pydantic and `CLOSED_REASONS` from `rhapto.db.models`.

`api/routers/jobs.py` — `job_to_out` gains `hidden_at=job.hidden_at, unlisted_at=job.unlisted_at, salary_text=job.salary_text`; append the two routes:

```python
@router.post("/{job_id}/hide", response_model=JobOut)
async def hide_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    """"Not interested": the job leaves the grid, recommendations and the Resumes queue."""
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    repo.set_hidden(job, True)
    await session.commit()
    return await _out(session, user_id, job)


@router.post("/{job_id}/unhide", response_model=JobOut)
async def unhide_job(job_id: uuid.UUID, user_id: UserDep, session: SessionDep) -> JobOut:
    """Undo, from the toast or the "Show hidden" view."""
    job = await repo.get_job(session, user_id, job_id)
    if job is None:
        raise not_found("job", job_id)
    repo.set_hidden(job, False)
    await session.commit()
    return await _out(session, user_id, job)
```

`api/routers/packages.py` — `list_all_packages` gains `archived: bool = Query(default=False)`, passes it to `repo.list_packages`, and adds `archived_at=p.archived_at` to each `PackageListItem`; append:

```python
@router.post("/packages/{package_id}/archive", response_model=PackageOut)
async def archive_package(
    package_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> PackageOut:
    """"Skip": the draft leaves the review queue and its job leaves the Jobs grid together.

    Archiving only the package would leave the job in recommendations, where Tailor would offer
    to write the very draft the user just skipped.
    """
    row = await _get_package(session, user_id, package_id)
    repo.set_archived(row, True)
    job = await job_repo.get_job(session, user_id, row.job_id)
    if job is None:
        raise not_found("job", row.job_id)
    job_repo.set_hidden(job, True)
    await session.commit()
    await session.refresh(row)
    return package_to_out(row)
```

`api/routers/applications.py` — `application_to_out` returns `closed_reason=row.closed_reason, follow_up_at=row.follow_up_at`, and `patch_application` becomes:

```python
@router.patch("/{application_id}", response_model=ApplicationOut)
async def patch_application(
    application_id: uuid.UUID,
    body: ApplicationPatch,
    user_id: UserDep,
    session: SessionDep,
) -> ApplicationOut:
    row = await repo.get_application(session, user_id, application_id)
    if row is None:
        raise not_found("application", application_id)
    sent = body.model_dump(exclude_unset=True)
    if body.status is not None:
        repo.set_status(row, body.status)
        if body.status != "closed":
            # A reopened application cannot keep "rejected" on it; the DB check constraint would
            # refuse the row anyway, and a 500 is the wrong way to say "that makes no sense".
            row.closed_reason = None
    if body.notes is not None:
        row.notes = body.notes
    if "closed_reason" in sent:
        if body.closed_reason is not None and row.status != "closed":
            raise HTTPException(
                status_code=422, detail="closed_reason is only valid when status is closed"
            )
        row.closed_reason = body.closed_reason
    if "follow_up_at" in sent:
        row.follow_up_at = body.follow_up_at
    await session.commit()
    await session.refresh(row)
    return await _out(session, row)
```

with `HTTPException` added to the FastAPI import.

Then from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_flow_api.py tests/api/test_packages_api.py tests/api/test_applications_api.py tests/api/test_jobs_api.py tests/api/test_tailor_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): a way out of every stage (hide, archive, close with a reason, follow up)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 11: GET /jobs gains ids, hidden, search_id, posted_within, sources, field, recommended

**Files:**
- Create: `apps/api/tests/api/test_jobs_filters_api.py`
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py` (`list_jobs`), `apps/api/src/rhapto/api/routers/jobs.py` (`list_jobs` lines 173–186, add the parsing helpers)
- Generated (never hand-edited): `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_jobs_filters_api.py`

**Interfaces:**

Consumes: `Job.hidden_at`, `Job.unlisted_at`, `Job.search_id` (Tasks 2 and 9); `Track.field` (Task 8); `find_field` (Task 7).

Produces:
- `jobs_repo.list_jobs(session, user_id, *, search=None, track=None, bucket=None, region="any", sort="fit", ids: list[uuid.UUID] | None = None, hidden: bool = False, search_id: uuid.UUID | None = None, posted_within: str = "any", sources: list[str] | None = None, track_ids: list[str] | None = None, recommended: bool = False) -> list[tuple[Job, str | None]]`.
- `jobs_repo.POSTED_WITHIN_DAYS: dict[str, int]` = `{"24h": 1, "7d": 7, "30d": 30}`.
- `api/routers/jobs.py`: `MAX_IDS = 200`; `def parse_ids(raw: str | None) -> list[uuid.UUID] | None`; `def parse_csv(raw: str | None) -> list[str] | None`.
- `GET /api/v1/jobs` query parameters `ids`, `hidden`, `search_id`, `posted_within`, `sources`, `field`, `recommended` alongside the existing `search`, `track`, `bucket`, `region`, `sort`.

Note for the executor: `recommended=true` is **not** in spec §10's list. It is added deliberately, because §3.1's Recommended roles card ("fit-ranked jobs with no resume and no application, not hidden, not no-longer-listed") is otherwise three client round trips and a join the client cannot do. See the Self-review.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/api/test_jobs_filters_api.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.models.profile.tracks import Track


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> dict[str, Any]:
    """Four jobs across two sources, two tracks, one saved search and three posting ages."""
    async with session_factory() as session:
        await profile_repo.upsert_track(
            session,
            user_id,
            Track(
                id="tpm", name="TPM", resume_base="b", min_fit=60, keywords=["tpm"],
                field="program-project-management", role="technical-program-manager",
            ),
        )
        await profile_repo.upsert_track(
            session,
            user_id,
            Track(id="be", name="Backend", resume_base="b", min_fit=60, keywords=["backend"],
                  field="engineering", role="backend"),
        )
        search = await searches_repo.create_search(
            session, user_id, name="Platform", keywords=["tpm"], location=None, remote="include"
        )
        now = datetime.now(UTC)
        made: dict[str, Any] = {"search_id": str(search.id)}
        for key, source, track, age_days, search_id in [
            ("fresh", "themuse", "tpm", 0, search.id),
            ("week", "remotive", "tpm", 4, None),
            ("old", "themuse", "be", 20, None),
            ("ancient", "greenhouse", "be", 200, None),
        ]:
            job = await jobs_repo.create_discovered_job(
                session, user_id, source=source, external_id=key, company="ExampleCo",
                title=f"{key} role", location=None, url=f"https://example.com/{key}",
                jd_text="x" * 80, posted_at=now - timedelta(days=age_days),
                identity_hash=f"h-{key}", repost_of=None, search_id=search_id,
            )
            job.best_track_id = track
            job.best_fit = 80
            made[key] = str(job.id)
        await session.commit()
        return made


async def test_ids_selects_exactly_those_jobs(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    wanted = f"{made['fresh']},{made['old']}"
    rows = (await client.get(f"/api/v1/jobs?ids={wanted}")).json()
    assert {j["id"] for j in rows} == {made["fresh"], made["old"]}


async def test_too_many_ids_is_422(client: httpx.AsyncClient) -> None:
    ids = ",".join(str(uuid.uuid4()) for _ in range(201))
    assert (await client.get(f"/api/v1/jobs?ids={ids}")).status_code == 422
    assert (await client.get("/api/v1/jobs?ids=not-a-uuid")).status_code == 422


async def test_search_id_filters_to_one_saved_search(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get(f"/api/v1/jobs?search_id={made['search_id']}")).json()
    assert [j["id"] for j in rows] == [made["fresh"]]


async def test_posted_within_windows(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    assert {j["id"] for j in (await client.get("/api/v1/jobs?posted_within=24h")).json()} == {
        made["fresh"]
    }
    assert {j["id"] for j in (await client.get("/api/v1/jobs?posted_within=7d")).json()} == {
        made["fresh"], made["week"]
    }
    assert len((await client.get("/api/v1/jobs?posted_within=30d")).json()) == 3
    assert len((await client.get("/api/v1/jobs?posted_within=any")).json()) == 4


async def test_sources_filter(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs?sources=remotive,greenhouse")).json()
    assert {j["id"] for j in rows} == {made["week"], made["ancient"]}


async def test_field_maps_to_its_tracks(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs?field=program-project-management")).json()
    assert {j["id"] for j in rows} == {made["fresh"], made["week"]}
    # A field the user has no track in is an empty result, not an error.
    assert (await client.get("/api/v1/jobs?field=design")).json() == []
    assert (await client.get("/api/v1/jobs?field=not-a-field")).status_code == 422


async def test_recommended_excludes_tailored_applied_hidden_and_unlisted(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    tailored_package: dict[str, Any],
) -> None:
    made = await _seed(session_factory, user_id)
    await client.post(f"/api/v1/jobs/{made['week']}/hide")
    await client.post("/api/v1/applications", json={"job_id": made["old"]})
    async with session_factory() as session:
        job = await jobs_repo.get_job(session, user_id, uuid.UUID(made["ancient"]))
        assert job is not None
        job.unlisted_at = datetime.now(UTC)
        await session.commit()
    rows = (await client.get("/api/v1/jobs?recommended=true")).json()
    # `fresh` is the only one left: the tailored job has a package, and the other three are
    # applied, hidden and unlisted.
    assert [j["id"] for j in rows] == [made["fresh"]]


async def test_filters_compose_with_sort(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    made = await _seed(session_factory, user_id)
    rows = (await client.get("/api/v1/jobs?sources=themuse&sort=newest")).json()
    assert [j["id"] for j in rows] == [made["fresh"], made["old"]]
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_jobs_filters_api.py`. Expected: `assert 4 == 2` on the `ids` test — FastAPI ignores the unknown query parameter and returns every job.

- [ ] **Step 3: Write minimal implementation** —

`db/repositories/jobs.py` — `list_jobs` grows the filters (everything else in the function is unchanged):

```python
#: How far back each `posted_within` value reaches.
POSTED_WITHIN_DAYS = {"24h": 1, "7d": 7, "30d": 30}


async def list_jobs(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    search: str | None = None,
    track: str | None = None,
    bucket: str | None = None,
    region: str = "any",
    sort: str = "fit",
    ids: list[uuid.UUID] | None = None,
    hidden: bool = False,
    search_id: uuid.UUID | None = None,
    posted_within: str = "any",
    sources: list[str] | None = None,
    track_ids: list[str] | None = None,
    recommended: bool = False,
) -> list[tuple[Job, str | None]]:
    tracks = select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()
    query = (
        select(Job, SearchRow.name)
        .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
        .outerjoin(SearchRow, SearchRow.id == Job.search_id)
        .where(Job.user_id == user_id)
    )
    if ids is not None:
        query = query.where(Job.id.in_(ids))
    # `hidden` is a switch, not a filter that can be off: the grid's default view must not show
    # jobs the user said no to, and "Show hidden" wants exactly those and nothing else.
    query = query.where(Job.hidden_at.is_not(None) if hidden else Job.hidden_at.is_(None))
    if search_id is not None:
        query = query.where(Job.search_id == search_id)
    if sources:
        query = query.where(Job.source.in_(sources))
    if track_ids is not None:
        # An empty list means "the user has no track in that field", which is an empty result,
        # not "no filter" -- hence the `is not None` test rather than a truthiness test.
        query = query.where(Job.best_track_id.in_(track_ids))
    days = POSTED_WITHIN_DAYS.get(posted_within)
    if days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=days)
        # A posting with no date from the source is judged by when Rhapto first saw it, which is
        # the only honest answer available.
        query = query.where(func.coalesce(Job.posted_at, Job.discovered_at) >= cutoff)
    if recommended:
        has_package = select(Package.id).where(
            Package.user_id == user_id, Package.job_id == Job.id
        )
        has_application = select(Application.id).where(
            Application.user_id == user_id, Application.job_id == Job.id
        )
        query = query.where(
            Job.unlisted_at.is_(None),
            ~has_package.exists(),
            ~has_application.exists(),
        )
    if search:
        ...  # unchanged
```

with `from datetime import UTC, datetime, timedelta` and `SearchRow` added to the module's imports.

`api/routers/jobs.py` — add the parsing helpers and the new parameters:

```python
#: A refetch after a live search asks for at most LIVE_CAP jobs per source across a handful of
#: sources; 200 is generous for that and small enough to keep the IN clause sane.
MAX_IDS = 200


def parse_ids(raw: str | None) -> list[uuid.UUID] | None:
    """`?ids=a,b,c` as UUIDs. None when the parameter was not sent at all."""
    if raw is None:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) > MAX_IDS:
        raise problem_error(422, f"ids accepts at most {MAX_IDS} values")
    try:
        return [uuid.UUID(p) for p in parts]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"ids contains a value that is not a UUID: {exc}") from exc


def parse_csv(raw: str | None) -> list[str] | None:
    if raw is None:
        return None
    return [p.strip() for p in raw.split(",") if p.strip()]


@router.get("", response_model=list[JobOut])
async def list_jobs(
    user_id: UserDep,
    session: SessionDep,
    search: str | None = Query(default=None),
    track: str | None = Query(default=None),
    bucket: Literal["fit", "low"] | None = Query(default=None),
    region: Literal["preferred", "us", "any"] = Query(default="any"),
    sort: Literal["fit", "newest"] = Query(default="fit"),
    ids: str | None = Query(default=None, description="comma-separated job ids, at most 200"),
    hidden: bool = Query(default=False, description="show only hidden jobs"),
    search_id: uuid.UUID | None = Query(default=None),
    posted_within: Literal["24h", "7d", "30d", "any"] = Query(default="any"),
    sources: str | None = Query(default=None, description="comma-separated source ids"),
    field: str | None = Query(default=None, description="taxonomy field id"),
    recommended: bool = Query(
        default=False,
        description="only jobs with no resume, no application, not hidden and not unlisted",
    ),
) -> list[JobOut]:
    track_ids: list[str] | None = None
    if field is not None:
        if find_field(field) is None:
            raise HTTPException(status_code=422, detail=f"unknown taxonomy field {field!r}")
        track_ids = [
            t.track_id for t in await profile_repo.list_tracks(session, user_id) if t.field == field
        ]
    rows = await repo.list_jobs(
        session,
        user_id,
        search=search,
        track=track,
        bucket=bucket,
        region=region,
        sort=sort,
        ids=parse_ids(ids),
        hidden=hidden,
        search_id=search_id,
        posted_within=posted_within,
        sources=parse_csv(sources),
        track_ids=track_ids,
        recommended=recommended,
    )
    return await _outs(session, user_id, rows)
```

`parse_ids` raises `HTTPException(422, ...)` in both branches (drop the `problem_error` placeholder above and use `HTTPException` for the count check too, so both failures render through the existing handlers identically). Add `from fastapi import HTTPException` and `from rhapto.services.taxonomy import find_field` to the imports; `_outs` now takes `list[tuple[Job, str | None]]` (already the case after Task 4).

Then from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_jobs_filters_api.py tests/api/test_jobs_api.py tests/api/test_flow_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): the Jobs grid's filters (ids, hidden, search, date, source, field, recommended)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 12: Unlisted detection — two consecutive misses mark a job "no longer listed"

**Files:**
- Create: `apps/api/tests/unit/test_unlisted.py`
- Modify: `apps/api/src/rhapto/db/repositories/jobs.py` (append `UNLISTED_AFTER` and `reconcile_listing`), `apps/api/src/rhapto/services/discovery/poller.py` (`poll_sources` success branch)
- Test: `apps/api/tests/unit/test_unlisted.py`

**Interfaces:**

Consumes: `Job.miss_count`, `Job.unlisted_at` (Task 9); `SourceSpec.search_id`, `SourceSpec.company` (Task 3).

Produces:
- `jobs_repo.UNLISTED_AFTER = 2`.
- `async def reconcile_listing(session, user_id, *, source: str, company: str | None, search_id: uuid.UUID | None, seen_external_ids: set[str]) -> int` — returns how many jobs it newly marked unlisted.
- `RunResult.unlisted` populated by the poller; `PollSummary.unlisted_jobs: int`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/unit/test_unlisted.py`:

```python
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Job, User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo


async def _job(
    session: AsyncSession, user: User, external_id: str, **kwargs: object
) -> Job:
    job = await jobs_repo.create_discovered_job(
        session,
        user.id,
        source=str(kwargs.pop("source", "greenhouse")),
        external_id=external_id,
        company=str(kwargs.pop("company", "ExampleCo")),
        title="Technical Program Manager",
        location=None,
        url=f"https://example.com/{external_id}",
        jd_text="x" * 80,
        posted_at=None,
        identity_hash=f"h-{external_id}",
        repost_of=None,
        **kwargs,  # type: ignore[arg-type]
    )
    await session.flush()
    return job


async def test_two_consecutive_misses_mark_a_job_unlisted(
    session: AsyncSession, user: User
) -> None:
    gone = await _job(session, user, "gone")
    still = await _job(session, user, "still")
    args = {"source": "greenhouse", "company": "ExampleCo", "search_id": None}
    assert await jobs_repo.reconcile_listing(
        session, user.id, seen_external_ids={"still"}, **args
    ) == 0
    assert gone.miss_count == 1 and gone.unlisted_at is None
    assert await jobs_repo.reconcile_listing(
        session, user.id, seen_external_ids={"still"}, **args
    ) == 1
    assert gone.miss_count == 2 and gone.unlisted_at is not None
    assert still.miss_count == 0 and still.unlisted_at is None
    # Already marked: it is not counted a second time.
    assert await jobs_repo.reconcile_listing(
        session, user.id, seen_external_ids={"still"}, **args
    ) == 0


async def test_a_sighting_resets_both_fields(session: AsyncSession, user: User) -> None:
    job = await _job(session, user, "back")
    args = {"source": "greenhouse", "company": "ExampleCo", "search_id": None}
    await jobs_repo.reconcile_listing(session, user.id, seen_external_ids=set(), **args)
    await jobs_repo.reconcile_listing(session, user.id, seen_external_ids=set(), **args)
    assert job.unlisted_at is not None
    await jobs_repo.reconcile_listing(session, user.id, seen_external_ids={"back"}, **args)
    assert job.miss_count == 0 and job.unlisted_at is None


async def test_the_scope_is_the_search_or_the_company_not_the_whole_source(
    session: AsyncSession, user: User
) -> None:
    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["a"], location=None, remote="include"
    )
    other = await searches_repo.create_search(
        session, user.id, name="B", keywords=["b"], location=None, remote="include"
    )
    mine = await _job(session, user, "mine", source="themuse", search_id=search.id)
    theirs = await _job(session, user, "theirs", source="themuse", search_id=other.id)
    other_company = await _job(session, user, "elsewhere", company="OtherCo")
    for _ in range(2):
        await jobs_repo.reconcile_listing(
            session, user.id, source="themuse", company=None, search_id=search.id,
            seen_external_ids=set(),
        )
    assert mine.unlisted_at is not None
    assert theirs.unlisted_at is None and theirs.miss_count == 0
    assert other_company.miss_count == 0


async def test_manual_jobs_are_never_touched(session: AsyncSession, user: User) -> None:
    manual = await jobs_repo.create_job(session, user.id, jd_text="y" * 80, company="ExampleCo")
    await session.flush()
    for _ in range(3):
        await jobs_repo.reconcile_listing(
            session, user.id, source="manual", company="ExampleCo", search_id=None,
            seen_external_ids=set(),
        )
    assert manual.miss_count == 0 and manual.unlisted_at is None


async def test_the_poller_reconciles_only_on_a_successful_non_empty_fetch(
    session: AsyncSession, user: User, fake_aggregators: None
) -> None:
    """A source that errors, or returns nothing, must not empty the user's queue."""
    from rhapto.db.repositories import profile as profile_repo
    from rhapto.engine.providers.fake import FakeEmbeddingProvider
    from rhapto.models.profile.watchlist import AggregatorEntry
    from rhapto.services.discovery.http import FakeDiscoveryHttp
    from rhapto.services.discovery.poller import poll_sources
    from tests.unit.test_poller import FakeAggregator  # registered by the fixture

    search = await searches_repo.create_search(
        session, user.id, name="A", keywords=["a"], location=None, remote="include"
    )
    stale = await _job(session, user, "stale", source="fake-agg", search_id=search.id)
    await profile_repo.replace_aggregators(
        session, user.id, [AggregatorEntry(source="fake-agg", enabled=True, keywords=[])]
    )
    await session.flush()
    FakeAggregator.postings = []
    await poll_sources(
        session, user.id, http=FakeDiscoveryHttp({}), embedder=FakeEmbeddingProvider(dimensions=384)
    )
    assert stale.miss_count == 0, "an empty fetch says nothing about what is still listed"
```

(`fake_aggregators` is the fixture added in Task 3's `tests/unit/test_poller.py`; move it into `tests/unit/conftest.py` so both modules can request it, changing nothing about its body.)

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_unlisted.py`. Expected: `AttributeError: module 'rhapto.db.repositories.jobs' has no attribute 'reconcile_listing'`.

- [ ] **Step 3: Write minimal implementation** —

`db/repositories/jobs.py` — append:

```python
#: Consecutive polls that must miss a posting before it counts as gone. Two, not one: a source
#: paginating differently, or a transient partial page, routinely drops a posting for one run.
UNLISTED_AFTER = 2


async def reconcile_listing(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    source: str,
    company: str | None,
    search_id: uuid.UUID | None,
    seen_external_ids: set[str],
) -> int:
    """Update miss counts for one poll of one source, and return how many jobs it just retired.

    The scope is what this particular fetch could have returned -- the saved search's own
    `search_id`, or the company for a board -- never the whole source. Scoping wider would mark
    every job from a search the user just paused as unlisted the first time another search ran.
    A job that is seen again has both fields cleared: postings come back.
    """
    scope = [Job.user_id == user_id, Job.source == source, Job.external_id.is_not(None)]
    if search_id is not None:
        scope.append(Job.search_id == search_id)
    elif company is not None:
        scope.append(Job.company == company)
    rows = list(await session.scalars(select(Job).where(*scope)))
    now = datetime.now(UTC)
    retired = 0
    for job in rows:
        if job.external_id in seen_external_ids:
            job.miss_count = 0
            job.unlisted_at = None
            continue
        if job.unlisted_at is not None:
            continue
        job.miss_count = min(job.miss_count + 1, UNLISTED_AFTER)
        if job.miss_count >= UNLISTED_AFTER:
            job.unlisted_at = now
            retired += 1
    await session.flush()
    return retired
```

`services/discovery/poller.py` — in `poll_sources`' success branch, between `_ingest`/`_discover_boards` and `finish_run`:

```python
            unlisted = 0
            if postings:
                # Only a fetch that actually returned something can tell us a posting is gone.
                # An empty page (or a silently truncated one) would otherwise retire the whole
                # queue on the next poll.
                unlisted = await jobs_repo.reconcile_listing(
                    session,
                    user_id,
                    source=spec.source,
                    company=spec.company,
                    search_id=spec.search_id,
                    seen_external_ids={p.external_id for p in postings},
                )
            disc_repo.finish_run(run, found=len(postings), new=len(created), error=None)
            await session.commit()
            results.append(
                RunResult(
                    spec.source, spec.board, len(postings), len(created), None,
                    spec.search_id, unlisted,
                )
            )
```

and `PollSummary` gains `unlisted_jobs: int`, summed as `sum(r.unlisted for r in results)` when the summary is built.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_unlisted.py tests/unit/test_poller.py tests/unit/test_worker_discovery.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(discovery): retire a posting after two polls that no longer return it

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 13: Live search service

**Files:**
- Create: `apps/api/src/rhapto/services/discovery/live.py`, `apps/api/tests/unit/test_live_search.py`
- Modify: none
- Test: `apps/api/tests/unit/test_live_search.py`

**Interfaces:**

Consumes: `SearchSpec` (Task 1), `get_aggregator`/`get_source` (Task 1), `identity_hash` and `dedupe_hash` (existing), `jobs_repo.create_discovered_job(..., search_id=None, salary_text=...)` (Tasks 2 and 9).

Produces:
- `LIVE_TIMEOUT_SECONDS = 8.0`; `LIVE_CAP = 30`.
- `@dataclass(frozen=True) class LiveTarget: source: str; board: str | None = None; company: str | None = None; credentials: dict[str, str] = field(default_factory=dict)` (declared with `field(default_factory=dict)` inside a frozen dataclass, which is legal).
- `@dataclass class SourceOutcome: found: int = 0; new: int = 0; error: str | None = None`.
- `@dataclass class LiveResult: jobs: list[Job]; per_source: dict[str, SourceOutcome]; new_job_ids: list[uuid.UUID]`.
- `async def live_search(session, user_id, *, http, spec: SearchSpec, targets: list[LiveTarget]) -> LiveResult`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/unit/test_live_search.py`:

```python
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import User
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import FakeDiscoveryHttp
from rhapto.services.discovery.live import LIVE_CAP, LiveTarget, live_search
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo

SPEC = SearchSpec(keywords=("program manager",))


def _posting(n: int, **kwargs: object) -> Posting:
    data = {
        "external_id": f"e{n}",
        "company": "ExampleCo",
        "title": f"Program Manager {n}",
        "location": "Denver, CO",
        "url": f"https://example.com/{n}",
        "jd_text": f"Program {n}. " * 20,
    }
    data.update(kwargs)
    return Posting(**data)  # type: ignore[arg-type]


class Alpha:
    info = SourceInfo("live-alpha", "aggregator", "Alpha", False)
    result: object = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        value = type(self).result
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return await value()
        return list(value)  # type: ignore[arg-type]


class Beta(Alpha):
    info = SourceInfo("live-beta", "aggregator", "Beta", False)
    result: object = []


@pytest.fixture(autouse=True)
def live_sources():  # type: ignore[no-untyped-def]
    SOURCES["live-alpha"] = Alpha  # type: ignore[assignment]
    SOURCES["live-beta"] = Beta  # type: ignore[assignment]
    yield
    SOURCES.pop("live-alpha", None)
    SOURCES.pop("live-beta", None)
    Alpha.result = []
    Beta.result = []


TARGETS = [LiveTarget(source="live-alpha"), LiveTarget(source="live-beta")]


async def test_new_postings_are_stored_unscored_with_no_search_id(
    session: AsyncSession, user: User
) -> None:
    Alpha.result = [_posting(1, salary_text="$150k")]
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    assert {j.external_id for j in result.jobs} == {"e1", "e2"}
    assert all(j.search_id is None and j.best_fit is None for j in result.jobs)
    assert {j.salary_text for j in result.jobs} == {"$150k", None}
    assert result.per_source == {
        "live-alpha": {"found": 1, "new": 1, "error": None},
        "live-beta": {"found": 1, "new": 1, "error": None},
    } or (
        result.per_source["live-alpha"].found == 1 and result.per_source["live-beta"].new == 1
    )
    assert len(result.new_job_ids) == 2


async def test_an_identity_match_returns_the_existing_scored_job(
    session: AsyncSession, user: User
) -> None:
    existing = await jobs_repo.create_discovered_job(
        session, user.id, source="greenhouse", external_id="old", company="ExampleCo",
        title="Program Manager 1", location="Denver, CO", url="https://gh.example/old",
        jd_text="different text " * 20, posted_at=None,
        identity_hash=identity_hash("ExampleCo", "Program Manager 1", "Denver, CO"),
        repost_of=None,
    )
    existing.best_fit = 82
    await session.flush()
    Alpha.result = [_posting(1)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    # Opposite of the poller: a live search shows the job the user already has (with its score)
    # rather than inserting a repost row the moment they type a query.
    assert [j.id for j in result.jobs] == [existing.id]
    assert result.jobs[0].best_fit == 82
    assert result.new_job_ids == []
    assert result.per_source["live-alpha"].new == 0


async def test_a_timeout_is_reported_not_raised(session: AsyncSession, user: User) -> None:
    async def never() -> list[Posting]:
        await asyncio.sleep(30)
        return []

    Alpha.result = never
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS, timeout=0.05
    )
    assert result.per_source["live-alpha"].error is not None
    assert "timed out" in result.per_source["live-alpha"].error
    assert result.per_source["live-beta"].new == 1
    assert [j.external_id for j in result.jobs] == ["e2"]


async def test_a_source_error_is_reported_not_raised(session: AsyncSession, user: User) -> None:
    Alpha.result = SourceError("Alpha: check the API key")
    Beta.result = [_posting(2)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=TARGETS
    )
    assert result.per_source["live-alpha"].error == "Alpha: check the API key"
    assert len(result.jobs) == 1


async def test_each_source_is_capped(session: AsyncSession, user: User) -> None:
    Alpha.result = [_posting(n) for n in range(LIVE_CAP + 20)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert len(result.jobs) == LIVE_CAP
    assert result.per_source["live-alpha"].found == LIVE_CAP


async def test_posted_within_drops_old_postings_but_keeps_undated_ones(
    session: AsyncSession, user: User
) -> None:
    from datetime import UTC, datetime, timedelta

    old = _posting(1, posted_at=datetime.now(UTC) - timedelta(days=40))
    fresh = _posting(2, posted_at=datetime.now(UTC))
    undated = _posting(3)
    Alpha.result = [old, fresh, undated]
    spec = SearchSpec(keywords=("program manager",), posted_within="30d")
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=spec, targets=[TARGETS[0]]
    )
    assert {j.external_id for j in result.jobs} == {"e2", "e3"}


async def test_results_are_ordered_scored_first(session: AsyncSession, user: User) -> None:
    scored = await jobs_repo.create_discovered_job(
        session, user.id, source="greenhouse", external_id="old", company="ExampleCo",
        title="Program Manager 1", location="Denver, CO", url="https://gh.example/old",
        jd_text="different " * 20, posted_at=None,
        identity_hash=identity_hash("ExampleCo", "Program Manager 1", "Denver, CO"),
        repost_of=None,
    )
    scored.best_fit = 70
    await session.flush()
    Alpha.result = [_posting(2), _posting(1)]
    result = await live_search(
        session, user.id, http=FakeDiscoveryHttp({}), spec=SPEC, targets=[TARGETS[0]]
    )
    assert result.jobs[0].id == scored.id
    assert result.jobs[1].best_fit is None
```

(the first test's `per_source` assertion should be written as the second form only — compare `SourceOutcome` attributes, not a dict — clean it up to `assert result.per_source["live-alpha"].found == 1 and result.per_source["live-alpha"].new == 1` and the same for beta when writing the file.)

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_live_search.py`. Expected: `ModuleNotFoundError: No module named 'rhapto.services.discovery.live'`.

- [ ] **Step 3: Write minimal implementation** — create `apps/api/src/rhapto/services/discovery/live.py`:

```python
"""The synchronous half of discovery: one search, every source at once, one response.

The poller is patient and thorough; this is neither. It fans out with a hard per-source timeout,
caps each source, and never lets one vendor's outage fail the request -- the user typed a query
and is watching a spinner.

Two rules differ from the poller on purpose:

* An identity-hash match returns the job the user already has, rather than inserting a repost.
  The poller is recording history (a genuinely re-posted job is a new event); a search box is
  answering "what is out there", and showing the same role twice -- once scored, once not --
  is just wrong.
* Nothing is scored here. Scoring needs the embedding provider and takes long enough to blow the
  request budget, so the caller enqueues `score_jobs` and the client refetches.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.hashing import dedupe_hash
from rhapto.db.models import Job
from rhapto.db.repositories import jobs as jobs_repo
from rhapto.services.discovery.dedupe import identity_hash
from rhapto.services.discovery.http import DiscoveryHttp, FakeDiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import POSTED_WITHIN_DAYS, SearchSpec
from rhapto.services.discovery.sources import get_aggregator, get_source
from rhapto.services.discovery.sources.base import SourceError

logger = logging.getLogger(__name__)

#: How long any one source gets before the response goes out without it.
LIVE_TIMEOUT_SECONDS = 8.0
#: How many postings per source reach the database. The grid shows a page at a time; a search
#: box that quietly ingests hundreds of rows per keystroke is a different product.
LIVE_CAP = 30


@dataclass(frozen=True)
class LiveTarget:
    """One thing to ask: an aggregator (board None) or a watchlist board."""

    source: str
    board: str | None = None
    company: str | None = None
    credentials: dict[str, str] = field(default_factory=dict)


@dataclass
class SourceOutcome:
    found: int = 0
    new: int = 0
    error: str | None = None


@dataclass
class LiveResult:
    jobs: list[Job]
    per_source: dict[str, SourceOutcome]
    new_job_ids: list[uuid.UUID]


async def _fetch_one(
    http: DiscoveryHttp | FakeDiscoveryHttp,
    target: LiveTarget,
    spec: SearchSpec,
    timeout: float,
) -> tuple[LiveTarget, list[Posting], str | None]:
    """Fetch one target. Never raises, never touches the session.

    The session is deliberately out of reach here: these coroutines run concurrently under
    `asyncio.gather`, and an AsyncSession is not safe to share between them.
    """
    try:
        if target.board is None:
            postings = await asyncio.wait_for(
                get_aggregator(target.source).fetch_search(http, spec, target.credentials),  # type: ignore[arg-type]
                timeout,
            )
        else:
            postings = await asyncio.wait_for(
                get_source(target.source).fetch(  # type: ignore[arg-type]
                    http, board=target.board, keywords=list(spec.keywords)
                ),
                timeout,
            )
    except TimeoutError:
        return (target, [], f"timed out after {timeout:g}s")
    except SourceError as exc:
        return (target, [], str(exc))
    except Exception as exc:  # one adapter's bug must not fail the search
        logger.exception("live search of %s failed", target.source)
        return (target, [], f"{type(exc).__name__}: {exc}")
    return (target, postings, None)


def _within_window(posting: Posting, posted_within: str) -> bool:
    """A posting with no date from the source is kept: silence is not evidence of age."""
    days = POSTED_WITHIN_DAYS.get(posted_within)
    if days is None or posting.posted_at is None:
        return True
    return posting.posted_at >= datetime.now(UTC) - timedelta(days=days)


async def live_search(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    http: DiscoveryHttp | FakeDiscoveryHttp,
    spec: SearchSpec,
    targets: list[LiveTarget],
    timeout: float = LIVE_TIMEOUT_SECONDS,
) -> LiveResult:
    """Ask every target at once, ingest what came back, and report per source."""
    per_source: dict[str, SourceOutcome] = {}
    if not targets:
        return LiveResult(jobs=[], per_source=per_source, new_job_ids=[])
    fetched = await asyncio.gather(
        *(_fetch_one(http, target, spec, timeout) for target in targets)
    )

    jobs: list[Job] = []
    new_ids: list[uuid.UUID] = []
    seen_hashes: set[str] = set()
    seen_ids: set[uuid.UUID] = set()
    # Ingest is sequential and after the gather: one session, one writer.
    for target, postings, error in fetched:
        outcome = per_source.setdefault(target.source, SourceOutcome())
        if error is not None:
            outcome.error = outcome.error or error
            continue
        kept = [p for p in postings if _within_window(p, spec.posted_within)][:LIVE_CAP]
        outcome.found += len(kept)
        for posting in kept:
            company = target.company or posting.company
            text_hash = dedupe_hash(posting.jd_text)
            if text_hash in seen_hashes:
                continue
            seen_hashes.add(text_hash)
            existing = await jobs_repo.find_by_external_id(
                session, user_id, target.source, posting.external_id
            ) or await jobs_repo.find_by_identity(
                session, user_id, identity_hash(company, posting.title, posting.location)
            )
            if existing is not None:
                if existing.id not in seen_ids:
                    seen_ids.add(existing.id)
                    jobs.append(existing)
                continue
            job = await jobs_repo.create_discovered_job(
                session,
                user_id,
                source=target.source,
                external_id=posting.external_id,
                company=company,
                title=posting.title,
                location=posting.location,
                url=posting.url,
                jd_text=posting.jd_text,
                posted_at=posting.posted_at,
                identity_hash=identity_hash(company, posting.title, posting.location),
                repost_of=None,
                search_id=None,
                salary_text=posting.salary_text,
            )
            seen_ids.add(job.id)
            jobs.append(job)
            new_ids.append(job.id)
            outcome.new += 1
    await session.flush()
    # Scored jobs first, best fit at the top; everything the search just found follows in the
    # order the sources returned it, and gets its ring as soon as the worker catches up.
    jobs.sort(key=lambda j: (j.best_fit is None, -(j.best_fit or 0)))
    return LiveResult(jobs=jobs, per_source=per_source, new_job_ids=new_ids)
```

Move `POSTED_WITHIN_DAYS` from `db/repositories/jobs.py` into `services/discovery/search.py` and have the repo import it from there — `services` may import `db`, but `db` may not import `services`, so the shared constant has to live on the `db` side or be duplicated. Keep it in `db/repositories/jobs.py` and have `live.py` import it from there instead:

```python
from rhapto.db.repositories.jobs import POSTED_WITHIN_DAYS
```

(that is the import to write; the sentence above records why the other direction is impossible.)

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_live_search.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(discovery): live search fan-out with a per-source timeout and cap

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 14: POST /api/v1/search

**Files:**
- Create: `apps/api/src/rhapto/api/routers/search.py`, `apps/api/tests/api/test_live_search_api.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (append `LiveSearchIn`, `PerSourceOut`, `LiveSearchOut`), `apps/api/src/rhapto/api/app.py` (imports + mount)
- Generated (never hand-edited): `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_live_search_api.py`

**Interfaces:**

Consumes: `live_search(session, user_id, *, http, spec, targets, timeout=LIVE_TIMEOUT_SECONDS) -> LiveResult`, `LiveTarget`, `SourceOutcome` (Task 13); `SearchSpec` (Task 1); `creds_repo.get_credentials(session, fernet, user_id, source)` (Task 2); `fernet_for(settings)` (existing); `AppState.discovery_http` (Task 4); `find_field` (Task 7); `job_to_out` / `_outs` (Task 4).

Produces:
- `LiveSearchIn(query: str, location: str | None, remote: RemoteValue, field: str | None, posted_within: Literal["24h","7d","30d","any"], sources: list[str] | None)`.
- `PerSourceOut(found: int, new: int, error: str | None)`.
- `LiveSearchOut(jobs: list[JobOut], per_source: dict[str, PerSourceOut])`.
- Route `POST /api/v1/search`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/api/test_live_search_api.py`:

```python
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import profile as profile_repo
from rhapto.models.profile.watchlist import AggregatorEntry
from rhapto.models.profile.watchlist import WatchlistEntry as WatchlistModel
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.discovery.sources.base import SourceError, SourceInfo


class ApiAlpha:
    info = SourceInfo("api-alpha", "aggregator", "Api Alpha", False)
    result: object = []
    seen: list[SearchSpec] = []

    async def fetch_search(self, http, spec, credentials):  # type: ignore[no-untyped-def]
        type(self).seen.append(spec)
        value = type(self).result
        if isinstance(value, BaseException):
            raise value
        if callable(value):
            return await value()
        return list(value)  # type: ignore[arg-type]


class ApiKeyed(ApiAlpha):
    info = SourceInfo(
        "api-keyed", "aggregator", "Api Keyed", False, needs_key=True, fields=("api_key",)
    )
    result: object = []
    seen: list[SearchSpec] = []


@pytest.fixture(autouse=True)
def api_sources():  # type: ignore[no-untyped-def]
    ApiAlpha.result, ApiAlpha.seen = [], []
    ApiKeyed.result, ApiKeyed.seen = [], []
    SOURCES["api-alpha"] = ApiAlpha  # type: ignore[assignment]
    SOURCES["api-keyed"] = ApiKeyed  # type: ignore[assignment]
    yield
    SOURCES.pop("api-alpha", None)
    SOURCES.pop("api-keyed", None)


def _posting(n: int) -> Posting:
    return Posting(
        external_id=f"e{n}",
        company="ExampleCo",
        title=f"Program Manager {n}",
        location="Denver, CO",
        url=f"https://example.com/{n}",
        jd_text=f"Program {n}. " * 20,
        salary_text="$150k" if n == 1 else None,
    )


async def _enable(
    session_factory: async_sessionmaker[AsyncSession], user_id: Any, *sources: str
) -> None:
    async with session_factory() as session:
        await profile_repo.replace_aggregators(
            session,
            user_id,
            [AggregatorEntry(source=s, enabled=True, keywords=[]) for s in sources],
        )
        await session.commit()


async def test_a_search_returns_jobs_and_per_source_counts(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-alpha")
    ApiAlpha.result = [_posting(1), _posting(2)]
    response = await client.post(
        "/api/v1/search",
        json={"query": "program manager", "location": "Denver, CO", "remote": "include"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["jobs"]) == 2
    assert body["per_source"]["api-alpha"] == {"found": 2, "new": 2, "error": None}
    assert {j["salary_text"] for j in body["jobs"]} == {"$150k", None}
    # New jobs come back unscored; the client refetches GET /jobs?ids= until they have a ring.
    assert all(j["best_fit"] is None for j in body["jobs"])
    ids = ",".join(j["id"] for j in body["jobs"])
    assert len((await client.get(f"/api/v1/jobs?ids={ids}")).json()) == 2
    assert ApiAlpha.seen[0].keywords == ("program manager",)
    assert ApiAlpha.seen[0].location == "Denver, CO"


async def test_a_failing_source_is_reported_and_the_rest_still_answer(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-alpha", "api-keyed")
    ApiAlpha.result = [_posting(1)]
    ApiKeyed.result = SourceError("Api Keyed: check the API key")
    body = (await client.post("/api/v1/search", json={"query": "program manager"})).json()
    assert body["per_source"]["api-keyed"]["error"] == "Api Keyed: check the API key"
    assert body["per_source"]["api-alpha"]["new"] == 1
    assert len(body["jobs"]) == 1


async def test_a_slow_source_times_out_without_failing_the_request(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from rhapto.api.routers import search as search_router

    monkeypatch.setattr(search_router, "LIVE_TIMEOUT_SECONDS", 0.05)
    await _enable(session_factory, user_id, "api-alpha")

    async def never() -> list[Posting]:
        await asyncio.sleep(30)
        return []

    ApiAlpha.result = never
    response = await client.post("/api/v1/search", json={"query": "program manager"})
    assert response.status_code == 200
    assert "timed out" in response.json()["per_source"]["api-alpha"]["error"]


async def test_watchlist_boards_are_searched_too(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    async with session_factory() as session:
        await profile_repo.replace_watchlist(
            session,
            user_id,
            [WatchlistModel(company="ExampleCo", source="greenhouse", board="exampleco", keywords=[])],
        )
        await session.commit()
    body = (await client.post("/api/v1/search", json={"query": "program manager"})).json()
    # The fake HTTP client has no route for the Greenhouse board, so the board reports an error
    # instead of the request failing.
    assert "greenhouse" in body["per_source"]


async def test_the_sources_filter_narrows_the_fan_out(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: Any
) -> None:
    await _enable(session_factory, user_id, "api-alpha", "api-keyed")
    ApiAlpha.result = [_posting(1)]
    body = (
        await client.post(
            "/api/v1/search", json={"query": "program manager", "sources": ["api-alpha"]}
        )
    ).json()
    assert list(body["per_source"]) == ["api-alpha"]


async def test_validation(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/v1/search", json={"query": ""})).status_code == 422
    assert (
        await client.post("/api/v1/search", json={"query": "pm", "remote": "maybe"})
    ).status_code == 422
    assert (
        await client.post("/api/v1/search", json={"query": "pm", "field": "not-a-field"})
    ).status_code == 422
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_live_search_api.py`. Expected: `assert 404 == 200` on `POST /api/v1/search`.

- [ ] **Step 3: Write minimal implementation** —

`api/schemas.py` — append:

```python
class LiveSearchIn(BaseModel):
    """The search form: one free-text query plus the filter chips."""

    query: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    field: str | None = Field(default=None, max_length=50)
    posted_within: Literal["24h", "7d", "30d", "any"] = "any"
    #: None means every enabled source; a list narrows the fan-out to those source ids.
    sources: list[str] | None = None


class PerSourceOut(BaseModel):
    found: int
    new: int
    error: str | None = None


class LiveSearchOut(BaseModel):
    jobs: list[JobOut]
    #: Keyed by source id, so the UI can say which vendor was slow or needs a key.
    per_source: dict[str, PerSourceOut]
```

`apps/api/src/rhapto/api/routers/search.py`:

```python
"""One search box, every source at once.

Everything slow is bounded here: `live_search` caps each source and gives it
`LIVE_TIMEOUT_SECONDS`, so this endpoint answers in roughly that long no matter how many vendors
are having a bad day. Scoring is not part of the response -- the new rows are enqueued and the
client refetches `GET /jobs?ids=` until they have a fit ring.
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_enqueuer, get_session, get_settings_dep, get_state
from rhapto.api.routers.jobs import _outs
from rhapto.api.schemas import LiveSearchIn, LiveSearchOut, PerSourceOut
from rhapto.config import Settings
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import source_credentials as creds_repo
from rhapto.services.discovery.live import LIVE_TIMEOUT_SECONDS, LiveTarget, live_search
from rhapto.services.discovery.search import SearchSpec
from rhapto.services.discovery.sources import SOURCES
from rhapto.services.enqueue import Enqueuer
from rhapto.services.secrets import SecretsError, fernet_for
from rhapto.services.taxonomy import find_field

logger = logging.getLogger(__name__)

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
EnqueuerDep = Annotated[Enqueuer, Depends(get_enqueuer)]


async def build_targets(
    session: AsyncSession, settings: Settings, user_id: uuid.UUID, wanted: list[str] | None
) -> list[LiveTarget]:
    """Every enabled aggregator plus every watchlist board, narrowed by `wanted` if given."""
    fernet = None
    try:
        fernet = fernet_for(settings)
    except SecretsError:
        # No deployment secret: keyless sources still work, keyed ones report a missing key.
        logger.warning("no encryption secret configured; keyed sources will be skipped")
    targets: list[LiveTarget] = []
    for row in await profile_repo.list_aggregators(session, user_id):
        if not row.enabled or (wanted is not None and row.source not in wanted):
            continue
        info = SOURCES[row.source].info if row.source in SOURCES else None
        credentials: dict[str, str] = {}
        if info is not None and info.needs_key and fernet is not None:
            credentials = await creds_repo.get_credentials(session, fernet, user_id, row.source)
        targets.append(LiveTarget(source=row.source, credentials=credentials))
    for entry in await profile_repo.list_watchlist(session, user_id):
        if wanted is not None and entry.source not in wanted:
            continue
        targets.append(
            LiveTarget(source=entry.source, board=entry.board, company=entry.company)
        )
    return targets


@router.post("/search", response_model=LiveSearchOut)
async def live(
    body: LiveSearchIn,
    request: Request,
    user_id: UserDep,
    session: SessionDep,
    settings: SettingsDep,
    enqueuer: EnqueuerDep,
) -> LiveSearchOut:
    if body.field is not None and find_field(body.field) is None:
        raise HTTPException(status_code=422, detail=f"unknown taxonomy field {body.field!r}")
    spec = SearchSpec(
        keywords=(body.query.strip(),),
        location=(body.location or "").strip() or None,
        remote=body.remote,
        name=body.query.strip(),
        field=body.field,
        posted_within=body.posted_within,
    )
    targets = await build_targets(session, settings, user_id, body.sources)
    result = await live_search(
        session,
        user_id,
        http=get_state(request).discovery_http,
        spec=spec,
        targets=targets,
        timeout=LIVE_TIMEOUT_SECONDS,
    )
    await session.commit()
    if result.new_job_ids:
        try:
            await enqueuer.enqueue(
                "score_jobs",
                user_id=str(user_id),
                job_ids=[str(i) for i in result.new_job_ids],
            )
        except Exception:  # the rows are committed; a queue outage must not fail the search
            logger.exception(
                "could not enqueue %s; %d new job(s) are saved but not scored",
                "score_jobs",
                len(result.new_job_ids),
            )
    session.expire_all()
    ids = [job.id for job in result.jobs]
    rows = await __import__("rhapto.db.repositories.jobs", fromlist=["list_jobs"]).list_jobs(
        session, user_id, ids=ids, sort="fit"
    )
    return LiveSearchOut(
        jobs=await _outs(session, user_id, rows),
        per_source={
            name: PerSourceOut(found=o.found, new=o.new, error=o.error)
            for name, o in result.per_source.items()
        },
    )
```

Replace that `__import__` with a normal top-level `from rhapto.db.repositories import jobs as jobs_repo` and call `jobs_repo.list_jobs(session, user_id, ids=ids, sort="fit")` — the refetch after the commit is what makes `JobOut` carry the package/application/score joins that `_outs` expects, and it is a single query.

`LIVE_TIMEOUT_SECONDS` is re-exported from this module (imported at the top) precisely so a test can monkeypatch `search_router.LIVE_TIMEOUT_SECONDS`.

`api/app.py` — import the `search` router and mount it: `app.include_router(search.router, prefix=API_PREFIX, tags=["search"])`.

Then from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_live_search_api.py tests/unit/test_live_search.py tests/api/test_jobs_filters_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): POST /search fans one query out to every enabled source

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 15: Saved searches — query or keywords, last_viewed_at, new_count, /viewed

**Files:**
- Create: `apps/api/tests/api/test_saved_search_counts_api.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (`SearchIn`, `SearchOut`), `apps/api/src/rhapto/api/routers/searches.py` (`search_to_out`, create, update, append `/viewed`), `apps/api/src/rhapto/db/repositories/searches.py` (append `new_counts`, `mark_viewed`)
- Generated (never hand-edited): `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_saved_search_counts_api.py`

**Interfaces:**

Consumes: `SearchRow.last_viewed_at` (Task 9), `Job.search_id`, `Job.hidden_at`, `Job.unlisted_at` (Tasks 2 and 9).

Produces:
- `SearchIn` accepting exactly one of `query: str | None` / `keywords: list[str] | None`, with `name: str | None` defaulting to the query; properties `resolved_keywords: list[str]` and `resolved_name: str`.
- `SearchOut` gains `last_viewed_at: datetime | None` and `new_count: int`.
- `searches_repo.new_counts(session, user_id) -> dict[uuid.UUID, int]` (one grouped query).
- `searches_repo.mark_viewed(session, row) -> None`.
- Route `POST /api/v1/searches/{search_id}/viewed` → `SearchOut`.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/api/test_saved_search_counts_api.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import searches as searches_repo


async def test_a_search_can_be_created_from_a_bare_query(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/v1/searches", json={"query": "program manager"})
    assert created.status_code == 201
    body = created.json()
    # The form sends what the user typed; the name and the keyword list follow from it.
    assert body["name"] == "program manager"
    assert body["keywords"] == ["program manager"]
    assert body["new_count"] == 0 and body["last_viewed_at"] is None


async def test_keywords_still_work_and_an_explicit_name_wins(client: httpx.AsyncClient) -> None:
    created = await client.post(
        "/api/v1/searches", json={"name": "Platform", "keywords": ["tpm", "delivery"]}
    )
    assert created.json()["name"] == "Platform"
    assert created.json()["keywords"] == ["tpm", "delivery"]


async def test_query_and_keywords_together_are_rejected(client: httpx.AsyncClient) -> None:
    both = await client.post("/api/v1/searches", json={"query": "pm", "keywords": ["pm"]})
    assert both.status_code == 422
    neither = await client.post("/api/v1/searches", json={"name": "x"})
    assert neither.status_code == 422


async def _job_for(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
    search_id: uuid.UUID,
    external_id: str,
    **kwargs: Any,
) -> uuid.UUID:
    async with session_factory() as session:
        job = await jobs_repo.create_discovered_job(
            session, user_id, source="themuse", external_id=external_id, company="ExampleCo",
            title="Program Manager", location=None, url=f"https://example.com/{external_id}",
            jd_text="x" * 80, posted_at=None, identity_hash=f"h-{external_id}", repost_of=None,
            search_id=search_id,
        )
        for key, value in kwargs.items():
            setattr(job, key, value)
        await session.commit()
        return job.id


async def test_new_count_counts_jobs_discovered_since_the_last_view(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    search_id = uuid.UUID((await client.post("/api/v1/searches", json={"query": "pm"})).json()["id"])
    await _job_for(session_factory, user_id, search_id, "a")
    await _job_for(session_factory, user_id, search_id, "b")
    # Hidden and unlisted jobs have left the flow, so they are not "new" to look at.
    await _job_for(session_factory, user_id, search_id, "c", hidden_at=datetime.now(UTC))
    await _job_for(session_factory, user_id, search_id, "d", unlisted_at=datetime.now(UTC))
    listed = (await client.get("/api/v1/searches")).json()
    assert listed[0]["new_count"] == 2
    viewed = await client.post(f"/api/v1/searches/{search_id}/viewed")
    assert viewed.status_code == 200
    assert viewed.json()["last_viewed_at"] is not None
    assert viewed.json()["new_count"] == 0
    assert (await client.get("/api/v1/searches")).json()[0]["new_count"] == 0
    await _job_for(session_factory, user_id, search_id, "e")
    assert (await client.get("/api/v1/searches")).json()[0]["new_count"] == 1


async def test_viewed_on_an_unknown_search_is_404(client: httpx.AsyncClient) -> None:
    missing = "00000000-0000-0000-0000-000000000000"
    assert (await client.post(f"/api/v1/searches/{missing}/viewed")).status_code == 404


async def test_new_counts_is_one_query_for_every_search(
    session: AsyncSession, user: Any
) -> None:
    for name in ("a", "b", "c"):
        await searches_repo.create_search(
            session, user.id, name=name, keywords=[name], location=None, remote="include"
        )
    await session.commit()
    counts = await searches_repo.new_counts(session, user.id)
    assert len(counts) == 3 and set(counts.values()) == {0}
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_saved_search_counts_api.py`. Expected: `assert 422 == 201` on the bare-query create (`SearchIn` still requires `name` and `keywords`).

- [ ] **Step 3: Write minimal implementation** —

`api/schemas.py` — replace `SearchIn` and extend `SearchOut`:

```python
class SearchIn(BaseModel):
    """What the form sends: either the one phrase the user typed, or an explicit keyword list.

    The search box has a single input, so `query` is the common case and `name` follows from it;
    the Searches tab edits the keyword list directly. Accepting both at once would leave "what
    is this search actually looking for" ambiguous, so exactly one is required.
    """

    name: str | None = Field(default=None, max_length=100)
    query: str | None = Field(default=None, max_length=200)
    keywords: list[str] | None = Field(default=None, max_length=10)
    location: str | None = Field(default=None, max_length=200)
    remote: RemoteValue = "include"
    active: bool = True

    @model_validator(mode="after")
    def _exactly_one_source(self) -> SearchIn:
        if (self.query is None) == (self.keywords is None):
            raise ValueError("provide exactly one of query or keywords")
        if self.query is not None and not self.query.strip():
            raise ValueError("query must not be blank")
        if self.keywords is not None:
            cleaned = [k.strip() for k in self.keywords if k.strip()]
            if not cleaned or any(len(k) > 60 for k in cleaned):
                raise ValueError("each keyword must be 1-60 characters")
        return self

    @property
    def resolved_keywords(self) -> list[str]:
        if self.keywords is not None:
            return [k.strip() for k in self.keywords if k.strip()]
        return [(self.query or "").strip()]

    @property
    def resolved_name(self) -> str:
        return ((self.name or "").strip() or self.resolved_keywords[0])[:100]


class SearchOut(BaseModel):
    id: uuid.UUID
    name: str
    keywords: list[str]
    location: str | None
    remote: RemoteValue
    active: bool
    derived_from_track_id: str | None
    created_at: datetime
    last_viewed_at: datetime | None = None
    #: Jobs this search found since `last_viewed_at`, excluding hidden and unlisted ones.
    new_count: int = 0
```

`db/repositories/searches.py` — append:

```python
async def new_counts(session: AsyncSession, user_id: uuid.UUID) -> dict[uuid.UUID, int]:
    """Per search, how many of its jobs arrived after the user last opened it.

    One grouped query for every search, not one per row: the dashboard and the Searches tab both
    render the whole list at once. Hidden and unlisted jobs are excluded -- a count that points
    at a job the user already said no to is not news.
    """
    counted = (
        select(Job.search_id, func.count(Job.id).label("n"))
        .join(SearchRow, SearchRow.id == Job.search_id)
        .where(
            Job.user_id == user_id,
            Job.hidden_at.is_(None),
            Job.unlisted_at.is_(None),
            Job.discovered_at > func.coalesce(SearchRow.last_viewed_at, EPOCH),
        )
        .group_by(Job.search_id)
        .subquery()
    )
    rows = await session.execute(
        select(SearchRow.id, func.coalesce(counted.c.n, 0))
        .outerjoin(counted, counted.c.search_id == SearchRow.id)
        .where(SearchRow.user_id == user_id)
    )
    return {search_id: int(count) for search_id, count in rows.all()}


def mark_viewed(row: SearchRow) -> None:
    row.last_viewed_at = datetime.now(UTC)
```

with `EPOCH = datetime(1970, 1, 1, tzinfo=UTC)` as a module constant (a search never opened counts everything it has found) and `Job`, `func` added to the imports.

`api/routers/searches.py` — `search_to_out` takes the count, the create/update paths use the resolved values, and the new route:

```python
def search_to_out(row: SearchRow, new_count: int = 0) -> SearchOut:
    return SearchOut(
        id=row.id,
        name=row.name,
        keywords=list(row.keywords),
        location=row.location,
        remote=row.remote,  # type: ignore[arg-type]
        active=row.active,
        derived_from_track_id=row.derived_from_track_id,
        created_at=row.created_at,
        last_viewed_at=row.last_viewed_at,
        new_count=new_count,
    )


@router.get("", response_model=list[SearchOut])
async def list_searches(user_id: UserDep, session: SessionDep) -> list[SearchOut]:
    counts = await repo.new_counts(session, user_id)
    return [search_to_out(r, counts.get(r.id, 0)) for r in await repo.list_searches(session, user_id)]


@router.post("", response_model=SearchOut, status_code=201)
async def create_search(body: SearchIn, user_id: UserDep, session: SessionDep) -> SearchOut:
    row = await repo.create_search(
        session,
        user_id,
        name=body.resolved_name,
        keywords=body.resolved_keywords,
        location=body.location,
        remote=body.remote,
        active=body.active,
    )
    await session.commit()
    return search_to_out(row)


@router.post("/{search_id}/viewed", response_model=SearchOut)
async def mark_viewed(
    search_id: uuid.UUID, user_id: UserDep, session: SessionDep
) -> SearchOut:
    """The user opened this search's results, so nothing in it is unseen any more."""
    row = await repo.get_search(session, user_id, search_id)
    if row is None:
        raise not_found("search", search_id)
    repo.mark_viewed(row)
    await session.commit()
    counts = await repo.new_counts(session, user_id)
    return search_to_out(row, counts.get(row.id, 0))
```

and `update_search` passes `name=body.resolved_name, keywords=body.resolved_keywords` and returns `search_to_out(row, (await repo.new_counts(session, user_id)).get(row.id, 0))`.

Then from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_saved_search_counts_api.py tests/api/test_searches_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`. The portal-ui plan's Searches form sends `{name, keywords, ...}`, which still validates against the rewritten `SearchIn`; no web check runs here.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): saved searches count what is new since you last looked

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 16: GET /api/v1/dashboard

**Files:**
- Create: `apps/api/src/rhapto/db/repositories/dashboard.py`, `apps/api/src/rhapto/api/routers/dashboard.py`, `apps/api/tests/api/test_dashboard_api.py`
- Modify: `apps/api/src/rhapto/api/schemas.py` (append `ChecklistOut`, `SavedSearchCountOut`, `FollowUpOut`, `DashboardOut`), `apps/api/src/rhapto/api/app.py` (imports + mount), `apps/api/tests/api/conftest.py` (append the `select_counter` fixture)
- Generated (never hand-edited): `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`
- Test: `apps/api/tests/api/test_dashboard_api.py`

**Interfaces:**

Consumes: `Job.hidden_at`/`unlisted_at`/`best_fit`/`discovered_at` and `Package.archived_at`, `Application.follow_up_at` (Task 9); `searches_repo.new_counts` (Task 15); `Track.min_fit` (existing).

Produces:
- `db/repositories/dashboard.py`: `NEW_WINDOW_DAYS = 7`; `@dataclass(frozen=True) class Checklist(resume_template: bool, contact: bool, tracks: bool, blocks_verified: bool, guardrails: bool, location: bool, verified_blocks: int, total_blocks: int)`; `async def new_fit_count(session, user_id) -> int`; `async def needs_review_count(session, user_id) -> int`; `async def checklist(session, user_id) -> Checklist`; `async def due_followups(session, user_id) -> list[tuple[Application, Job]]`.
- `ChecklistOut`, `SavedSearchCountOut(id, name, new_count)`, `FollowUpOut(application_id, job, status, follow_up_at)`, `DashboardOut(new_fit_count, needs_review_count, checklist, saved_searches, due_followups)`.
- Route `GET /api/v1/dashboard`.

- [ ] **Step 1: Write the failing test** — first append to `apps/api/tests/api/conftest.py`:

```python
@pytest.fixture
def select_counter(engine: AsyncEngine) -> Iterator[list[str]]:
    """Every SELECT the app issues while the fixture is active.

    The dashboard is one request that has to answer five questions; the guard exists so a
    well-meaning refactor cannot turn it back into a loop of per-row queries.
    """
    seen: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):  # type: ignore[no-untyped-def]
        if statement.lstrip().upper().startswith("SELECT"):
            seen.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", before)
    try:
        yield seen
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", before)
```

with `from collections.abc import Iterator`, `from sqlalchemy import event` and `from sqlalchemy.ext.asyncio import AsyncEngine` added to that file's imports.

Then create `apps/api/tests/api/test_dashboard_api.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.repositories import jobs as jobs_repo
from rhapto.db.repositories import profile as profile_repo
from rhapto.db.repositories import searches as searches_repo
from rhapto.models.profile.tracks import Track


async def test_an_empty_account_reports_zeroes_and_an_empty_checklist(
    client: httpx.AsyncClient,
) -> None:
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["new_fit_count"] == 0 and body["needs_review_count"] == 0
    assert body["saved_searches"] == [] and body["due_followups"] == []
    assert body["checklist"] == {
        "resume_template": False,
        "contact": False,
        "tracks": False,
        "blocks_verified": False,
        "guardrails": False,
        "location": False,
        "verified_blocks": 0,
        "total_blocks": 0,
    }


async def test_the_checklist_reads_the_imported_profile(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    checklist = (await client.get("/api/v1/dashboard")).json()["checklist"]
    assert checklist["contact"] is True
    assert checklist["tracks"] is True
    assert checklist["guardrails"] is True
    assert checklist["location"] is True
    assert checklist["total_blocks"] > 0
    assert checklist["blocks_verified"] is (checklist["verified_blocks"] > 0)
    # No .docx was uploaded by the importer.
    assert checklist["resume_template"] is False


async def test_new_fit_count_respects_the_track_threshold_and_the_window(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    async with session_factory() as session:
        await profile_repo.upsert_track(
            session,
            user_id,
            Track(id="tpm", name="TPM", resume_base="b", min_fit=60, keywords=["tpm"]),
        )
        now = datetime.now(UTC)
        for key, fit, age, extra in [
            ("good", 80, 1, {}),
            ("weak", 40, 1, {}),
            ("stale", 90, 30, {}),
            ("hidden", 90, 1, {"hidden_at": now}),
            ("gone", 90, 1, {"unlisted_at": now}),
        ]:
            job = await jobs_repo.create_discovered_job(
                session, user_id, source="themuse", external_id=key, company="ExampleCo",
                title=key, location=None, url=f"https://example.com/{key}", jd_text="x" * 80,
                posted_at=None, identity_hash=f"h-{key}", repost_of=None,
            )
            job.best_track_id, job.best_fit = "tpm", fit
            job.discovered_at = now - timedelta(days=age)
            for attr, value in extra.items():
                setattr(job, attr, value)
        await session.commit()
    assert (await client.get("/api/v1/dashboard")).json()["new_fit_count"] == 1


async def test_needs_review_counts_unarchived_drafts_on_visible_jobs(
    client: httpx.AsyncClient, tailored_package: dict[str, Any]
) -> None:
    assert (await client.get("/api/v1/dashboard")).json()["needs_review_count"] == 1
    await client.post(f"/api/v1/packages/{tailored_package['id']}/archive")
    assert (await client.get("/api/v1/dashboard")).json()["needs_review_count"] == 0


async def test_saved_searches_carry_their_new_counts(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    created = (await client.post("/api/v1/searches", json={"query": "program manager"})).json()
    async with session_factory() as session:
        await jobs_repo.create_discovered_job(
            session, user_id, source="themuse", external_id="s1", company="ExampleCo",
            title="PM", location=None, url="https://example.com/s1", jd_text="x" * 80,
            posted_at=None, identity_hash="h-s1", repost_of=None,
            search_id=uuid.UUID(created["id"]),
        )
        await session.commit()
    body = (await client.get("/api/v1/dashboard")).json()
    assert body["saved_searches"] == [
        {"id": created["id"], "name": "program manager", "new_count": 1}
    ]


async def test_due_followups_are_today_or_earlier_soonest_first(
    client: httpx.AsyncClient, session_factory: async_sessionmaker[AsyncSession], user_id: uuid.UUID
) -> None:
    ids = []
    for key, offset in [("overdue", -3), ("today", 0), ("later", 5)]:
        job = (
            await client.post(
                "/api/v1/jobs",
                json={
                    "jd_text": f"Technical program manager {key}. " * 5,
                    "company": "ExampleCo",
                    "title": key,
                },
            )
        ).json()
        application = (
            await client.post("/api/v1/applications", json={"job_id": job["id"]})
        ).json()
        await client.patch(
            f"/api/v1/applications/{application['id']}",
            json={"follow_up_at": (datetime.now(UTC) + timedelta(days=offset)).isoformat()},
        )
        ids.append((key, application["id"]))
    due = (await client.get("/api/v1/dashboard")).json()["due_followups"]
    assert [d["application_id"] for d in due] == [ids[0][1], ids[1][1]]
    assert due[0]["job"]["title"] == "overdue"


async def test_the_dashboard_is_at_most_eight_selects(
    client: httpx.AsyncClient, imported_profile: None, select_counter: list[str]
) -> None:
    select_counter.clear()
    assert (await client.get("/api/v1/dashboard")).status_code == 200
    assert len(select_counter) <= 8, "\n".join(select_counter)
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_dashboard_api.py`. Expected: `assert 404 == 200` on `GET /api/v1/dashboard`.

- [ ] **Step 3: Write minimal implementation** —

`apps/api/src/rhapto/db/repositories/dashboard.py`:

```python
"""The five numbers the Dashboard reports, one aggregate query each.

Everything here is deliberately a single statement per answer. The dashboard is the first screen
a user sees on every visit; doing it with per-row follow-ups would make the landing page the
slowest thing in the product.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import (
    APPLIED_STATUSES,
    Answers,
    Application,
    Guardrail,
    Job,
    Package,
    ResumeBlock,
    ResumeDocumentRow,
    Track,
)

#: How long a job counts as "new" on the dashboard.
NEW_WINDOW_DAYS = 7

#: answers.yaml keys the checklist's two rows require, per spec §7.
CONTACT_KEYS = ("name", "email", "phone", "location", "links")
LOCATION_KEYS = ("location_home", "location_preferred", "remote_ok")


@dataclass(frozen=True)
class Checklist:
    resume_template: bool
    contact: bool
    tracks: bool
    blocks_verified: bool
    guardrails: bool
    location: bool
    verified_blocks: int
    total_blocks: int


async def new_fit_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Jobs found in the last week that clear their own track's threshold and are still live."""
    cutoff = datetime.now(UTC) - timedelta(days=NEW_WINDOW_DAYS)
    tracks = select(Track.track_id, Track.min_fit).where(Track.user_id == user_id).subquery()
    # A job whose track was renamed or deleted outer-joins to NULL; coalescing above any real
    # threshold (0-100) keeps the comparison a definite boolean instead of NULL, so such a job
    # counts as not-a-fit rather than silently counting as one.
    threshold = func.coalesce(tracks.c.min_fit, 101)
    count = await session.scalar(
        select(func.count(Job.id))
        .outerjoin(tracks, tracks.c.track_id == Job.best_track_id)
        .where(
            Job.user_id == user_id,
            Job.hidden_at.is_(None),
            Job.unlisted_at.is_(None),
            Job.discovered_at >= cutoff,
            Job.best_fit.is_not(None),
            Job.best_fit >= threshold,
        )
    )
    return int(count or 0)


async def needs_review_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Latest drafts waiting for a human, on jobs that are still in the flow."""
    latest = (
        select(Package.job_id, func.max(Package.version).label("version"))
        .where(Package.user_id == user_id)
        .group_by(Package.job_id)
        .subquery()
    )
    count = await session.scalar(
        select(func.count(Package.id))
        .join(latest, and_(Package.job_id == latest.c.job_id, Package.version == latest.c.version))
        .join(Job, Job.id == Package.job_id)
        .outerjoin(Application, Application.job_id == Package.job_id)
        .where(
            Package.user_id == user_id,
            Package.status == "draft",
            Package.archived_at.is_(None),
            Job.hidden_at.is_(None),
            Job.unlisted_at.is_(None),
            or_(Application.id.is_(None), Application.status.not_in(APPLIED_STATUSES)),
        )
    )
    return int(count or 0)


async def checklist(session: AsyncSession, user_id: uuid.UUID) -> Checklist:
    """The six profile-setup tests from spec §7, plus the verified-block tally.

    Two statements: one row of counts and existence flags, and one read of the answers JSON,
    which has to come back whole because the two answer rows test different keys.
    """
    row = (
        await session.execute(
            select(
                select(func.count(ResumeDocumentRow.id))
                .where(ResumeDocumentRow.user_id == user_id)
                .scalar_subquery(),
                select(func.count(Track.id)).where(Track.user_id == user_id).scalar_subquery(),
                select(func.count(Guardrail.id))
                .where(Guardrail.user_id == user_id, Guardrail.active.is_(True))
                .scalar_subquery(),
                select(func.count(ResumeBlock.id))
                .where(ResumeBlock.user_id == user_id)
                .scalar_subquery(),
                select(func.count(ResumeBlock.id))
                .where(ResumeBlock.user_id == user_id, ResumeBlock.verified.is_(True))
                .scalar_subquery(),
            )
        )
    ).one()
    documents, tracks, guardrails, total_blocks, verified_blocks = (int(v or 0) for v in row)
    answers_row = await session.scalar(select(Answers).where(Answers.user_id == user_id))
    answers = dict(answers_row.answers_json) if answers_row is not None else {}
    return Checklist(
        resume_template=documents > 0,
        contact=all((answers.get(k) or "").strip() for k in CONTACT_KEYS),
        tracks=tracks > 0,
        blocks_verified=verified_blocks > 0,
        guardrails=guardrails > 0,
        location=all((answers.get(k) or "").strip() for k in LOCATION_KEYS),
        verified_blocks=verified_blocks,
        total_blocks=total_blocks,
    )


async def due_followups(
    session: AsyncSession, user_id: uuid.UUID
) -> list[tuple[Application, Job]]:
    """Follow-ups dated today or earlier, soonest first, on applications still open."""
    now = datetime.now(UTC)
    rows = await session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.user_id == user_id,
            Application.follow_up_at.is_not(None),
            Application.follow_up_at <= now,
            Application.status != "closed",
        )
        .order_by(Application.follow_up_at, Application.id)
    )
    return [(application, job) for application, job in rows.all()]
```

`api/schemas.py` — append:

```python
class ChecklistOut(BaseModel):
    """Six setup tests plus the verified-block tally, rendered as "18 of 23 verified"."""

    resume_template: bool
    contact: bool
    tracks: bool
    blocks_verified: bool
    guardrails: bool
    location: bool
    verified_blocks: int
    total_blocks: int


class SavedSearchCountOut(BaseModel):
    id: uuid.UUID
    name: str
    new_count: int


class FollowUpOut(BaseModel):
    application_id: uuid.UUID
    job: JobRef
    status: str
    follow_up_at: datetime


class DashboardOut(BaseModel):
    new_fit_count: int
    needs_review_count: int
    checklist: ChecklistOut
    saved_searches: list[SavedSearchCountOut]
    due_followups: list[FollowUpOut]
```

`apps/api/src/rhapto/api/routers/dashboard.py`:

```python
"""Everything the Dashboard shows, in one call.

Five reads, no N+1: `tests/api/test_dashboard_api.py` asserts the whole request stays inside
eight SELECTs, so this endpoint cannot quietly become a loop.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.api.deps import current_user, get_session
from rhapto.api.schemas import (
    ChecklistOut,
    DashboardOut,
    FollowUpOut,
    JobRef,
    SavedSearchCountOut,
)
from rhapto.db.repositories import dashboard as repo
from rhapto.db.repositories import searches as searches_repo

router = APIRouter()

UserDep = Annotated[uuid.UUID, Depends(current_user)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(user_id: UserDep, session: SessionDep) -> DashboardOut:
    checklist = await repo.checklist(session, user_id)
    counts = await searches_repo.new_counts(session, user_id)
    searches = await searches_repo.list_searches(session, user_id)
    followups = await repo.due_followups(session, user_id)
    return DashboardOut(
        new_fit_count=await repo.new_fit_count(session, user_id),
        needs_review_count=await repo.needs_review_count(session, user_id),
        checklist=ChecklistOut(
            resume_template=checklist.resume_template,
            contact=checklist.contact,
            tracks=checklist.tracks,
            blocks_verified=checklist.blocks_verified,
            guardrails=checklist.guardrails,
            location=checklist.location,
            verified_blocks=checklist.verified_blocks,
            total_blocks=checklist.total_blocks,
        ),
        saved_searches=[
            SavedSearchCountOut(id=s.id, name=s.name, new_count=counts.get(s.id, 0))
            for s in searches
        ],
        due_followups=[
            FollowUpOut(
                application_id=application.id,
                job=JobRef(id=job.id, company=job.company, title=job.title),
                status=application.status,
                follow_up_at=follow_up,
            )
            for application, job in followups
            # `due_followups` only returns rows with a date, but mypy cannot see that.
            if (follow_up := application.follow_up_at) is not None
        ],
    )
```

`api/app.py` — import the `dashboard` router and mount it: `app.include_router(dashboard.router, prefix=API_PREFIX, tags=["dashboard"])`.

Then from the repo root: `bash scripts/codegen.sh`.

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/api/test_dashboard_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`. Finally, confirm the whole stack still starts with every migration applied: `docker compose build api worker && docker compose up -d && docker compose logs --tail 20 api`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(api): one dashboard call for where you stand

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

### Task 17: `RHAPTO_LLM_PROVIDER=fake` — a deterministic provider for the e2e stack

**Files:**
- Create: `docker-compose.e2e.yml`, `apps/api/tests/unit/test_fake_provider.py`, `apps/api/tests/api/test_fake_provider_api.py`
- Modify: `apps/api/src/rhapto/engine/providers/fake.py` (append `DeterministicFakeProvider`), `apps/api/src/rhapto/engine/providers/registry.py` (add `ENV_ONLY_PROVIDERS`, `provider_info`, extend `model_for` and `build_llm`), `apps/api/src/rhapto/services/llm.py` (`env_llm_config`, append `warn_if_fake_llm`), `apps/api/src/rhapto/api/app.py` (lifespan), `apps/api/src/rhapto/worker/main.py` (`on_startup`), `README.md` (one paragraph under the market-wide search section)
- Test: the two new test modules

**Interfaces:**

Consumes: `LLMProvider`, `StructuredResult`, `SystemBlock`, `Message`, `TokenUsage`, `MalformedOutputError` (existing); `build_system_blocks`' `<blocks>` payload and `build_user_message`' `<selected_block_ids>` payload (existing, `engine/compose.py`); `profile.example` blocks via the `imported_profile` fixture.

Produces:
- `engine/providers/fake.py`: `FAKE_MODEL = "fake-1"`; `class DeterministicFakeProvider` with `__init__(self, model: str = FAKE_MODEL)` and the `LLMProvider` `complete_structured` signature.
- `engine/providers/registry.py`: `FAKE_PROVIDER_ID = "fake"`; `ENV_ONLY_PROVIDERS: dict[str, ProviderInfo]`; `def provider_info(provider: str) -> ProviderInfo | None`. `PROVIDERS` keeps exactly the three real providers, so `provider_list()` and the Settings router's `known_provider()` are unchanged and can never offer or accept `fake`.
- `services/llm.py`: `FAKE_PROVIDER_WARNING: str`; `def warn_if_fake_llm(settings: Settings) -> bool` (True when it warned).
- `docker-compose.e2e.yml`: an override layer setting `RHAPTO_LLM_PROVIDER: fake` on `api` and `worker`.

Why an override file rather than `.env.e2e`: `docker-compose.yml` gives both services `env_file: .env` plus an `environment:` block. `--env-file` **replaces** the whole file, so an `.env.e2e` would have to duplicate `RHAPTO_API_TOKEN`, `RHAPTO_SECRET_KEY` and anything else the operator keeps there, and drift from `.env` the first time one of them changes. A `-f docker-compose.yml -f docker-compose.e2e.yml` override adds one variable on top of whatever `.env` already says, is committed (unlike `.env`, which is gitignored), and is self-documenting in the repo.

- [ ] **Step 1: Write the failing test** — create `apps/api/tests/unit/test_fake_provider.py`:

```python
from __future__ import annotations

import json

import pytest

from rhapto.config import Settings
from rhapto.engine.compose import ComposeOutput
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.providers.fake import FAKE_MODEL, DeterministicFakeProvider
from rhapto.engine.providers.llm import Message, SystemBlock
from rhapto.engine.providers.registry import (
    PROVIDERS,
    build_llm,
    model_for,
    provider_info,
)
from rhapto.engine.tune import TuneOutput
from rhapto.models.jd_extract import JDExtract
from rhapto.profile.loader import load_profile
from rhapto.services.llm import env_llm_config, warn_if_fake_llm

JD = (
    "Technical Program Manager, Data Platform\n"
    "You will run cross functional programs for the data platform team, manage dependencies "
    "across engineering, and report on delivery risk to leadership."
)


def _settings(provider: str = "fake", **kwargs: object) -> Settings:
    return Settings(_env_file=None, rhapto_llm_provider=provider, **kwargs)  # type: ignore[arg-type]


def test_fake_is_never_in_the_settings_picker() -> None:
    assert "fake" not in PROVIDERS
    assert provider_info("fake") is not None
    assert provider_info("nope") is None


def test_the_default_provider_is_still_anthropic() -> None:
    assert Settings(_env_file=None).rhapto_llm_provider == "anthropic"
    # Without a key, the default deployment resolves to nothing -- never to the fake.
    assert env_llm_config(Settings(_env_file=None)) is None


def test_env_resolution_picks_the_fake_up_with_no_api_key() -> None:
    config = env_llm_config(_settings())
    assert config is not None
    assert config.provider == "fake" and config.model == FAKE_MODEL
    assert build_llm(config.provider, config.model, config.api_key).__class__ is (
        DeterministicFakeProvider
    )
    assert model_for("fake", "") == FAKE_MODEL
    # A model id left over from another provider does not follow you into the fake.
    assert model_for("fake", "claude-sonnet-5") == FAKE_MODEL


def test_it_warns_loudly_only_when_active(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert warn_if_fake_llm(_settings()) is True
    assert "RHAPTO_LLM_PROVIDER=fake" in caplog.text
    assert "never" in caplog.text.lower()
    caplog.clear()
    with caplog.at_level("WARNING"):
        assert warn_if_fake_llm(_settings("anthropic")) is False
    assert caplog.text == ""


async def _compose(blocks_json: str, selected: list[str]) -> ComposeOutput:
    provider = DeterministicFakeProvider()
    result = await provider.complete_structured(
        system=[SystemBlock(text=f"rules\n\n<blocks>\n{blocks_json}\n</blocks>", cache=True)],
        messages=[
            Message(
                role="user",
                content=f"<selected_block_ids>\n{json.dumps(selected)}\n</selected_block_ids>",
            )
        ],
        output_schema=ComposeOutput,
    )
    return result.value


async def test_it_extracts_a_title_and_keywords_from_the_jd() -> None:
    provider = DeterministicFakeProvider()
    result = await provider.complete_structured(
        system=[SystemBlock(text="rules")],
        messages=[Message(role="user", content=JD)],
        output_schema=JDExtract,
    )
    extract = result.value
    assert extract.title == "Technical Program Manager, Data Platform"
    assert extract.company
    assert extract.keywords, "an empty extract makes the golden classification meaningless"
    # Deterministic: the same JD twice gives the same answer.
    again = await provider.complete_structured(
        system=[SystemBlock(text="rules")],
        messages=[Message(role="user", content=JD)],
        output_schema=JDExtract,
    )
    assert again.value.model_dump() == extract.model_dump()


async def test_compose_cites_only_selected_blocks_and_copies_them_verbatim(
    demo_profile_dir: object,
) -> None:
    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    selected = [b["id"] for b in blocks]
    output = await _compose(json.dumps(blocks), selected)
    cited = {e.source_block_id for s in output.sections for e in s.entries}
    assert cited and cited <= set(selected)
    by_id = {b["id"]: b for b in blocks}
    for section in output.sections:
        for entry in section.entries:
            source = by_id[entry.source_block_id]
            assert entry.org == source.get("org")
            assert entry.role == source.get("role")
            assert entry.period == source.get("period")
            for bullet in entry.bullets:
                assert source["content"] in bullet.text
                assert bullet.source_block_id == entry.source_block_id
    assert output.cover_note and output.change_log


async def test_a_block_outside_the_selection_is_never_cited(demo_profile_dir: object) -> None:
    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    selected = [blocks[0]["id"]]
    output = await _compose(json.dumps(blocks), selected)
    cited = {e.source_block_id for s in output.sections for e in s.entries}
    assert cited == set(selected)


async def test_the_composed_resume_passes_every_guardrail(demo_profile_dir: object) -> None:
    from rhapto.engine.compose import assemble_resume

    profile = load_profile(demo_profile_dir)  # type: ignore[arg-type]
    blocks = [b.model_dump(mode="json", exclude_none=True) for b in profile.blocks]
    selected = [b["id"] for b in blocks]
    output = await _compose(json.dumps(blocks), selected)
    resume = assemble_resume(output, profile)
    extract = JDExtract(company="ExampleCo", title="Technical Program Manager")
    report = run_guardrails(resume, profile, selected, extract, cover_note=output.cover_note)
    assert report.passed, [v.model_dump() for v in report.violations]


async def test_tune_mode_proposes_no_edits() -> None:
    provider = DeterministicFakeProvider()
    result = await provider.complete_structured(
        system=[SystemBlock(text="rules")],
        messages=[Message(role="user", content="<document>\np1: hello\n</document>")],
        output_schema=TuneOutput,
    )
    # Zero edits is the only rewrite of someone's own document that cannot invent anything.
    assert result.value.edits == []
    assert result.value.cover_note and result.value.change_log


async def test_an_unsupported_schema_says_so() -> None:
    from pydantic import BaseModel

    from rhapto.engine.providers.llm import MalformedOutputError

    class Surprise(BaseModel):
        whatever: int

    with pytest.raises(MalformedOutputError, match="Surprise"):
        await DeterministicFakeProvider().complete_structured(
            system=[], messages=[], output_schema=Surprise
        )
```

and `apps/api/tests/api/test_fake_provider_api.py`:

```python
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from rhapto.config import Settings
from rhapto.services.llm import clear_llm_cache, resolve_llm

TOKEN = "test-token"


@pytest.fixture(autouse=True)
def _clear_adapter_cache() -> None:
    clear_llm_cache()


@pytest.fixture
def api_settings(tmp_path: Path) -> Settings:
    """The e2e stack's environment: the fake provider and no vendor key anywhere."""
    return Settings(
        _env_file=None,
        rhapto_llm_provider="fake",
        anthropic_api_key="",
        rhapto_api_token=TOKEN,
        rhapto_user_email="test@example.com",
        rhapto_packages_dir=tmp_path / "packages",
        rhapto_soffice_binary="soffice-not-installed",
    )


@pytest.fixture
def llm_resolver():  # type: ignore[no-untyped-def]
    """The real resolver, so the run goes through env -> registry -> adapter for real.

    The default fixture injects a scripted double, which would prove nothing about whether
    RHAPTO_LLM_PROVIDER=fake actually resolves.
    """
    return resolve_llm


async def test_me_reports_the_stack_as_configured(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/me")).json()["llm_configured"] is True


async def test_the_fake_is_not_offered_in_settings(client: httpx.AsyncClient) -> None:
    body = (await client.get("/api/v1/settings/llm")).json()
    assert "fake" not in [p["id"] for p in body["providers"]]
    # Nor can it be saved: it is an environment switch for the e2e stack, not a user choice.
    rejected = await client.put(
        "/api/v1/settings/llm", json={"provider": "fake", "model": "fake-1"}
    )
    assert rejected.status_code == 422


async def test_a_whole_tailor_run_produces_a_clean_package(
    client: httpx.AsyncClient, imported_profile: None
) -> None:
    job = (
        await client.post(
            "/api/v1/jobs",
            json={
                "jd_text": (
                    "Technical Program Manager, Data Platform\n"
                    "Run cross functional programs for the data platform team and report on "
                    "delivery risk to leadership. " * 3
                ),
                "company": "ExampleCo",
                "title": "Technical Program Manager",
            },
        )
    ).json()
    task = await client.post(f"/api/v1/jobs/{job['id']}/tailor", json={})
    assert task.status_code in (200, 202), task.text
    packages = (await client.get(f"/api/v1/jobs/{job['id']}/packages")).json()
    assert packages, "the inline enqueuer should have produced a package"
    package = packages[-1]
    assert package["status"] == "draft", package["guardrail_report"]
    assert package["guardrail_report"]["passed"] is True
    assert package["resume"]["sections"], "an empty resume is not a usable e2e fixture"
    block_ids = {
        b["source_block_id"]
        for section in package["resume"]["sections"]
        for entry in section["entries"]
        for b in entry["bullets"]
    }
    assert block_ids, "every bullet must still cite a block"
```

- [ ] **Step 2: Run test to verify it fails** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_fake_provider.py tests/api/test_fake_provider_api.py`. Expected: `ImportError: cannot import name 'DeterministicFakeProvider' from 'rhapto.engine.providers.fake'` (collection error in both modules).

- [ ] **Step 3: Write minimal implementation** —

`engine/providers/fake.py` — append (the module already imports `re`, `json` is new):

```python
FAKE_MODEL = "fake-1"

_BLOCKS_RE = re.compile(r"<blocks>\s*(?P<body>.*?)\s*</blocks>", re.DOTALL)
_SELECTED_RE = re.compile(
    r"<selected_block_ids>\s*(?P<body>.*?)\s*</selected_block_ids>", re.DOTALL
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z+#.-]{3,}")
_DIGIT_RE = re.compile(r"\d")

#: Block type -> the section it belongs in, and that section's title.
_SECTIONS: dict[str, tuple[str, str]] = {
    "role": ("experience", "Experience"),
    "achievement": ("experience", "Experience"),
    "project": ("projects", "Projects"),
    "skill": ("skills", "Skills"),
    "credential": ("credentials", "Credentials"),
}

_STOPWORDS = frozenset(
    {
        "will", "with", "your", "you", "this", "that", "them", "they", "have", "from",
        "about", "their", "while", "into", "team", "work", "role", "well", "also",
        "across", "using", "must", "should", "would", "which", "were", "been", "when",
    }
)

FAKE_COMPANY = "Example Company"


class DeterministicFakeProvider:
    """An `LLMProvider` that answers from the prompt instead of from a model.

    It exists so the Docker Compose stack and the Playwright specs can run the whole
    Find -> Tailor -> Review -> Apply flow with no vendor key, no network and no bill, and get the
    *same* package every time. It is not a mock of a good model: it is the most conservative
    answer that satisfies every guardrail.

    * **Compose** copies each selected block's `content` into one bullet, verbatim, and copies the
      block's `org`/`role`/`period` onto the entry. That is provenance, entities and dates clean by
      construction, and it cannot invent a metric because it never writes a word of its own into a
      bullet. An unverified block whose content contains a digit is skipped outright rather than
      risking the verified-metrics rule.
    * **Tune** proposes no edits at all. Zero edits is the only rewrite of a human's own document
      that is guaranteed not to invent anything.
    * The cover note is deliberately bland: no company name, no numbers, nothing for a guardrail
      to catch.

    Selected by `RHAPTO_LLM_PROVIDER=fake`; never a default, and never offered in Settings.
    """

    def __init__(self, model: str = FAKE_MODEL) -> None:
        self.model = model
        self.calls: list[FakeCall] = []

    async def complete_structured(
        self,
        *,
        system: list[SystemBlock],
        messages: list[Message],
        output_schema: type[T],
        max_tokens: int = 4096,
    ) -> StructuredResult[T]:
        self.calls.append(
            FakeCall(system=list(system), messages=list(messages), output_schema=output_schema)
        )
        system_text = "\n\n".join(block.text for block in system)
        user_text = "\n\n".join(m.content for m in messages)
        name = output_schema.__name__
        if name == "JDExtract":
            payload: dict[str, Any] = self._extract(user_text)
        elif name == "ComposeOutput":
            payload = self._compose(system_text, user_text)
        elif name == "TuneOutput":
            payload = self._tune()
        elif name == "Ping":
            payload = {"ok": True}
        else:
            raise MalformedOutputError(
                f"DeterministicFakeProvider has no answer for {name}; "
                "teach it one in engine/providers/fake.py"
            )
        try:
            value = output_schema.model_validate(payload)
        except ValidationError as exc:
            raise MalformedOutputError(
                f"fake {name} did not match the schema: {exc.error_count()}"
            ) from exc
        return StructuredResult(value=value, usage=TokenUsage(input_tokens=0, output_tokens=0))

    def _extract(self, jd_text: str) -> dict[str, Any]:
        lines = [line.strip() for line in jd_text.splitlines() if line.strip()]
        title = lines[0][:200] if lines else "Unspecified Role"
        counts: dict[str, int] = {}
        for word in _WORD_RE.findall(jd_text.lower()):
            if word not in _STOPWORDS:
                counts[word] = counts.get(word, 0) + 1
        # Sorted by count then alphabetically, so the same JD always yields the same list.
        ranked = sorted(counts, key=lambda w: (-counts[w], w))[:8]
        return {
            "company": FAKE_COMPANY,
            "title": title,
            "location_policy": "unspecified",
            "seniority": "unspecified",
            "must_have": ranked[:4],
            "nice_to_have": [],
            "keywords": ranked,
            "likely_knockouts": [],
            "context_tags": [],
        }

    def _blocks(self, system_text: str, user_text: str) -> list[dict[str, Any]]:
        """The selected blocks, in the order the selector chose them."""
        blocks_match = _BLOCKS_RE.search(system_text)
        selected_match = _SELECTED_RE.search(user_text)
        if blocks_match is None or selected_match is None:
            return []
        try:
            blocks = json.loads(blocks_match.group("body"))
            selected = json.loads(selected_match.group("body"))
        except ValueError:
            return []
        by_id = {
            str(b["id"]): b for b in blocks if isinstance(b, dict) and isinstance(b.get("id"), str)
        }
        return [by_id[i] for i in selected if isinstance(i, str) and i in by_id]

    def _compose(self, system_text: str, user_text: str) -> dict[str, Any]:
        sections: dict[str, dict[str, Any]] = {}
        for block in self._blocks(system_text, user_text):
            content = str(block.get("content") or "").strip()
            if not content:
                continue
            # Verified-metrics: a number may only appear if the block carrying it is verified.
            if not block.get("verified") and _DIGIT_RE.search(content):
                continue
            kind, title = _SECTIONS.get(str(block.get("type")), ("experience", "Experience"))
            attribution = str(block.get("attribution") or "").strip()
            text = content if not attribution or attribution in content else f"{content} ({attribution})"
            section = sections.setdefault(kind, {"title": title, "kind": kind, "entries": []})
            section["entries"].append(
                {
                    "source_block_id": block["id"],
                    "org": block.get("org"),
                    "role": block.get("role"),
                    "period": block.get("period"),
                    "bullets": [{"text": text, "source_block_id": block["id"]}],
                }
            )
        ordered = [sections[k] for k in ("experience", "projects", "skills", "credentials") if k in sections]
        return {
            "summary": [],
            "sections": ordered,
            "cover_note": (
                "Thank you for considering my application. I would welcome the chance to discuss "
                "how my background fits this role."
            ),
            "change_log": (
                "Generated by the deterministic fake provider: every bullet is its source block's "
                "content, unchanged."
            ),
            "answers": [],
        }

    def _tune(self) -> dict[str, Any]:
        return {
            "edits": [],
            "cover_note": (
                "Thank you for considering my application. I would welcome the chance to discuss "
                "how my background fits this role."
            ),
            "change_log": "Generated by the deterministic fake provider: no edits proposed.",
            "answers": [],
        }
```

with `import json` and `from typing import Any` already present, and `MalformedOutputError`, `ValidationError` already imported at the top of the module.

`engine/providers/registry.py` — add the env-only tier and route the two lookups through it:

```python
from rhapto.engine.providers.fake import FAKE_MODEL, DeterministicFakeProvider

FAKE_PROVIDER_ID = "fake"

#: Providers that exist but are never offered in Settings and can never be saved by a user.
#: `env_key` is RHAPTO_LLM_PROVIDER itself: asking for the fake *is* the credential, which is why
#: the e2e stack needs no key at all. Kept out of PROVIDERS so `provider_list()` and the Settings
#: router's `known_provider()` stay exactly as strict as they were.
ENV_ONLY_PROVIDERS: dict[str, ProviderInfo] = {
    FAKE_PROVIDER_ID: ProviderInfo(
        id=FAKE_PROVIDER_ID,
        label="Deterministic fake (testing only)",
        models=(FAKE_MODEL,),
        default=FAKE_MODEL,
        env_key="RHAPTO_LLM_PROVIDER",
    )
}


def provider_info(provider: str) -> ProviderInfo | None:
    """Any provider this build can actually construct, selectable or not."""
    return PROVIDERS.get(provider) or ENV_ONLY_PROVIDERS.get(provider)
```

`_MODEL_OWNER` keeps covering only `PROVIDERS` (so `model_for("fake", "claude-sonnet-5")` sees the id owned by anthropic and falls back to `FAKE_MODEL`), and the two functions consult `provider_info`:

```python
def model_for(provider: str, model: str) -> str:
    info = provider_info(provider)
    ...  # body otherwise unchanged


def build_llm(provider: str, model: str, api_key: str) -> LLMProvider:
    if provider == FAKE_PROVIDER_ID:
        return DeterministicFakeProvider(model=model or FAKE_MODEL)
    if provider not in PROVIDERS:
        raise EngineError(f"unknown provider {provider!r}")
    ...  # body otherwise unchanged
```

`services/llm.py` — `env_llm_config` swaps its one lookup and gains the warning helper:

```python
def env_llm_config(settings: Settings) -> LlmConfig | None:
    info = provider_info(settings.rhapto_llm_provider)
    ...  # body otherwise unchanged
```

```python
FAKE_PROVIDER_WARNING = (
    "RHAPTO_LLM_PROVIDER=fake: every resume on this deployment is written by the deterministic "
    "fake provider, not by a language model. Bullets are copied verbatim from your blocks and no "
    "tailoring happens. This is for end-to-end tests and demos and must never be set in a "
    "deployment anyone relies on."
)


def warn_if_fake_llm(settings: Settings) -> bool:
    """Say loudly, once per process start, that this deployment writes nothing real."""
    if settings.rhapto_llm_provider != FAKE_PROVIDER_ID:
        return False
    logger.warning("%s", FAKE_PROVIDER_WARNING)
    return True
```

with `import logging`, `logger = logging.getLogger("rhapto.llm")`, and `FAKE_PROVIDER_ID`, `provider_info` added to the registry import.

`api/app.py` — first line inside the lifespan, before the user bootstrap:

```python
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        warn_if_fake_llm(settings)
        async with state.session_factory() as session:
            ...
```

`worker/main.py` — first line of `on_startup`, after `settings = get_settings()`:

```python
    warn_if_fake_llm(settings)
```

`docker-compose.e2e.yml`:

```yaml
# End-to-end / demo override. Layer it on top of the real file:
#
#   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
#
# It adds exactly one variable, so everything else (DATABASE_URL, RHAPTO_API_TOKEN and the rest
# of your .env) is untouched -- which is why this is an override layer and not an --env-file.
# With it, tailoring runs on the deterministic fake provider: no vendor key, no network, no bill,
# and the same package every run. Never use it for a deployment you rely on; both the api and the
# worker log a warning at startup while it is active.
services:
  api:
    environment:
      RHAPTO_LLM_PROVIDER: fake
  worker:
    environment:
      RHAPTO_LLM_PROVIDER: fake
```

`README.md` — append to the "Find jobs across the whole market" section:

````markdown
### Running the stack without an API key

For a demo or an end-to-end test run, `docker-compose.e2e.yml` switches the API and worker to a
deterministic fake provider:

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
```

Tailoring then needs no vendor key and no network: every bullet is copied verbatim from your own
blocks, so the package is guardrail-clean and identical on every run — and completely untailored.
Both services log a warning at startup while it is active. Never set `RHAPTO_LLM_PROVIDER=fake`
on a deployment you rely on.
````

- [ ] **Step 4: Run tests to verify they pass** — `cd apps/api && uv run pytest -q -p no:cacheprovider tests/unit/test_fake_provider.py tests/api/test_fake_provider_api.py tests/unit/test_resolve_llm.py tests/unit/test_provider_registry.py tests/api/test_llm_settings_api.py`, then `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py`, `uv run pytest -q -p no:cacheprovider tests/api tests/db`. Then prove the override end to end, with no key in the environment:

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml build api worker
docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
docker compose logs api worker | grep -i "RHAPTO_LLM_PROVIDER=fake"   # the warning must be there
export TOKEN="$(grep -E '^RHAPTO_API_TOKEN=' .env | cut -d= -f2-)"
JOB=$(curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"jd_text":"Technical Program Manager, Data Platform. Run cross functional programs for the data platform team and report on delivery risk to leadership.","company":"ExampleCo","title":"Technical Program Manager"}' \
  http://localhost:8000/api/v1/jobs | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -sS -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{}' \
  "http://localhost:8000/api/v1/jobs/$JOB/tailor"
curl -sS -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/v1/jobs/$JOB/packages" \
  | python -c 'import json,sys; p=json.load(sys.stdin)[-1]; print(p["status"], p["guardrail_report"]["passed"])'
```

The last line must print `draft True`.

- [ ] **Step 5: Commit** —

```bash
git add -A && git commit -m "$(cat <<'EOF'
feat(providers): RHAPTO_LLM_PROVIDER=fake for the end-to-end stack

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_018nj9MER4aGXPAfYzbAo6oP
EOF
)"
```

---

## Self-review

### Spec coverage

| Spec § | What it asks for | Where it lands |
|---|---|---|
| portal §4 (states) | `hidden_at`, `unlisted_at`, `archived_at`, `closed_reason`, `follow_up_at` | T9 (columns), T10 (endpoints) |
| portal §4 (Job: Tailor / Not interested) | `POST /jobs/{id}/hide`, `/unhide`, `hidden` filter for "Show hidden" | T10, T11 |
| portal §4 (Resume: Skip archives and hides) | `POST /packages/{id}/archive`, `GET /packages?archived=` | T10 |
| portal §4 (Pipeline: Closed with reason, Follow-up) | `PATCH /applications/{id}` + DB check constraint | T9, T10 |
| portal §4 (closed postings, two polls) | `jobs.miss_count`, `reconcile_listing`, `UNLISTED_AFTER = 2` | T9, T12 |
| portal §4 (reposts) | unchanged: `repost_of` already exists; live search deliberately does not create reposts | T13 |
| portal §5 (fields, roles, keywords, categories) | `packages/schemas/taxonomy.{json,yaml}`, `services/taxonomy.py` | T7 |
| portal §5 (`min_fit` 60, track from a role) | `tracks.field` / `tracks.role`, taxonomy `min_fit` documented in the data file header | T8 (UI creates the track in portal-ui) |
| portal §5 (`GET /api/v1/taxonomy`) | `api/routers/taxonomy.py` | T8 |
| portal §5 (suggested from your resume) | `GET /taxonomy/suggestions` over `entry_title` paragraphs | T8 |
| portal §5 (Muse/Adzuna take the field's category) | `SearchSpec.field` → `find_field(...).themuse_category` / `.adzuna_category` | T1 (field), T7 (wiring) |
| portal §6 (search form fields) | `LiveSearchIn(query, location, remote, field, posted_within, sources)` | T14 |
| portal §6 (`POST /search`, 8 s, cap 30, dedupe, enqueue, `per_source`) | `services/discovery/live.py` + `api/routers/search.py` | T13, T14 |
| portal §6 (client refetches `GET /jobs?ids=`) | `ids` parameter, ≤ 200 | T11 |
| portal §6 (saved searches, background cap 100) | `searches` table, `SEARCH_CAP = 100`, poller fan-out | T1, T2, T3 |
| portal §6 (`last_viewed_at`, "N new", `/viewed`) | `searches.last_viewed_at`, `new_counts`, `POST /searches/{id}/viewed` | T9, T15 |
| portal §7 (`GET /dashboard`, six checklist booleans, verified counts) | `db/repositories/dashboard.py`, `api/routers/dashboard.py` | T16 |
| portal §7 ("new" = 7 days) | `NEW_WINDOW_DAYS = 7` | T16 |
| portal §9 (data model changes) | 0006 (`search_id`), 0007 (`tracks.field/role`), 0008 (the rest) | T2, T8, T9 |
| portal §10 (API changes) | every route listed; `GET /jobs` gains `ids`, `hidden`, `search_id`, `posted_within`, `sources`, `field` (`sort` already existed) | T4, T8, T10, T11, T14, T15, T16 |
| portal §11 item 1 | the job-portal six plus live search, taxonomy, flow fields, dashboard, unlisted | all 16 tasks |
| job-portal §3 (sources, credentials) | five new sources, `source_credentials`, `/settings/sources` | T1, T2, T4 |
| job-portal §4 (saved searches, derivation) | `searches` table, `derive_searches`, CRUD | T2, T3, T4 |
| job-portal §5 (auto-discovered boards) | `board_from_url`, watchlist insert with `discovered` | T3 |
| job-portal §6 (applying) | unchanged by design; no task | — |
| job-portal §7 (UI) | Searches tab, Job sources, source chips | superseded — `docs/superpowers/plans/2026-09-14-portal-ui.md` (Settings additions) |
| job-portal §8 (testing) | per-source unit tests, no network anywhere | T1–T4 |
| portal §14 (e2e run against the stack with the API's fake LLM provider) | `RHAPTO_LLM_PROVIDER=fake` + `docker-compose.e2e.yml` | T17 |
| portal §3, §8, §12–13, §15 (UI, tokens, screenshots, docs) | out of scope: portal-ui plan | — |

### Type consistency

- `SearchSpec(keywords: tuple[str, ...], location, remote, name, field, posted_within)` is constructed in T3 (poller), T4 (`/settings/sources/{s}/test`), T13 (tests) and T14 (router) with the same keyword names; every source signature is `fetch_search(http, spec, credentials) -> list[Posting]`.
- `Posting.salary_text` (T1) → `create_discovered_job(..., salary_text=)` (T9) → `Job.salary_text` (T9) → `JobOut.salary_text` (declared T4, populated T10). Declared in T4 rather than T10 so the generated TypeScript changes once.
- `jobs_repo.list_jobs` returns `list[tuple[Job, str | None]]` from T4 onwards; `_outs` takes that shape in T4, T11 and T14.
- `LiveResult.per_source: dict[str, SourceOutcome]` (T13) maps 1:1 to `LiveSearchOut.per_source: dict[str, PerSourceOut]` (T14) — same three fields, no renames.
- `get_credentials(session, fernet, user_id, source)` has the `Fernet` in the same position in T2, T3, T4 and T14; the only callers that build one are `services.secrets.fernet_for(settings)` in the API and the worker.
- `POSTED_WITHIN_DAYS` lives in `db/repositories/jobs.py` (T11) and is imported by `services/discovery/live.py` (T13); the reverse direction is impossible under import-linter, so do not "tidy" it into `services`.
- `RunResult` gains `search_id` in T3 and `unlisted` in T12; both have defaults, so T3's tests keep constructing it positionally with five arguments.
- `SearchIn` is rewritten once, in T15. T4's tests send `{name, keywords}` and still validate under the new model; T5's web component sends the same shape.

### Executor-judgement items (including the deliberate deviations)

1. **`recommended=true` on `GET /jobs` is an addition to spec §10.** §3.1 defines the Recommended roles card but §10 never gives the API a way to express it. Filtering client-side would mean fetching every job and joining packages and applications in the browser. If the reviewer objects, the fallback is three parameters (`has_package=false`, `has_application=false`) rather than a single flag — but then the Dashboard makes the same query in two places.
2. **A live-search identity match returns the existing job instead of inserting a repost.** This is the opposite of the poller's rule and is stated in `live.py`'s module docstring. The poller records history; the search box answers a question. If reposts must also surface live, the change is to return both rows and let the UI group them by `repost_of`.
3. **"N new" and the dashboard's saved-search counts exclude hidden and unlisted jobs.** §6 says only "jobs with `search_id` and `discovered_at > last_viewed_at`". Counting a job the user already dismissed would make the badge un-clearable, so the two exclusions are added. Say so in the UI copy if it ever matters.
4. **`closed_reason` is enforced by a DB check constraint, and reopening an application clears it.** The spec only says the reason belongs to the closed state. The alternative — leaving a stale reason on a reopened application — makes the Pipeline's history lie.
5. **`reconcile_listing` is skipped when a fetch returns zero postings.** A source that silently returns an empty page would otherwise retire the user's whole queue in two polls. This costs one poll of latency in the genuine case where a board really did empty.
6. **Exact pagination and field names per vendor API.** The five source adapters are written from the vendor docs; verify each with one manual request against the live keyless endpoints (The Muse, Remotive) before trusting the mapping, and never in a test. Adzuna's `category` slug in particular may need the machine tag rather than the display label — check one response and adjust `taxonomy.yaml`'s `adzuna_category` values if so.
7. **The Muse and Adzuna category names in `taxonomy.yaml` are the plan's best reading of those vendors' published category lists.** They are data, not code: correcting one is a one-line edit to the YAML with no code change, and `tests/unit/test_taxonomy.py` only asserts that they are non-empty.
8. **`AppState.discovery_http`** is introduced in Task 4 so the API can reach sources on the request path (`/settings/sources/{s}/test`, then `POST /search`). Confirm the lifespan closes it and that every API test injects `FakeDiscoveryHttp` — a test that reaches the network is a bug, not a flake.
9. **The dashboard's ≤ 8 SELECT guard** counts every statement the request issues, including the user lookup FastAPI's dependency does. If a legitimate addition pushes it to nine, raise the number in one place and say why in the commit — do not delete the assertion.
10. **The fake provider is registered outside `PROVIDERS`.** Putting it in the main dict would have shown it in the Settings picker and let a user save it, so it lives in `ENV_ONLY_PROVIDERS` and `env_key` points at `RHAPTO_LLM_PROVIDER` itself — asking for the fake is the credential. If a future provider also needs to be env-only, that dict is the place; do not merge the two.
11. **The fake skips unverified blocks whose content contains a digit.** That is stricter than the verified-metrics guardrail needs (a digit is not always a metric), and it means a `profile.example` edit that adds a number to an unverified block silently shrinks the e2e resume. `test_the_composed_resume_passes_every_guardrail` is what catches the alternative — a fake that produces blocked packages — so keep it strict.
12. **`default_tailor_script()`** is assumed to exist in the tailor tests. If the LLM response sequence there is inline rather than a helper, lift it verbatim into `tests/helpers.py` as part of Task 10 Step 1; changing what it returns would break the golden tests.
