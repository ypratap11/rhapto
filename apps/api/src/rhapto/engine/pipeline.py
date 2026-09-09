from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pydantic import BaseModel

from rhapto.engine.compose import assemble_resume, build_system_blocks, compose
from rhapto.engine.extract import extract
from rhapto.engine.guardrails.registry import run_guardrails
from rhapto.engine.providers.embeddings import EmbeddingProvider
from rhapto.engine.providers.llm import LLMProvider, TokenUsage
from rhapto.engine.render.docx import OrphanBulletError, render_docx
from rhapto.engine.repair import repair
from rhapto.engine.select import Selection, SelectionConfig, select_blocks
from rhapto.engine.types import EngineError, Profile, TailorRequest
from rhapto.models.package import ApplicationPackage, JobSnapshot

STEPS = ("extract", "select", "compose", "validate", "repair", "render")
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


async def _notify(on_step: ProgressCallback | None, step: str) -> None:
    if on_step is not None:
        await on_step(step)


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
    """extract -> select -> compose -> validate -> (repair -> validate) -> render. At most 3 LLM calls."""
    budget = budget or CallBudget()
    track = profile.get_track(request.track_id)

    await _notify(on_step, "extract")
    budget.before_call()
    jd_extract, usage = await extract(request.jd_text, llm)
    budget.after_call(usage)

    await _notify(on_step, "select")
    selection = await select_blocks(jd_extract, profile, track, embedder, selection_config)

    await _notify(on_step, "compose")
    previous = request.previous_package.resume if request.previous_package else None
    budget.before_call()
    output, usage = await compose(
        jd_extract, profile, track, selection, llm, request.feedback, previous
    )
    budget.after_call(usage)

    await _notify(on_step, "validate")
    resume = assemble_resume(output, profile)
    report = run_guardrails(
        resume, profile, selection.block_ids, jd_extract, cover_note=output.cover_note
    )

    if not report.passed:
        await _notify(on_step, "repair")
        budget.before_call()
        output, usage = await repair(output, report, build_system_blocks(profile, track), llm)
        budget.after_call(usage)
        resume = assemble_resume(output, profile)
        report = run_guardrails(
            resume, profile, selection.block_ids, jd_extract, cover_note=output.cover_note
        )

    await _notify(on_step, "render")
    try:
        docx = render_docx(resume, profile.block_map())
    except OrphanBulletError:
        docx = b""  # provenance violation is already in the report; nothing safe to render

    package = ApplicationPackage(
        job=JobSnapshot(
            company=jd_extract.company, title=jd_extract.title, jd_text=request.jd_text
        ),
        track_id=track.id,
        jd_extract=jd_extract,
        resume=resume,
        cover_note=output.cover_note,
        change_log=output.change_log,
        answers=output.answers,
        guardrail_report=report,
        version=(request.previous_package.version + 1) if request.previous_package else 1,
        status="draft" if report.passed else "blocked",
        llm_calls=budget.calls,
        created_at=datetime.now(UTC),
    )
    return TailorResult(package=package, docx=docx, selection=selection)
