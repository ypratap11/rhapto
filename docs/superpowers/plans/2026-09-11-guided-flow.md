# Guided Flow and Navigation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the web app one linear Find → Tailor → Review → Apply flow: a step bar, a Next up panel that says which job to act on, Jobs tabs, a Packages page, a state-aware card button, and a sticky review action bar with candidate-named downloads.

**Architecture:** One new API endpoint (`GET /api/v1/packages`) and candidate-named `Content-Disposition` headers; on the web, a small `lib/flow.ts` state machine (`jobState`) shared by the Next up panel, the job card, and the Packages page, a `StepBar` in the shell driven by the existing jobs and new packages queries, and a `/packages` route. No scoring, discovery, or pipeline changes.

**Tech Stack:** FastAPI + SQLAlchemy (apps/api); Next 16, React 19, TanStack Query, shadcn base-nova on Base UI, vitest (apps/web).

**Spec:** `docs/superpowers/specs/2026-09-11-guided-flow-design.md`

## Global Constraints

- All stage 3 and 0.3 constraints apply: no personal data in tracked files (fixtures use fictional names such as `Maya Chen`, `ExampleCo`); nothing submits an application; the token goes only to the configured API URL; every API access through `apiClient()` except `download.ts` and `sse.ts`.
- Python checks before every commit (from `apps/api`): `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run pytest -q --deselect tests/unit/test_enqueue_arq.py`, `uv run lint-imports`. Never run two DB-backed suites at once (shared test database deadlocks).
- Web checks before every commit (from `apps/web`): `pnpm test`, `pnpm typecheck`, `pnpm lint` (one accepted warning in `TaskProgress.tsx`), `pnpm build`.
- Generated files never hand-edited: after any API change run `bash scripts/codegen.sh` from the repo root and commit `packages/schemas/openapi.json` and `apps/web/src/lib/api/schema.d.ts`.
- Toolchain facts: `Button` uses `render` not `asChild`; `AlertDialogAction` does not auto-close; `Select.onValueChange` may receive `string | null`; no synchronous setState in effects (`react-hooks/set-state-in-effect`); `Tabs` primitive exists in `components/ui/tabs.tsx`.
- Flow states (verbatim, used by every task): `jobState(job)` returns `"tailor"` when `latest_package` is null, `"review"` when a package exists and `application_status` is null or `"queued"` or `"discovered"`, `"applied"` when `application_status` is `"applied"`, `"screen"`, `"interview"`, `"offer"`, or `"closed"`. A running tailor task is component state (`"tailoring"`), not a server state.
- Download names (verbatim): `<Name>_Resume.pdf`, `<Name>_Resume.docx`, `<Name>_Package.zip`, where `<Name>` is the profile's `name` answer with every run of characters outside `[A-Za-z0-9]` replaced by `_`, trimmed of leading and trailing `_`; fallback `Resume` when the answer is missing or empty. Blocked packages keep the `X-Rhapto-Guardrails: blocked` header and the zip's `GUARDRAILS-BLOCKED.md`.
- Design: the accent colour only on primary actions (the state button on a card and in Next up, Mark applied); step bar and tabs use neutral styles; every control labelled.
- Commit messages end with the two attribution lines given in the session.

## File Structure

```
apps/api/src/rhapto/api/schemas.py                 + PackageListItem
apps/api/src/rhapto/api/routers/packages.py       + GET /packages, candidate-named downloads
apps/api/src/rhapto/db/repositories/packages.py   + list_packages(session, user_id, status, applied)
apps/api/src/rhapto/services/naming.py            NEW download_basename(name) 
apps/api/tests/api/test_packages_api.py           + list + filename tests
apps/api/tests/unit/test_naming.py                NEW
apps/web/src/lib/flow.ts                           NEW jobState, nextUp, FLOW_STEPS, stepForPath
apps/web/src/lib/skipped.ts                        NEW localStorage skip list (rhapto.skipped)
apps/web/src/lib/download.ts                       + resumeFilename
apps/web/src/lib/api/queries.ts                    + usePackageList, packageListKeys, invalidate hooks
apps/web/src/components/shell/Nav.tsx              items Jobs, Packages, Pipeline, Profile, Settings icon
apps/web/src/components/shell/StepBar.tsx          NEW
apps/web/src/components/shell/Shell.tsx            renders StepBar under the header
apps/web/src/components/queue/NextUp.tsx           NEW
apps/web/src/components/queue/JobActionButton.tsx  NEW state-aware primary button (wraps TailorButton)
apps/web/src/components/queue/JobCard.tsx          uses JobActionButton, drops the underlined link
apps/web/src/components/queue/FilterBar.tsx        tabs New / Tailored / Low fit instead of Fit / Low fit
apps/web/src/components/queue/JobList.tsx          applies the tab filter
apps/web/src/app/page.tsx                          NextUp + tabs; title "Jobs"
apps/web/src/app/packages/page.tsx                 NEW
apps/web/src/components/packages/PackageTable.tsx  NEW
apps/web/src/components/review/PackageActions.tsx  sticky bar: PDF, DOCX, zip, Regenerate, Mark applied, Open posting
apps/web/src/app/jobs/[jobId]/packages/[packageId]/page.tsx   blocked panel first, Next tailored job link
README.md                                          flow paragraph
```

