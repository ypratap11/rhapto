# Resume Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A user uploads their existing `.docx` resume and gets a reviewed block library, proposed tracks with taxonomy, and location answers — turning a two-hour manual setup into minutes, without any number reaching a resume unverified.

**Architecture:** Parsing is two stages. `engine/document.py:parse_docx` already turns a `.docx` into classified `DocParagraph`s deterministically; a new pure-engine module makes one LLM call to turn that into a *proposal* of blocks, tracks and location. The proposal is returned to the browser and **persisted only after the user confirms**, through the profile endpoints that already exist. Taxonomy validation lives in the API layer, because import-linter forbids `engine` from importing `services`.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, SQLAlchemy; Next 16 / React 19 / TanStack Query / vitest.

**Spec:** `docs/superpowers/specs/2026-09-22-first-run-onboarding-design.md` (§6 Screen 2, §9 Data and API, §10 Testing)

## Global Constraints

- CLAUDE.md rules: never submit an application; nothing personal and no keys in the repo; max 3 LLM calls per tailoring run (resume import is a separate flow and makes exactly 1).
- Import-linter: `engine` imports none of config/profile/db/services/worker/api/cli; `services` never import worker/api/cli.
- **Every imported block is `verified=False`.** No code path in this plan may set it true. Spec §6.
- **Dates are never invented.** A period that does not match the schema's pattern is dropped, not guessed. Spec §6.
- Nothing is written to the database until the user confirms. The import endpoint is read-only with respect to the profile. Spec §9.
- Generated files never hand-edited: `apps/api/src/rhapto/models/**`, `packages/schemas/openapi.json`, `apps/web/src/lib/api/schema.d.ts` — regenerate via `bash scripts/codegen.sh` from the repo root and commit with the change that caused them.
- Python checks before every commit (from `apps/api`): `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, then pytest in two foreground runs (memory is tight; never two at once, never backgrounded): `uv run pytest -q -p no:cacheprovider tests/unit tests/golden tests/guardrails --deselect tests/unit/test_enqueue_arq.py` then `uv run pytest -q -p no:cacheprovider tests/api tests/db`. Web (from `apps/web`): `npx vitest run --maxWorkers=4 --testTimeout=90000`, `pnpm typecheck`, `pnpm lint` (one accepted warning in `TaskProgress.tsx`), `pnpm build`.
- Commit messages end with the two attribution lines given in the session.

## File Structure

```
apps/api/src/rhapto/engine/prompts/import_resume.py   NEW  the system prompt
apps/api/src/rhapto/engine/import_resume.py           NEW  ResumeImport models + import_resume()
apps/api/src/rhapto/api/routers/profile.py            MOD  POST /profile/import-resume
apps/api/src/rhapto/api/schemas.py                    MOD  ResumeImportOut
apps/web/src/lib/api/queries.ts                       MOD  useImportResume, useConfirmImport
apps/web/src/components/profile/ImportResume.tsx      NEW  upload + review proposal
apps/web/src/components/profile/ConfirmMetrics.tsx    NEW  one-number-at-a-time confirmation
apps/web/src/components/profile/ImportExport.tsx      MOD  entry point for the new flow
```

---

### Task 1: Engine — parse a resume into a proposal

**Files:**
- Create: `apps/api/src/rhapto/engine/prompts/import_resume.py`
- Create: `apps/api/src/rhapto/engine/import_resume.py`
- Test: `apps/api/tests/unit/test_import_resume.py`

**Interfaces:**
- Consumes: `SourceDocument` from `rhapto.models.source_document`; `LLMProvider`, `Message`, `SystemBlock`, `TokenUsage` from `rhapto.engine.providers.llm`; `Block` from `rhapto.models.profile.blocks`.
- Produces:
  - `class ImportedBlock(BaseModel)` — `id: str`, `type: Literal["role","project","achievement","skill","credential"]`, `org: str | None = None`, `role: str | None = None`, `period: str | None = None`, `content: str`, `metric: str | None = None`, `tags: list[str] = []`
  - `class ImportedTrack(BaseModel)` — `id: str`, `name: str`, `keywords: list[str]`, `field: str`, `role: str`
  - `class ImportedLocation(BaseModel)` — `location_home: str | None = None`, `location_preferred: list[str] = []`, `remote_ok: str | None = None`
  - `class ResumeImport(BaseModel)` — `blocks: list[ImportedBlock]`, `tracks: list[ImportedTrack]`, `location: ImportedLocation`
  - `async def import_resume(document: SourceDocument, llm: LLMProvider) -> tuple[ResumeImport, TokenUsage]`
  - `def to_blocks(imported: list[ImportedBlock]) -> list[Block]` — converts, always `verified=False`, drops an unparseable period, de-duplicates ids.

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/unit/test_import_resume.py
import pytest
from rhapto.engine.import_resume import ImportedBlock, ResumeImport, import_resume, to_blocks
from rhapto.engine.providers.fake import FakeLLMProvider
from rhapto.models.source_document import DocParagraph, SourceDocument


def _doc() -> SourceDocument:
    return SourceDocument(
        filename="cv.docx",
        paragraphs=[
            DocParagraph(id="p1", text="Jane Roe", role="heading", section=None),
            DocParagraph(id="p2", text="Delivery Lead, Acme 2019-2023", role="body", section="Experience"),
        ],
        sections=[],
    )


def _payload() -> dict:
    return ResumeImport(
        blocks=[
            ImportedBlock(id="acme-lead", type="role", org="Acme", role="Delivery Lead",
                          period="2019-2023", content="Led delivery for Acme.", metric=None),
        ],
        tracks=[],
        location={"location_home": "Dublin, CA", "location_preferred": [], "remote_ok": "yes"},
    ).model_dump(mode="json")


async def test_import_resume_makes_one_call_and_returns_the_proposal() -> None:
    llm = FakeLLMProvider([_payload()])
    result, usage = await import_resume(_doc(), llm)
    assert [b.id for b in result.blocks] == ["acme-lead"]
    assert result.location.location_home == "Dublin, CA"
    assert usage.output_tokens >= 0


async def test_an_empty_document_is_rejected_before_spending_a_call() -> None:
    empty = SourceDocument(filename="cv.docx", paragraphs=[], sections=[])
    llm = FakeLLMProvider([])
    with pytest.raises(ValueError, match="empty"):
        await import_resume(empty, llm)


def test_imported_blocks_are_never_verified() -> None:
    """The whole provenance guarantee rests on this: a number the user has not confirmed
    must not be citable. An import that auto-verified would put a figure they wrote once
    onto every future resume with Rhapto's blessing."""
    blocks = to_blocks([
        ImportedBlock(id="a", type="role", content="Cut costs 30%.", metric="30%"),
    ])
    assert all(b.verified is False for b in blocks)


def test_an_unparseable_period_is_dropped_not_guessed() -> None:
    """Fabricating employment dates on a CV is not a recoverable error."""
    blocks = to_blocks([
        ImportedBlock(id="a", type="role", period="summer of 2019", content="x"),
        ImportedBlock(id="b", type="role", period="2019-2023", content="y"),
    ])
    assert blocks[0].period is None
    assert blocks[1].period == "2019-2023"


def test_duplicate_ids_are_made_unique() -> None:
    blocks = to_blocks([
        ImportedBlock(id="acme", type="role", content="x"),
        ImportedBlock(id="acme", type="project", content="y"),
    ])
    assert len({b.id for b in blocks}) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `apps/api`): `uv run pytest -q -p no:cacheprovider tests/unit/test_import_resume.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'rhapto.engine.import_resume'`

- [ ] **Step 3: Write the prompt**

```python
# apps/api/src/rhapto/engine/prompts/import_resume.py
IMPORT_RESUME_SYSTEM = """You convert a parsed resume into a structured profile proposal.

Return blocks, tracks and location.

BLOCKS. One block per distinct thing the resume claims. Use these types:
- role: a job held at an employer, with org and period
- project: a named engagement or deliverable, usually inside a role
- achievement: a specific accomplishment, especially one carrying a number
- skill: a grouped capability statement
- credential: a degree, certification or course

Give each block a short kebab-case id derived from its org and subject
(e.g. "acme-delivery-lead"). Copy the resume's own wording; do not
embellish, and do not invent anything the resume does not say.

PERIOD. Use exactly the form the resume gives: "2019", "2019-2023",
"Mar 2019-Present". If a block has no date in the resume, omit the field.
NEVER guess or infer a date.

METRIC. If a block's text contains any number that makes a claim
(percentages, money, counts, durations), put a short summary of those
numbers in `metric`. Leave it out when there are none.

TRACKS. Propose one to three career tracks the resume supports. Each needs
a taxonomy `field` and `role` id from this list:
engineering, data-science, product, program-project-management, design,
marketing, sales, finance, operations, people, customer-success, other.

LOCATION. Extract location_home if stated, any preferred locations, and
whether remote is acceptable ("yes"/"no") if the resume says.
"""
```

- [ ] **Step 4: Write the module**

```python
# apps/api/src/rhapto/engine/import_resume.py
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from rhapto.engine.prompts.import_resume import IMPORT_RESUME_SYSTEM
from rhapto.engine.providers.llm import LLMProvider, Message, SystemBlock, TokenUsage
from rhapto.models.profile.blocks import Block
from rhapto.models.source_document import SourceDocument


