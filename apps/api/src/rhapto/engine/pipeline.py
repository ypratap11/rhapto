from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from rhapto.engine.compose import assemble_resume, build_header, build_system_blocks, compose
from rhapto.engine.document import apply_edits, to_resume_document
from rhapto.engine.extract import extract
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.guardrails.tune import run_tune_guardrails
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.providers.llm import LLMProvider, MalformedOutputError, TokenUsage
from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.engine.render.tune_docx import render_tuned_docx
from rhapto.engine.repair import repair
from rhapto.engine.select import Selection, SelectionConfig, select_blocks
from rhapto.engine.tune import build_tune_system_blocks, to_edits, tune, tune_repair
from rhapto.engine.types import EngineError, Profile, TailorRequest
from rhapto.models.guardrail_report import GuardrailReport
from rhapto.models.jd_extract import JDExtract
from rhapto.models.package import ApplicationPackage, JobSnapshot
from rhapto.models.package import TokenUsage as PackageTokenUsage
from rhapto.models.profile.tracks import Track
from rhapto.models.resume_document import ResumeDocument
from rhapto.models.source_document import Edit, SourceDocument

# "tune" is the progress step tune mode emits in place of "select" and "compose". Steps may be
# added but never removed: the web progress bar maps task events onto these names.
STEPS = ("extract", "select", "compose", "tune", "validate", "repair", "render")
ProgressCallback = Callable[[str], Awaitable[None]]


class LLMBudgetExceeded(EngineError):
    """The pipeline would exceed the per-run LLM call budget."""


class CallBudget:
    def __init__(self, max_calls: int = 3) -> None:
        self.max_calls = max_calls
        self.calls = 0
        self.usage = TokenUsage()

    def before_call(self) -> None:
        if self.calls >= self.max_calls:
            raise LLMBudgetExceeded(f"LLM call budget of {self.max_calls} exhausted")

    def after_call(self, usage: TokenUsage) -> None:
        self.calls += 1
        self.usage = self.usage + usage


class TailorResult(BaseModel):
    package: ApplicationPackage
    docx: bytes
    selection: Selection
    edits: list[Edit] = Field(default_factory=list)
    # Blocks mode only. `package.guardrail_report` is always the POST-repair report, so on its own
    # a model that dropped a role and repaired it looks the same as one that never dropped
    # anything. `pre_repair_report` is the first compose's report, set only when that report
    # failed; `repaired` is True only when a repair call actually returned an output (not when
    # the budget or a malformed answer skipped it). Phase 4 measurement reads both.
    pre_repair_report: GuardrailReport | None = None
    repaired: bool = False


async def _notify(on_step: ProgressCallback | None, step: str) -> None:
    if on_step is not None:
        await on_step(step)


async def _structured_call[R](
    budget: CallBudget, call: Callable[[], Awaitable[tuple[R, TokenUsage]]]
) -> R:
    """Run one LLM step under the budget, retrying once if the model's output was malformed.

    A malformed answer still counts as a call, so the retry happens only when the budget has
    room for it; otherwise the error propagates.
    """
    budget.before_call()
    try:
        value, usage = await call()
    except MalformedOutputError:
        budget.after_call(TokenUsage())
        budget.before_call()
        value, usage = await call()
    budget.after_call(usage)
    return value


async def _repair_call[R](
    budget: CallBudget, call: Callable[[], Awaitable[tuple[R, TokenUsage]]]
) -> R | None:
    """The one repair attempt both modes make, or None when it cannot happen or failed.

    Unlike `_structured_call` it never raises and never retries: with no calls left, or with a
    malformed answer (which still counts as a call), the caller keeps its blocked draft so the
    human sees the report instead of a failed task.
    """
    try:
        budget.before_call()
    except LLMBudgetExceeded:
        return None
    try:
        value, usage = await call()
    except MalformedOutputError:
        budget.after_call(TokenUsage())
        return None
    budget.after_call(usage)
    return value


def _build_package(
    request: TailorRequest,
    track: Track,
    jd_extract: JDExtract,
    resume: ResumeDocument,
    cover_note: str,
    change_log: str,
    answers: dict[str, str],
    report: GuardrailReport,
    budget: CallBudget,
    llm: LLMProvider,
    *,
    mode: Literal["blocks", "tune"] = "blocks",
    edits: list[Edit] | None = None,
    source_document: SourceDocument | None = None,
) -> ApplicationPackage:
    """The parts of the package that are identical in both modes, in one place."""
    return ApplicationPackage(
        job=JobSnapshot(
            company=jd_extract.company, title=jd_extract.title, jd_text=request.jd_text
        ),
        track_id=track.id,
        jd_extract=jd_extract,
        resume=resume,
        cover_note=cover_note,
        change_log=change_log,
        answers=answers,
        guardrail_report=report,
        version=(request.previous_package.version + 1) if request.previous_package else 1,
        status="draft" if report.passed else "blocked",
        llm_calls=budget.calls,
        usage=PackageTokenUsage(**budget.usage.model_dump()),
        model=getattr(llm, "model", None),
        created_at=datetime.now(UTC),
        mode=mode,
        edits=edits or [],
        source_document=source_document,
    )