---

### Task 1: API: package list endpoint and candidate-named downloads

**Files:**
- Create: `apps/api/src/rhapto/services/naming.py`, `apps/api/tests/unit/test_naming.py`
- Modify: `apps/api/src/rhapto/api/schemas.py`, `apps/api/src/rhapto/api/routers/packages.py`, `apps/api/src/rhapto/db/repositories/packages.py`, `apps/api/tests/api/test_packages_api.py`
- Regenerate: `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts`

**Interfaces:**
- Produces: `def download_basename(name: str | None) -> str` (naming rule above); `class PackageListItem(BaseModel): id: uuid.UUID; job_id: uuid.UUID; company: str | None; title: str | None; version: int; status: str; application_status: str | None; best_fit: int | None; best_track_id: str | None; created_at: datetime`; `GET /api/v1/packages?status=draft|blocked&applied=true|false -> list[PackageListItem]` newest first, only the latest version per job; download endpoints set `Content-Disposition: attachment; filename="<Name>_Package.zip"` / `<Name>_Resume.pdf` / `<Name>_Resume.docx`.

- [ ] **Step 1: Failing tests**

`apps/api/tests/unit/test_naming.py`:

```python
from rhapto.services.naming import download_basename


def test_download_basename_normalises_and_falls_back() -> None:
    assert download_basename("Maya Chen") == "Maya_Chen"
    assert download_basename("  Ana-María O'Neil  ") == "Ana_Mar_a_O_Neil"
    assert download_basename("") == "Resume"
    assert download_basename(None) == "Resume"
    assert download_basename("___") == "Resume"
```

Append to `apps/api/tests/api/test_packages_api.py` (it already has helpers that create a job and persist a package through the inline worker; reuse the same fixtures the existing download test uses):

```python
async def test_package_list_and_named_downloads(client: httpx.AsyncClient, imported_profile: None, fake_llm: ScriptableLLM) -> None:
    fake_llm.script(demo_extract(), _output())
    job = (await client.post("/api/v1/jobs", json={"jd_text": JD, "company": "ExampleCo", "title": "Data PM"})).json()
    task = (await client.post(f"/api/v1/jobs/{job['id']}/tailor", json={})).json()
    package_id = (await client.get(f"/api/v1/tasks/{task['id']}")).json()["result_ref"]

    listed = await client.get("/api/v1/packages")
    assert listed.status_code == 200
    rows = listed.json()
    assert [r["id"] for r in rows] == [package_id]
    assert rows[0]["company"] == "ExampleCo" and rows[0]["application_status"] is None and rows[0]["status"] == "draft"
    assert (await client.get("/api/v1/packages", params={"status": "blocked"})).json() == []
    assert (await client.get("/api/v1/packages", params={"applied": "true"})).json() == []

    zip_response = await client.get(f"/api/v1/packages/{package_id}/download")
    assert zip_response.headers["content-disposition"] == 'attachment; filename="Maya_Chen_Package.zip"'
    docx = await client.get(f"/api/v1/packages/{package_id}/files/resume.docx")
    assert 'filename="Maya_Chen_Resume.docx"' in docx.headers["content-disposition"]

    app_row = (await client.post("/api/v1/applications", json={"job_id": job["id"], "package_id": package_id})).json()
    await client.patch(f"/api/v1/applications/{app_row['id']}", json={"status": "applied"})
    assert [r["application_status"] for r in (await client.get("/api/v1/packages", params={"applied": "true"})).json()] == ["applied"]
    assert (await client.get("/api/v1/packages", params={"applied": "false"})).json() == []
```

`imported_profile` imports `profile.example`, whose `answers.name` is `Maya Chen`. If the existing test module names its fixtures differently (`_output`, `JD`, `ScriptableLLM`), use the module's own names.

- [ ] **Step 2: Run to verify failure**

Run from `apps/api`: `uv run pytest tests/unit/test_naming.py tests/api/test_packages_api.py -q` → FAIL.

- [ ] **Step 3: Implement**

`apps/api/src/rhapto/services/naming.py`:

```python
from __future__ import annotations

import re

FALLBACK = "Resume"


def download_basename(name: str | None) -> str:
    """Candidate name as a safe filename stem: runs of non-alphanumerics become `_`; empty -> Resume."""
    stem = re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_")
    return stem or FALLBACK
```

`db/repositories/packages.py` add:

```python
async def list_packages(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    status: str | None = None,
    applied: bool | None = None,
) -> list[tuple[Package, Job, Application | None]]:
    """Latest package per job, newest first, with its job and application (if any)."""
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
    if status:
        query = query.where(Package.status == status)
    if applied is True:
        query = query.where(Application.status.in_(("applied", "screen", "interview", "offer", "closed")))
    elif applied is False:
        query = query.where(or_(Application.id.is_(None), Application.status.in_(("queued", "discovered"))))
    return [(p, j, a) for p, j, a in (await session.execute(query)).all()]
```