class ImportedBlock(BaseModel):
    id: str
    type: Literal["role", "project", "achievement", "skill", "credential"]
    org: str | None = None
    role: str | None = None
    period: str | None = None
    content: str
    metric: str | None = None
    tags: list[str] = Field(default_factory=list)


class ImportedTrack(BaseModel):
    id: str
    name: str
    keywords: list[str] = Field(default_factory=list)
    field: str
    role: str


class ImportedLocation(BaseModel):
    location_home: str | None = None
    location_preferred: list[str] = Field(default_factory=list)
    remote_ok: str | None = None


class ResumeImport(BaseModel):
    """What the model proposes. Nothing here is persisted until the user confirms it."""

    blocks: list[ImportedBlock] = Field(default_factory=list)
    tracks: list[ImportedTrack] = Field(default_factory=list)
    location: ImportedLocation = Field(default_factory=ImportedLocation)


async def import_resume(
    document: SourceDocument, llm: LLMProvider
) -> tuple[ResumeImport, TokenUsage]:
    """One LLM call: a parsed resume to a proposed profile."""
    text = "\n".join(p.text for p in document.paragraphs if p.text.strip())
    if not text.strip():
        raise ValueError("resume is empty")
    result = await llm.complete_structured(
        system=[SystemBlock(text=IMPORT_RESUME_SYSTEM, cache=True)],
        messages=[Message(role="user", content=f"<resume>\n{text}\n</resume>")],
        output_schema=ResumeImport,
        max_tokens=8192,
    )
    return result.value, result.usage