async def tailor(
    request: TailorRequest,
    profile: Profile,
    llm: LLMProvider,
    embedder: EmbeddingProvider,
    *,
    selection_config: SelectionConfig | None = None,
    budget: CallBudget | None = None,
    on_step: ProgressCallback | None = None,
) -> TailorResult:
    """extract -> select -> compose -> validate -> (repair -> validate) -> render. At most 3 LLM calls.

    In tune mode the middle of that changes to extract -> tune -> validate -> (repair ->
    validate) -> render: there is nothing to select (the user's document is the selection) and
    nothing to compose (the paragraphs already exist). The call budget is unchanged.
    """
    budget = budget or CallBudget()
    track = profile.get_track(request.track_id)

    await _notify(on_step, "extract")
    # A caller holding the extract from a previous run of the same unchanged JD passes it in; the
    # step is still announced so the UI's progress sequence does not change shape.
    jd_extract = request.jd_extract
    if jd_extract is None:
        jd_extract = await _structured_call(budget, lambda: extract(request.jd_text, llm))

    if request.mode == "tune":
        return await _tune_branch(request, profile, track, jd_extract, llm, budget, on_step)

    await _notify(on_step, "select")
    selection = await select_blocks(jd_extract, profile, track, embedder, selection_config)

    await _notify(on_step, "compose")
    previous = request.previous_package.resume if request.previous_package else None
    output = await _structured_call(
        budget,
        lambda: compose(jd_extract, profile, track, selection, llm, request.feedback, previous),
    )

    await _notify(on_step, "validate")
    resume = assemble_resume(output, profile)
    report = run_guardrails(
        resume, profile, selection.block_ids, jd_extract, cover_note=output.cover_note
    )

    pre_repair_report: GuardrailReport | None = None
    was_repaired = False
    if not report.passed:
        pre_repair_report = report
        await _notify(on_step, "repair")
        blocked = output
        fixed = await _repair_call(
            budget,
            lambda: repair(blocked, report, build_system_blocks(profile, track, selection), llm),
        )
        if fixed is not None:
            output = fixed
            was_repaired = True
            resume = assemble_resume(output, profile)
            report = run_guardrails(
                resume, profile, selection.block_ids, jd_extract, cover_note=output.cover_note
            )

    await _notify(on_step, "render")
    docx = b""
    if report.passed:
        try:
            docx = render_docx(resume, profile.block_map(), profile.base_for(track).style)
        except OrphanBulletError:
            docx = b""  # provenance violation is already in the report; nothing safe to render

    package = _build_package(
        request,
        track,
        jd_extract,
        resume,
        output.cover_note,
        output.change_log,
        output.answers_dict(),
        report,
        budget,
        llm,
    )
    return TailorResult(
        package=package,
        docx=docx,
        selection=selection,
        pre_repair_report=pre_repair_report,
        repaired=was_repaired,
    )


async def _tune_branch(
    request: TailorRequest,
    profile: Profile,
    track: Track,
    jd_extract: JDExtract,
    llm: LLMProvider,
    budget: CallBudget,
    on_step: ProgressCallback | None,
) -> TailorResult:
    """tune -> validate -> (repair -> validate) -> render, against the user's own document."""
    doc = request.source_document
    source_docx = request.source_docx
    assert doc is not None and source_docx is not None  # validated on the request

    await _notify(on_step, "tune")
    previous_edits = request.previous_package.edits if request.previous_package else None
    output = await _structured_call(
        budget,
        lambda: tune(jd_extract, doc, profile.answers, llm, request.feedback, previous_edits),
    )
    edits = to_edits(doc, output)

    await _notify(on_step, "validate")
    report = run_tune_guardrails(
        doc, edits, jd_extract, profile.guardrails, cover_note=output.cover_note
    )

    if not report.passed:
        await _notify(on_step, "repair")
        blocked_tune = output
        fixed_tune = await _repair_call(
            budget,
            lambda: tune_repair(blocked_tune, report, build_tune_system_blocks(doc), llm),
        )
        if fixed_tune is not None:
            output = fixed_tune
            edits = to_edits(doc, output)
            report = run_tune_guardrails(
                doc, edits, jd_extract, profile.guardrails, cover_note=output.cover_note
            )

    await _notify(on_step, "render")
    # Unlike blocks mode there is no safe partial artefact: the writer edits the user's own file
    # in place, so a failing report means we write nothing and let the human read the violations.
    # The guard mirrors the blocks branch's OrphanBulletError handling: `render_tuned_docx`
    # raises when a paragraph id is missing from the DOCX, which `tune-scope` already rules out
    # unless `source_document` and `source_docx` disagree (a stale upload, a cached parse). That
    # is worth a package the human can read, not a failed task.
    docx = b""
    if report.passed:
        try:
            docx = render_tuned_docx(source_docx, edits)
        except EngineError:
            docx = b""
    resume = to_resume_document(apply_edits(doc, edits), build_header(profile.answers))

    package = _build_package(
        request,
        track,
        jd_extract,
        resume,
        output.cover_note,
        output.change_log,
        output.answers_dict(),
        report,
        budget,
        llm,
        mode="tune",
        edits=edits,
        source_document=doc,
    )
    return TailorResult(
        package=package,
        docx=docx,
        selection=Selection(block_ids=[], scores={}, excluded_block_ids=[], requirements_text=""),
        edits=edits,
    )