`api/schemas.py` add `PackageListItem` as in Interfaces. `api/routers/packages.py` add (imports: `download_basename`, `get_answers`-style lookup — use `profile_repo.get_answers(session, user_id)` if it exists, otherwise `load_profile_from_db(session, user_id).answers`; keep it to one query):

```python
async def _basename(session: AsyncSession, user_id: uuid.UUID) -> str:
    answers = await profile_repo.get_answers(session, user_id)  # dict[str, str]
    return download_basename(answers.get("name"))


@router.get("/packages", response_model=list[PackageListItem])
async def list_packages(
    user_id: UserDep,
    session: SessionDep,
    status: Literal["draft", "blocked"] | None = Query(default=None),
    applied: bool | None = Query(default=None),
) -> list[PackageListItem]:
    rows = await package_repo.list_packages(session, user_id, status=status, applied=applied)
    return [
        PackageListItem(
            id=p.id, job_id=j.id, company=j.company, title=j.title, version=p.version, status=p.status,
            application_status=a.status if a else None, best_fit=j.best_fit, best_track_id=j.best_track_id,
            created_at=p.created_at,
        )
        for p, j, a in rows
    ]
```

Register the route before `/packages/{package_id}` so the literal path wins. In `download_package` set `filename = f"{await _basename(session, user_id)}_Package.zip"`; in `package_file` pass `filename=f"{stem}_Resume.{ext}"` where `ext` is `docx` or `pdf`. Confirm `profile_repo` exposes an answers getter (the profile router's `GET /profile/answers` uses one); reuse it.

- [ ] **Step 4: Run, regenerate, commit**

`uv run pytest tests/unit/test_naming.py tests/api/test_packages_api.py -q` → PASS; full Python check set; `bash scripts/codegen.sh` from the root.

```bash
git add apps/api/src/rhapto/services/naming.py apps/api/src/rhapto/api apps/api/src/rhapto/db/repositories/packages.py apps/api/tests packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts
git commit -m "feat(api): package list endpoint and candidate-named downloads"
```

---

### Task 2: Flow library, queries, navigation, and step bar

**Files:**
- Create: `apps/web/src/lib/flow.ts`, `flow.test.ts`, `apps/web/src/lib/skipped.ts`, `skipped.test.ts`, `apps/web/src/components/shell/StepBar.tsx`, `StepBar.test.tsx`
- Modify: `apps/web/src/lib/api/queries.ts`, `apps/web/src/lib/download.ts` (+ test), `apps/web/src/components/shell/Nav.tsx`, `Shell.tsx`

**Interfaces:**
- Consumes: `JobOut`, `PackageListItem` (regenerated types).
- Produces:
  - `flow.ts`: `export type JobState = "tailor" | "review" | "applied"`; `export function jobState(job: Pick<JobOut, "latest_package" | "application_status">): JobState`; `export const APPLIED_STATUSES = ["applied", "screen", "interview", "offer", "closed"] as const`; `export function nextUp(jobs: JobOut[], skipped: string[], limit = 5): JobOut[]` (state !== "applied", not skipped, `best_fit` not null, sorted by `best_fit` desc then `discovered_at` desc); `export const FLOW_STEPS = ["Find", "Tailor", "Review", "Apply"] as const`; `export function stepForPath(pathname: string, tailoring: boolean): 0 | 1 | 2 | 3` (`/packages/` under `/jobs/` → 2; `/pipeline` → 3; tailoring → 1; else 0); `export function flowPrompt(input: { needsReview: number; next: JobOut | null }): { text: string; href: string } | null` ("N packages ready to review" → `/packages?filter=review` when `needsReview > 0`; else "Next: tailor <company>, <title> (fit N)" → `/#job-<id>`; else null).
  - `skipped.ts`: `readSkipped(): string[]`, `skipJob(id: string): string[]`, `unskipAll(): void`, key `rhapto.skipped`, all wrapped in try/catch; dispatches a `rhapto-skipped` window event; `useSkipped(): string[]` via `useSyncExternalStore` (server snapshot `[]`).
  - `download.ts`: `export function resumeFilename(name: string | null | undefined, kind: "pdf" | "docx" | "zip"): string` (same rule as the API: `<Name>_Resume.pdf`, `<Name>_Resume.docx`, `<Name>_Package.zip`, fallback `Resume`).
  - `queries.ts`: `export type PackageListItem = components["schemas"]["PackageListItem"]`; `export type PackageListFilter = "all" | "review" | "blocked" | "applied"`; `packageListKeys.list(filter)`; `usePackageList(filter: PackageListFilter)` mapping `review → {applied: false, status: "draft"}`, `blocked → {status: "blocked"}`, `applied → {applied: true}`, `all → {}`; `invalidatePackageList(queryClient)`; and `invalidateApplications` plus `usePatchPackage`'s success handlers also invalidate the package list. `useAnswers()` already exists (profile) and provides the candidate name.
  - `Nav.tsx`: items `Jobs` (`/`, active for `/` and `/jobs/*`), `Packages` (`/packages`), `Pipeline`, `Profile`, and a Settings icon-only link with `aria-label="Settings"`.
  - `StepBar`: renders the four steps with the current one highlighted (`aria-current="step"`), and the prompt line from `flowPrompt` using `useJobs({search:"", track:null, bucket:"fit", sort:"fit"})` and `usePackageList("review")`; hidden on `/settings` and while the token gate is closed (the gate wraps children; place `StepBar` inside `TokenGate` so it never renders without a token).

- [ ] **Step 1: Failing tests**

`apps/web/src/lib/flow.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { flowPrompt, jobState, nextUp, stepForPath } from "./flow";
import type { JobOut } from "./api/queries";

const base = (over: Partial<JobOut>): JobOut => ({
  id: "j", source: "manual", company: "ExampleCo", title: "Data PM", location: null, url: null, jd_text: "x",
  extracted: null, discovered_at: "2026-09-01T00:00:00Z", latest_package: null, application_status: null,
  best_track_id: "data-pm", best_fit: 70, bucket: "fit", rescued: false, repost_of: null, posted_at: null, scores: [],
  ...over,
});

describe("flow", () => {
  it("derives the job state", () => {
    expect(jobState(base({}))).toBe("tailor");
    const pkg = { id: "p", version: 1, status: "draft", created_at: "2026-09-01T00:00:00Z" };
    expect(jobState(base({ latest_package: pkg }))).toBe("review");
    expect(jobState(base({ latest_package: pkg, application_status: "queued" }))).toBe("review");
    expect(jobState(base({ latest_package: pkg, application_status: "applied" }))).toBe("applied");
    expect(jobState(base({ latest_package: pkg, application_status: "interview" }))).toBe("applied");
  });
  it("ranks next up by fit, skipping applied, skipped and unscored jobs", () => {
    const jobs = [
      base({ id: "a", best_fit: 60 }),
      base({ id: "b", best_fit: 90 }),
      base({ id: "c", best_fit: 95, latest_package: { id: "p", version: 1, status: "draft", created_at: "" }, application_status: "applied" }),
      base({ id: "d", best_fit: null }),
      base({ id: "e", best_fit: 80 }),
    ];
    expect(nextUp(jobs, ["e"], 5).map((j) => j.id)).toEqual(["b", "a"]);
    expect(nextUp(jobs, [], 1).map((j) => j.id)).toEqual(["b"]);
  });
  it("maps paths to steps and builds the prompt", () => {
    expect(stepForPath("/", false)).toBe(0);
    expect(stepForPath("/", true)).toBe(1);
    expect(stepForPath("/jobs/j/packages/p", false)).toBe(2);
    expect(stepForPath("/pipeline", false)).toBe(3);
    expect(flowPrompt({ needsReview: 3, next: null })).toEqual({ text: "3 packages ready to review", href: "/packages?filter=review" });
    expect(flowPrompt({ needsReview: 0, next: base({ id: "z", best_fit: 72 }) })).toEqual({ text: "Next: tailor ExampleCo, Data PM (fit 72)", href: "/#job-z" });
    expect(flowPrompt({ needsReview: 0, next: null })).toBeNull();
  });
});
```

`apps/web/src/lib/skipped.test.ts`: `skipJob("a")` then `readSkipped()` equals `["a"]`, skipping twice does not duplicate, `unskipAll()` empties, and a thrown `localStorage` (mock `Storage.prototype.getItem` to throw) makes `readSkipped()` return `[]`.

`download.test.ts` (extend): `resumeFilename("Maya Chen", "pdf") === "Maya_Chen_Resume.pdf"`, `resumeFilename("", "zip") === "Resume_Package.zip"`, `resumeFilename("  Ana-María  ", "docx") === "Ana_Mar_a_Resume.docx"`.

`StepBar.test.tsx` (mock `next/navigation` `usePathname`, and `@/lib/api/queries` `useJobs`/`usePackageList`): on `/` with two review packages the bar marks Find current and shows "2 packages ready to review" linking to `/packages?filter=review`; on `/pipeline` Apply is current.

- [ ] **Step 2: Run to verify failure**: `pnpm test -- src/lib src/components/shell` → FAIL.

- [ ] **Step 3: Implement**

`lib/flow.ts`:

```ts
import type { JobOut } from "./api/queries";

export const APPLIED_STATUSES = ["applied", "screen", "interview", "offer", "closed"] as const;
export type JobState = "tailor" | "review" | "applied";
export const FLOW_STEPS = ["Find", "Tailor", "Review", "Apply"] as const;

export function jobState(job: Pick<JobOut, "latest_package" | "application_status">): JobState {
  if (job.application_status && (APPLIED_STATUSES as readonly string[]).includes(job.application_status)) return "applied";
  return job.latest_package ? "review" : "tailor";
}

export function nextUp(jobs: JobOut[], skipped: string[], limit = 5): JobOut[] {
  const skip = new Set(skipped);
  return jobs
    .filter((j) => j.best_fit !== null && !skip.has(j.id) && jobState(j) !== "applied")
    .sort((a, b) => (b.best_fit ?? 0) - (a.best_fit ?? 0) || b.discovered_at.localeCompare(a.discovered_at))
    .slice(0, limit);
}

export function stepForPath(pathname: string, tailoring: boolean): 0 | 1 | 2 | 3 {
  if (pathname.startsWith("/pipeline")) return 3;
  if (/^\/jobs\/[^/]+\/packages\//.test(pathname)) return 2;
  return tailoring ? 1 : 0;
}

export function flowPrompt(input: { needsReview: number; next: JobOut | null }): { text: string; href: string } | null {
  if (input.needsReview > 0) {
    const n = input.needsReview;
    return { text: `${n} package${n === 1 ? "" : "s"} ready to review`, href: "/packages?filter=review" };
  }
  if (input.next) {
    const j = input.next;
    return { text: `Next: tailor ${j.company ?? "Unknown company"}, ${j.title ?? "Untitled role"} (fit ${j.best_fit ?? 0})`, href: `/#job-${j.id}` };
  }
  return null;
}
```

`lib/skipped.ts`:

```ts
import { useSyncExternalStore } from "react";