def to_blocks(imported: list[ImportedBlock]) -> list[Block]:
    """Proposal to real `Block`s: never verified, never carrying a guessed date.

    `Block.period` is pattern-validated by the generated model, so an unparseable value is
    detected by trying it and dropping it -- rather than duplicating the regex here, where it
    would drift from the schema.
    """
    out: list[Block] = []
    seen: set[str] = set()
    for item in imported:
        block_id = item.id
        suffix = 2
        while block_id in seen:
            block_id = f"{item.id}-{suffix}"
            suffix += 1
        seen.add(block_id)
        fields = dict(
            id=block_id,
            type=item.type,
            org=item.org,
            role=item.role,
            content=item.content,
            metric=item.metric,
            tags=list(item.tags),
            verified=False,
        )
        try:
            out.append(Block(**fields, period=item.period))
        except ValidationError:
            out.append(Block(**fields))
    return out
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest -q -p no:cacheprovider tests/unit/test_import_resume.py`
Expected: PASS (5 tests)

- [ ] **Step 6: Run the full checks and commit**

Run from `apps/api`: `uv run ruff check src tests`, `uv run ruff format src tests`, `uv run mypy src`, `uv run lint-imports`, then the two pytest runs from Global Constraints.

```bash
git add apps/api/src/rhapto/engine/import_resume.py apps/api/src/rhapto/engine/prompts/import_resume.py apps/api/tests/unit/test_import_resume.py
git commit -m "feat(engine): parse a resume into a proposed profile"
```

---

### Task 2: API — `POST /profile/import-resume`

**Files:**
- Modify: `apps/api/src/rhapto/api/routers/profile.py`
- Modify: `apps/api/src/rhapto/api/schemas.py`
- Test: `apps/api/tests/api/test_import_resume_api.py`

**Interfaces:**
- Consumes: `import_resume`, `to_blocks`, `ResumeImport` from Task 1; `parse_docx` from `rhapto.engine.document`; `resolve_llm` from `rhapto.services.llm`; `find_field`, `find_role` from `rhapto.services.taxonomy`.
- Produces: `class ResumeImportOut(BaseModel)` in `api/schemas.py` — `blocks: list[Block]`, `tracks: list[ImportedTrack]`, `location: ImportedLocation`, `dropped_periods: int`, `metrics_to_confirm: int`. Endpoint `POST /api/v1/profile/import-resume` taking `file: UploadFile`, returning `ResumeImportOut`, status 200.

**Why taxonomy is validated here and not in Task 1:** import-linter forbids `engine` from importing `services`, and the taxonomy loader lives in `services/taxonomy.py`. A track whose `field`/`role` the model invented is dropped here rather than offered to the user — a track without valid taxonomy silently empties every Field filter on the Jobs page.

- [ ] **Step 1: Write the failing tests**

```python
# apps/api/tests/api/test_import_resume_api.py
from helpers_docx import build_fixture_docx


async def test_import_returns_a_proposal_without_persisting_anything(client, user) -> None:
    """Spec §9: the endpoint is read-only with respect to the profile."""
    before = (await client.get("/api/v1/profile/blocks")).json()
    docx = build_fixture_docx(["Jane Roe", "Delivery Lead, Acme 2019-2023"])
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", docx)}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["blocks"], "expected at least one proposed block"
    assert all(b["verified"] is False for b in body["blocks"])
    after = (await client.get("/api/v1/profile/blocks")).json()
    assert after == before, "import must not write to the profile"


async def test_a_track_with_invented_taxonomy_is_dropped(client, user) -> None:
    """A track whose field is not in the taxonomy would silently empty every Field filter."""
    docx = build_fixture_docx(["Jane Roe", "Delivery Lead, Acme 2019-2023"])
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.docx", docx)}
    )
    for track in res.json()["tracks"]:
        assert track["field"] in {
            "engineering", "data-science", "product", "program-project-management",
            "design", "marketing", "sales", "finance", "operations", "people",
            "customer-success", "other",
        }


async def test_a_non_docx_upload_is_rejected(client, user) -> None:
    res = await client.post(
        "/api/v1/profile/import-resume", files={"file": ("cv.txt", b"hello")}
    )
    assert res.status_code == 422
    assert "docx" in res.json()["detail"].lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q -p no:cacheprovider tests/api/test_import_resume_api.py`
Expected: FAIL — 404, the route does not exist.

- [ ] **Step 3: Add the response schema**

```python
# apps/api/src/rhapto/api/schemas.py
class ResumeImportOut(BaseModel):
    """A proposed profile the user has not yet accepted."""

    blocks: list[Block]
    tracks: list[ImportedTrack]
    location: ImportedLocation
    #: Blocks whose date could not be read and was deliberately left empty.
    dropped_periods: int
    #: Blocks carrying a number, which the confirmation step will walk through.
    metrics_to_confirm: int