const KEY = "rhapto.skipped";
const EVENT = "rhapto-skipped";
const EMPTY: string[] = [];

export function readSkipped(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed) ? parsed.filter((x): x is string => typeof x === "string") : [];
  } catch {
    return [];
  }
}

function write(ids: string[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(ids));
  } catch {
    // storage unavailable: the skip simply does not persist
  }
  window.dispatchEvent(new Event(EVENT));
}

export function skipJob(id: string): string[] {
  const next = readSkipped().includes(id) ? readSkipped() : [...readSkipped(), id];
  write(next);
  return next;
}

export function unskipAll(): void {
  write([]);
}

let cache: string[] = EMPTY;
let cacheRaw: string | null = null;
function snapshot(): string[] {
  let raw: string | null = null;
  try {
    raw = localStorage.getItem(KEY);
  } catch {
    raw = null;
  }
  if (raw !== cacheRaw) {
    cacheRaw = raw;
    cache = readSkipped();
  }
  return cache;
}

export function useSkipped(): string[] {
  return useSyncExternalStore(
    (cb) => {
      window.addEventListener(EVENT, cb);
      window.addEventListener("storage", cb);
      return () => {
        window.removeEventListener(EVENT, cb);
        window.removeEventListener("storage", cb);
      };
    },
    snapshot,
    () => EMPTY,
  );
}
```

(The snapshot caches by raw string so `useSyncExternalStore` gets a stable reference.)

`download.ts` add:

```ts
export function resumeFilename(name: string | null | undefined, kind: "pdf" | "docx" | "zip"): string {
  const stem = (name ?? "").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_+|_+$/g, "") || "Resume";
  return kind === "zip" ? `${stem}_Package.zip` : `${stem}_Resume.${kind}`;
}
```

`queries.ts` additions:

```ts
export type PackageListItem = components["schemas"]["PackageListItem"];
export type PackageListFilter = "all" | "review" | "blocked" | "applied";
export const packageListKeys = { list: (filter: PackageListFilter) => ["package-list", filter] as const };
const LIST_PARAMS: Record<PackageListFilter, { status?: "draft" | "blocked"; applied?: boolean }> = {
  all: {}, review: { applied: false, status: "draft" }, blocked: { status: "blocked" }, applied: { applied: true },
};
export function usePackageList(filter: PackageListFilter) {
  return useQuery({
    queryKey: packageListKeys.list(filter),
    queryFn: () => unwrap(apiClient().GET("/api/v1/packages", { params: { query: LIST_PARAMS[filter] } })),
    staleTime: 10_000,
  });
}
export function invalidatePackageList(queryClient: QueryClient): void {
  void queryClient.invalidateQueries({ queryKey: ["package-list"] });
}
```

and call `invalidatePackageList` inside `invalidateApplications`, `invalidatePackages`, and `invalidateJobs` (a new package or status change affects the list).

`Nav.tsx`: replace `ITEMS` with `Jobs` (`/`), `Packages` (`/packages`, icon `Package`), `Pipeline`, `Profile`; render Settings as an icon button (`Settings` icon, `aria-label="Settings"`, same active styling). Active rule for Jobs: `pathname === "/" || pathname.startsWith("/jobs")`.

`StepBar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { FLOW_STEPS, flowPrompt, nextUp, stepForPath } from "@/lib/flow";
import { useJobs, usePackageList } from "@/lib/api/queries";
import { useSkipped } from "@/lib/skipped";