```

- [ ] **Step 4: Add the endpoint**

```python
# apps/api/src/rhapto/api/routers/profile.py
@router.post("/import-resume", response_model=ResumeImportOut)
async def import_resume_endpoint(
    file: UploadFile,
    user_id: UserDep,
    session: SessionDep,
    settings: SettingsDep,
) -> ResumeImportOut:
    """Parse an uploaded resume into a proposed profile. Writes nothing.

    The user reviews the proposal and accepts it through the existing block, track and answer
    endpoints, so there is exactly one code path that writes a profile.
    """
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="upload a .docx file")
    data = await file.read()
    try:
        document = await asyncio.to_thread(parse_docx, data, file.filename or "resume.docx")
    except Exception as exc:
        raise HTTPException(
            status_code=422, detail="could not read the document; is it a valid .docx?"
        ) from exc

    llm = await resolve_llm(session, settings, user_id)
    try:
        proposal, _usage = await import_resume(document, llm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    blocks = to_blocks(proposal.blocks)
    tracks = [
        t
        for t in proposal.tracks
        if find_field(t.field) is not None and find_role(t.field, t.role) is not None
    ]
    return ResumeImportOut(
        blocks=blocks,
        tracks=tracks,
        location=proposal.location,
        dropped_periods=sum(
            1 for i, b in zip(proposal.blocks, blocks, strict=True) if i.period and not b.period
        ),
        metrics_to_confirm=sum(1 for b in blocks if b.metric),
    )
```

- [ ] **Step 5: Run tests, then codegen**

Run: `uv run pytest -q -p no:cacheprovider tests/api/test_import_resume_api.py`
Expected: PASS (3 tests)

Then from the repo root: `bash scripts/codegen.sh`

- [ ] **Step 6: Run the full checks and commit**

```bash
git add apps/api/src/rhapto/api apps/api/tests/api/test_import_resume_api.py packages/schemas/openapi.json apps/web/src/lib/api/schema.d.ts
git commit -m "feat(api): propose a profile from an uploaded resume"
```

---

### Task 3: Web — upload and review the proposal

**Files:**
- Create: `apps/web/src/components/profile/ImportResume.tsx`
- Create: `apps/web/src/components/profile/ImportResume.test.tsx`
- Modify: `apps/web/src/lib/api/queries.ts`
- Modify: `apps/web/src/components/profile/ImportExport.tsx`

**Interfaces:**
- Consumes: `POST /api/v1/profile/import-resume` from Task 2.
- Produces: `useImportResume()` mutation in `queries.ts` returning `ResumeImportOut`; `<ImportResume />` rendering the proposal and writing it on confirm via the existing `useUpsertBlock`, `useUpsertTrack` and `usePutAnswers` hooks.

**Design notes:** follow the approved visual vocabulary — components from `src/components/ui/*` and the tokens in `globals.css`. Do not invent colours or chip shapes. Blocks are grouped by type, each showing org, role, period and a "no date" marker where the period was dropped, so the user can see what was and was not read.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/profile/ImportResume.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ImportResume } from "./ImportResume";

const proposal = {
  blocks: [
    { id: "acme-lead", type: "role", org: "Acme", role: "Delivery Lead",
      period: "2019-2023", content: "Led delivery.", verified: false, tags: [] },
    { id: "acme-win", type: "achievement", org: "Acme", period: null,
      content: "Cut costs 30%.", metric: "30%", verified: false, tags: [] },
  ],
  tracks: [{ id: "tpm", name: "TPM", keywords: [], field: "program-project-management",
             role: "technical-program-manager" }],
  location: { location_home: "Dublin, CA", location_preferred: [], remote_ok: "yes" },
  dropped_periods: 1,
  metrics_to_confirm: 1,
};

describe("ImportResume", () => {
  it("shows every proposed block before anything is saved", () => {
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText("Delivery Lead")).toBeInTheDocument();
    expect(screen.getByText(/Cut costs 30%/)).toBeInTheDocument();
  });

  it("marks blocks whose date could not be read", () => {
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText(/1 .*no date/i)).toBeInTheDocument();
  });

  it("says nothing is saved until the user confirms", () => {
    render(<ImportResume proposal={proposal} onConfirm={vi.fn()} />);
    expect(screen.getByText(/nothing is saved yet/i)).toBeInTheDocument();
  });

  it("passes the proposal to onConfirm when accepted", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ImportResume proposal={proposal} onConfirm={onConfirm} />);
    await user.click(screen.getByRole("button", { name: /add .* to my profile/i }));
    expect(onConfirm).toHaveBeenCalledWith(proposal);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `apps/web`): `npx vitest run src/components/profile/ImportResume.test.tsx`
Expected: FAIL — cannot resolve `./ImportResume`.

- [ ] **Step 3: Add the hook**

```ts
// apps/web/src/lib/api/queries.ts
export type ResumeImportOut = components["schemas"]["ResumeImportOut"];

export function useImportResume() {
  return useMutation({
    mutationFn: async (file: File): Promise<ResumeImportOut> => {
      const body = new FormData();
      body.append("file", file);
      return apiFetch<ResumeImportOut>("/profile/import-resume", { method: "POST", body });
    },
  });
}
```

- [ ] **Step 4: Build the component**

Render the proposal grouped by block type. Above the list, a muted line: `Nothing is saved yet — review this first.` Where `dropped_periods > 0`, a line reading `${dropped_periods} blocks had no date Rhapto could read — add them later.` The primary action is `Add N blocks to my profile`; a secondary `Cancel` discards. On confirm, call `onConfirm(proposal)`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `npx vitest run src/components/profile/ImportResume.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 6: Wire it into ImportExport, run web checks and commit**

Add an "Import from a resume" entry alongside the existing profile import. Run `npx vitest run --maxWorkers=4 --testTimeout=90000`, `pnpm typecheck`, `pnpm lint`, `pnpm build`.

```bash
git add apps/web/src/components/profile apps/web/src/lib/api/queries.ts
git commit -m "feat(web): review a resume import before it is saved"
```

---

### Task 4: Web — guided metric confirmation

**Files:**
- Create: `apps/web/src/components/profile/ConfirmMetrics.tsx`
- Create: `apps/web/src/components/profile/ConfirmMetrics.test.tsx`
- Modify: `apps/web/src/components/profile/ImportResume.tsx`

**Interfaces:**
- Consumes: the saved blocks from Task 3; `useUpsertBlock` from `queries.ts`.
- Produces: `<ConfirmMetrics blocks={Block[]} onDone={() => void} />` — walks blocks where `metric` is set, one at a time, and sets `verified: true` only on the ones the user confirms.

**Why this step exists:** an imported block is unverified, so its numbers are stripped from output. This is where the user turns "many departments" into "15+ departments" — by asserting each figure themselves. It is also where they learn what `verified` means, by doing it once on their own numbers.

- [ ] **Step 1: Write the failing test**

```tsx
// apps/web/src/components/profile/ConfirmMetrics.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConfirmMetrics } from "./ConfirmMetrics";

const blocks = [
  { id: "a", type: "achievement", content: "Cut costs 30%.", metric: "30%", verified: false, tags: [] },
  { id: "b", type: "achievement", content: "Led team of 12.", metric: "12", verified: false, tags: [] },
];

describe("ConfirmMetrics", () => {
  it("shows one number at a time with its sentence", () => {
    render(<ConfirmMetrics blocks={blocks} onConfirm={vi.fn()} onSkip={vi.fn()} onDone={vi.fn()} />);
    expect(screen.getByText(/Cut costs 30%/)).toBeInTheDocument();
    expect(screen.queryByText(/Led team of 12/)).not.toBeInTheDocument();
  });

  it("verifies only the block the user confirms", async () => {
    const onConfirm = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ConfirmMetrics blocks={blocks} onConfirm={onConfirm} onSkip={vi.fn()} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /yes, .* accurate/i }));
    expect(onConfirm).toHaveBeenCalledWith("a");
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("leaves a skipped block unverified and moves on", async () => {
    const onSkip = vi.fn();
    const user = userEvent.setup({ delay: null });
    render(<ConfirmMetrics blocks={blocks} onConfirm={vi.fn()} onSkip={onSkip} onDone={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /skip/i }));
    expect(onSkip).toHaveBeenCalledWith("a");
    expect(screen.getByText(/Led team of 12/)).toBeInTheDocument();
  });

  it("explains what confirming buys", () => {
    render(<ConfirmMetrics blocks={blocks} onConfirm={vi.fn()} onSkip={vi.fn()} onDone={vi.fn()} />);
    expect(screen.getByText(/unconfirmed numbers are removed/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `npx vitest run src/components/profile/ConfirmMetrics.test.tsx`
Expected: FAIL — cannot resolve `./ConfirmMetrics`.

- [ ] **Step 3: Build the component**

One block at a time. Show the block's sentence with the metric highlighted, and the question `Is this accurate and defensible?`. Buttons: `Yes, it's accurate` → `onConfirm(id)`; `Skip` → `onSkip(id)`. A progress line `n of N`. Below, a muted explanation: `Unconfirmed numbers are removed from generated resumes — the claim stays, the figure goes.` When the last block is answered, call `onDone()`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `npx vitest run src/components/profile/ConfirmMetrics.test.tsx`
Expected: PASS (4 tests)

- [ ] **Step 5: Chain it after the import confirm**

In `ImportResume.tsx`, after blocks are written, render `<ConfirmMetrics />` over the saved blocks that carry a `metric`, calling `useUpsertBlock` with `verified: true` on each confirmation.

- [ ] **Step 6: Run web checks and commit**

```bash
git add apps/web/src/components/profile
git commit -m "feat(web): confirm each imported metric before it can be used"
```

---

## Self-review notes

- **Spec coverage.** §6 upload (T2), parse into blocks (T1), propose tracks with taxonomy (T1 proposes, T2 validates), location (T1/T2), guided metric confirmation (T4), unverified-always (T1 + asserted in T2/T4), dates never invented (T1). §9 `POST /profile/import-resume` (T2). §10 parser, verification, taxonomy tests (T1, T2, T4).
- **Deliberately out of scope**, and belonging to the other two plans: the `/welcome` wizard shell and screens 1 and 3 (plan 2); checklist expansion and empty states (plan 3); `POST /searches/validate-location` and `GET /settings/cost-estimate` (plan 2). This plan ships value on its own — any existing user can import a resume without a wizard.
- **Type consistency.** `ImportedBlock`, `ImportedTrack`, `ImportedLocation`, `ResumeImport`, `import_resume`, `to_blocks`, `ResumeImportOut`, `useImportResume` are used under those exact names in every task that references them.
- **Open decision from spec §12** — one LLM call for the whole resume versus one per section. This plan implements the single call, which is simpler and cheaper. If a long real resume returns truncated or low-quality blocks, splitting by section is the follow-up; measure before changing.