export function StepBar({ tailoring = false }: { tailoring?: boolean }) {
  const pathname = usePathname();
  const jobs = useJobs({ search: "", track: null, bucket: "fit", sort: "fit" });
  const review = usePackageList("review");
  const skipped = useSkipped();
  if (pathname.startsWith("/settings")) return null;
  const current = stepForPath(pathname, tailoring);
  const prompt = flowPrompt({ needsReview: review.data?.length ?? 0, next: nextUp(jobs.data ?? [], skipped, 1)[0] ?? null });
  return (
    <div className="border-b border-border bg-card/60">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-2 text-sm">
        <ol className="flex items-center gap-2" aria-label="Flow">
          {FLOW_STEPS.map((label, i) => (
            <li key={label} aria-current={i === current ? "step" : undefined} className={`flex items-center gap-2 ${i === current ? "font-medium text-foreground" : "text-muted-foreground"}`}>
              <span className={`inline-flex size-5 items-center justify-center rounded-full border text-xs ${i === current ? "border-foreground" : "border-border"}`}>{i + 1}</span>
              {label}
              {i < FLOW_STEPS.length - 1 ? <span aria-hidden className="text-muted-foreground">→</span> : null}
            </li>
          ))}
        </ol>
        {prompt ? <Link href={prompt.href} className="underline">{prompt.text}</Link> : null}
      </div>
    </div>
  );
}
```

`Shell.tsx`: render `<StepBar />` inside `TokenGate` above `{children}` (wrap both in a fragment) so it never shows without a token. The Tailor step (`tailoring`) is driven later by a tiny context in Task 3; for now the prop defaults to false.

- [ ] **Step 4: Run web checks and commit**

`pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build` → green.

```bash
git add apps/web/src
git commit -m "feat(web): flow state, step bar, packages query, and new navigation"
```

---

### Task 3: Jobs page: Next up panel, tabs, state-aware card button

**Files:**
- Create: `apps/web/src/components/queue/NextUp.tsx`, `NextUp.test.tsx`, `apps/web/src/components/queue/JobActionButton.tsx`, `JobActionButton.test.tsx`
- Modify: `apps/web/src/components/queue/JobCard.tsx` (+ test), `FilterBar.tsx` (+ test), `JobList.tsx`, `apps/web/src/app/page.tsx`, `apps/web/src/lib/api/queries.ts` (`JobFilters` gains `tab`)

**Interfaces:**
- Consumes: `jobState`, `nextUp`, `useSkipped`, `skipJob` (Task 2); `TailorButton`, `TaskProgress`; `useCreateApplication`, `usePatchApplication`.
- Produces:
  - `JobFilters` becomes `{ search: string; track: string | null; tab: "new" | "tailored" | "low"; sort: "fit" | "newest" }`; `useJobs` maps `tab === "low"` to `bucket: "low"` and the other two to `bucket: "fit"`; `JobList` applies the tab client-side: `new` keeps jobs with no `latest_package`, `tailored` keeps jobs with one, `low` keeps all returned.
  - `JobActionButton({ job, size?: "sm" | "default" })`: renders by `jobState`: `"tailor"` → the existing `TailorButton` (track select + Tailor, shows progress while running); `"review"` → a primary `Button` rendered as a `Link` to `/jobs/{id}/packages/{latest_package.id}` labelled **Review**, plus a small outline **Mark applied** button that creates the application if needed and patches it to `applied` (same logic as `PackageActions.markApplied`; move that logic into a shared hook `useMarkApplied()` in `queries.ts` returning `{ markApplied(job, packageId), isPending }`); `"applied"` → an `Applied` badge (tone green) and a link to `/pipeline`.
  - `NextUp({ jobs })`: card titled "Apply to these first"; rows ranked 1 to 5 from `nextUp(jobs, skipped)`; each row: rank, company, title, `FitBadge`, track name, `JobActionButton size="sm"`, and a `Skip` ghost button calling `skipJob(id)`; an empty state "Nothing to do: poll for jobs or add one" and a "Show skipped" link that calls `unskipAll()` when the skip list is non-empty.

- [ ] **Step 1: Failing tests**

`JobActionButton.test.tsx` (mock `./TailorButton` to a stub, mock `useMarkApplied` from queries): a job without a package renders the stub; with a package and no application renders a link named Review pointing at the package route and a Mark applied button that calls `markApplied` with the job and package id; with `application_status: "applied"` renders the text Applied.

`NextUp.test.tsx` (mock `./JobActionButton` to render the job id, mock `@/lib/skipped` with a controllable array): five of six jobs shown in fit order with ranks 1 to 5; a skipped job is absent; clicking Skip on row 1 calls `skipJob` with that id; the empty state renders when no jobs.

`FilterBar.test.tsx`: update to the tabs: three tabs New / Tailored / Low fit, clicking Tailored calls `onChange` with `tab: "tailored"`; the sort toggle unchanged.

`JobCard.test.tsx`: update: the "Review package" link no longer exists; a job with a package renders the Review button (via the real `JobActionButton` with `TailorButton` mocked).

- [ ] **Step 2: Run to verify failure**: `pnpm test -- src/components/queue` → FAIL.

- [ ] **Step 3: Implement**

`queries.ts`: change `JobFilters`, `keys.jobs`, and `useJobs`:

```ts
export type JobFilters = { search: string; track: string | null; tab: "new" | "tailored" | "low"; sort: "fit" | "newest" };
// in useJobs: bucket: filters.tab === "low" ? "low" : "fit"
export function useMarkApplied() {
  const create = useCreateApplication();
  const patch = usePatchApplication();
  return {
    isPending: create.isPending || patch.isPending,
    async markApplied(job: Pick<JobOut, "id">, packageId: string, existing: { id: string } | null): Promise<void> {
      const id = existing ? existing.id : (await create.mutateAsync({ job_id: job.id, package_id: packageId })).id;
      await patch.mutateAsync({ id, body: { status: "applied" } });
    },
  };
}
```

`JobActionButton.tsx`:

```tsx
"use client";

import Link from "next/link";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ApiError } from "@/lib/api/client";
import { useMarkApplied, type JobOut } from "@/lib/api/queries";
import { jobState } from "@/lib/flow";
import { TailorButton } from "./TailorButton";

export function JobActionButton({ job, size = "default" }: { job: JobOut; size?: "sm" | "default" }) {
  const state = jobState(job);
  const mark = useMarkApplied();
  if (state === "tailor") return <TailorButton job={job} />;
  if (state === "applied") {
    return (
      <div className="flex items-center gap-2">
        <StatusBadge tone="green">Applied</StatusBadge>
        <Link href="/pipeline" className="text-sm underline">Pipeline</Link>
      </div>
    );
  }
  const pkg = job.latest_package!;
  async function onMarkApplied() {
    try {
      // The card does not know the application id; PackageActions passes it when it has one.
      await mark.markApplied(job, pkg.id, null);
      toast.success("Marked as applied", { action: { label: "Open pipeline", onClick: () => { window.location.assign("/pipeline"); } } });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Could not mark as applied");
    }
  }
  return (
    <div className="flex items-center gap-2">
      <Button size={size} render={<Link href={`/jobs/${job.id}/packages/${pkg.id}`} />}>Review</Button>
      <Button size={size} variant="outline" onClick={onMarkApplied} disabled={mark.isPending}>Mark applied</Button>
    </div>
  );
}
```

`markApplied` with `existing = null` must tolerate a 409 from `POST /applications` (an application already exists, status `queued`): on `ApiError` with status 409 read `existing_application_id` from the problem body and patch that id instead. Implement that inside `useMarkApplied` so both callers get it.

`NextUp.tsx`: a `Card` with the heading, an ordered list of rows, using `FitBadge` and the track name from `useTracks()`; Skip button `aria-label={`Skip ${title}`}`; "Show skipped" calls `unskipAll()`.

`FilterBar.tsx`: replace the Fit / Low fit segmented toggle with `Tabs` (`value={filters.tab}`, `onValueChange={(v) => v && onChange({ ...filters, tab: v as JobFilters["tab"] })}`), triggers labelled New, Tailored, Low fit. `JobList.tsx`: filter `items` by the tab as specified. `JobCard.tsx`: replace `<TailorButton job={job} />` with `<JobActionButton job={job} />`, remove the underlined Review link, keep Open posting, Rescue, delete. `page.tsx`: title "Jobs"; initial filters `{ search: "", track: null, tab: "new", sort: "fit" }`; render `<NextUp jobs={allFit.data ?? []} />` above the filter bar using a second query `useJobs({ search: "", track: null, tab: "new", sort: "fit" })`; wrap each card in `<div id={`job-${job.id}`}>` (JobList already sets `id={job.id}`; change it to `job-${id}` to match the step bar's anchor).

- [ ] **Step 4: Run web checks and commit**

`pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build` → green.

```bash
git add apps/web/src
git commit -m "feat(web): next up panel, jobs tabs, and state-aware card actions"
```

---

### Task 4: Packages page

**Files:**
- Create: `apps/web/src/app/packages/page.tsx`, `apps/web/src/components/packages/PackageTable.tsx`, `PackageTable.test.tsx`

**Interfaces:**
- Consumes: `usePackageList(filter)`, `PackageListItem`, `FitBadge`, `useTracks`, `formatRelative`, `PACKAGE_STATUS_TONE`, `statusTone`.
- Produces: `/packages?filter=all|review|blocked|applied` (default `review`); `PackageTable({ rows, tracks })` renders a `Table` with columns Company, Role, Fit, Version · status, Application, Created, and a **Review** button (`Link` to `/jobs/{job_id}/packages/{id}`) per row; an empty state per filter ("Nothing to review", "No blocked packages", "Nothing applied yet", "No packages yet").

- [ ] **Step 1: Failing test**: `PackageTable.test.tsx` renders two rows (one draft unapplied, one blocked) and asserts the company, the `v1 · draft` badge, the `blocked` badge, and that each Review link points at the right route; the empty state text for `review`.

- [ ] **Step 2: Run to verify failure**: `pnpm test -- src/components/packages` → FAIL.

- [ ] **Step 3: Implement** `page.tsx` reads `filter` from `useSearchParams()` (fallback `review`), renders filter chips as `Tabs` (All, Needs review, Blocked, Applied) that push the query param with `router.replace`, then `<PackageTable rows={list.data ?? []} tracks={trackMap} />` with `Skeleton` while loading and `ApiErrorBanner` on error. Wrap the page body in `<Suspense>` (Next requires it around `useSearchParams` for static builds).

- [ ] **Step 4: Run web checks and commit**

```bash
git add apps/web/src
git commit -m "feat(web): packages page with review filters"
```

---

### Task 5: Review page: sticky action bar, named downloads, blocked-first layout, next tailored job

**Files:**
- Modify: `apps/web/src/components/review/PackageActions.tsx` (+ new `PackageActions.test.tsx`), `apps/web/src/app/jobs/[jobId]/packages/[packageId]/page.tsx`

**Interfaces:**
- Consumes: `resumeFilename`, `useAnswers()` (candidate name), `useMarkApplied`, `usePackageList("review")` for the next link, `downloadAuthenticated`.
- Produces: `PackageActions({ job, pkg, application, onRegenerate })` renders **Download PDF** (`/api/v1/packages/{id}/files/resume.pdf`, disabled when `!pkg.has_pdf`), **Download DOCX** (`files/resume.docx`, disabled when `!pkg.has_docx`), **Download zip**, **Regenerate** (calls `onRegenerate`), **Mark applied** or the status badge, **Open posting**; filenames from `resumeFilename(answers.name, kind)`; the Mark applied toast carries an "Open pipeline" action.

- [ ] **Step 1: Failing test** `PackageActions.test.tsx` (mock `@/lib/download` `downloadAuthenticated`, `useAnswers` returning `{ name: "Maya Chen" }`, `useMarkApplied`): clicking Download PDF calls `downloadAuthenticated("/api/v1/packages/p1/files/resume.pdf", "Maya_Chen_Resume.pdf")`; Download zip uses `Maya_Chen_Package.zip`; Regenerate calls `onRegenerate`; Mark applied calls `markApplied(job, "p1", application)`.

- [ ] **Step 2: Run to verify failure**: `pnpm test -- src/components/review/PackageActions.test.tsx` → FAIL.

- [ ] **Step 3: Implement**

`PackageActions.tsx`: add the two file downloads and the Regenerate button; name files with `resumeFilename(useAnswers().data?.name, kind)`; replace the local `markApplied` with `useMarkApplied().markApplied(job, pkg.id, application)`; the success toast: `toast.success("Marked as applied", { action: { label: "Open pipeline", onClick: () => router.push("/pipeline") } })` (use `useRouter` from `next/navigation`). Check `PackageOut` for the `has_pdf`/`has_docx` field names in `schema.d.ts`.

`page.tsx` (review): move the header block and `PackageActions` into a `<div className="sticky top-0 z-10 -mx-6 border-b border-border bg-background/95 px-6 py-3 backdrop-blur">` so the bar stays visible; pass `onRegenerate={() => setRegenOpen(true)}` and drop the separate Regenerate button. When `pkg.data.status === "blocked"` render `<GuardrailPanel>` above `<ResumePane>` (keep it below otherwise). At the bottom add the next link: from `usePackageList("review")`, find the first row whose `id !== packageId`; render **Next tailored job →** as a `Link` to its route, or the text "All reviewed" when none.

- [ ] **Step 4: Run web checks and commit**

```bash
git add apps/web/src
git commit -m "feat(web): sticky review actions with named downloads and next-job link"
```

---

### Task 6: Tailoring step signal, README, end-to-end check

**Files:**
- Create: `apps/web/src/lib/tailoring.ts` (tiny external store: `startTailoring(jobId)`, `stopTailoring(jobId)`, `useTailoringCount()`), test
- Modify: `apps/web/src/components/queue/TailorButton.tsx` (call start/stop around the task), `apps/web/src/components/shell/StepBar.tsx` (`tailoring = useTailoringCount() > 0`), `README.md`

- [ ] **Step 1: Failing test** `tailoring.test.ts`: count goes 0 → 1 → 0 across start/stop; two starts then one stop leaves 1; the hook re-renders (use `renderHook`).

- [ ] **Step 2: Run to verify failure**: `pnpm test -- src/lib/tailoring.test.ts` → FAIL.

- [ ] **Step 3: Implement** the store with `useSyncExternalStore` (module-level `Set<string>` and a listener set); in `TailorButton.start` call `startTailoring(job.id)` after the mutation succeeds and `stopTailoring(job.id)` inside `onFinished`; `StepBar` highlights Tailor while the count is positive.

README web section: replace the numbered walkthrough's queue/review lines with the flow: "Jobs shows *Apply to these first*; press the one button on the top row (Tailor → Review → Mark applied); Packages lists everything tailored; Pipeline tracks what you submitted. Downloads are named after you."

- [ ] **Step 4: Full verification and commit**

From `apps/web`: `pnpm test`, `pnpm typecheck`, `pnpm lint`, `pnpm build`. From `apps/api`: the full Python check set. From the root: `bash scripts/codegen.sh && git diff --exit-code packages/schemas apps/web/src/lib/api/schema.d.ts apps/api/src/rhapto/models`. Then `docker compose up -d --build web api` and a browser pass: Jobs shows Next up with the top row's button; the step bar prompt links to Packages when packages need review; `/packages` lists them; the review bar downloads `<Name>_Resume.pdf`; Mark applied moves the job to Applied and the Pipeline board.

```bash
git add apps/web/src README.md
git commit -m "feat(web): tailoring step signal and flow walkthrough"
```

---

## Self-review notes

- Spec coverage: step bar and prompt (T2, T6), navigation (T2), Next up with state button and Skip (T3), Jobs tabs (T3), state-aware card button (T3), Packages page and endpoint (T1, T4), review action bar, named downloads, blocked-first, next link, applied toast (T1, T5), README (T6).
- Type consistency: `JobFilters.tab` replaces `bucket` everywhere `useJobs`/`keys.jobs`/`FilterBar`/`StepBar` use it; `useMarkApplied(job, packageId, existing)` has one signature across `JobActionButton` and `PackageActions`; `PackageListItem` fields match the API schema in T1.
