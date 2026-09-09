from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from pathlib import Path

import typer

from rhapto.config import Settings, get_settings
from rhapto.engine.pipeline import LLMBudgetExceeded, TailorResult, tailor
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.embeddings import EmbeddingProvider, FastEmbedProvider
from rhapto.engine.providers.llm import LLMProvider
from rhapto.engine.render.pdf import PdfRenderError, convert_docx_to_pdf, soffice_available
from rhapto.engine.types import ProfileError, TailorRequest
from rhapto.profile.loader import load_profile

app = typer.Typer(
    no_args_is_help=True, help="Rhapto: human-in-the-loop AI job application copilot."
)
profile_app = typer.Typer(no_args_is_help=True, help="Inspect and validate a profile directory.")
app.add_typer(profile_app, name="profile")

EXIT_BLOCKED = 2


@dataclass
class Providers:
    llm: LLMProvider
    embedder: EmbeddingProvider


def build_providers(settings: Settings) -> Providers:
    if not settings.anthropic_api_key:
        raise typer.BadParameter("ANTHROPIC_API_KEY is not set; put it in .env or the environment")
    return Providers(
        llm=AnthropicProvider(model=settings.rhapto_llm_model, api_key=settings.anthropic_api_key),
        embedder=FastEmbedProvider(settings.rhapto_embedding_model),
    )


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "untitled"


def write_package(result: TailorResult, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    if result.docx:
        (target / "resume.docx").write_bytes(result.docx)
    (target / "cover-note.md").write_text(result.package.cover_note + "\n", encoding="utf-8")
    (target / "package.json").write_text(result.package.model_dump_json(indent=2), encoding="utf-8")


@app.command(name="tailor")
def tailor_cmd(
    jd: Path = typer.Option(
        ..., "--jd", exists=True, dir_okay=False, readable=True, help="Job description text file"
    ),
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    track: str | None = typer.Option(None, "--track", help="Track id (default: first track)"),
    out: Path = typer.Option(
        Path("out"), "--out", help="Output root; a <company>-<role> folder is created"
    ),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF conversion"),
    feedback: str | None = typer.Option(None, "--feedback", help="Regeneration feedback"),
) -> None:
    """Tailor a resume package for one job description."""
    settings = get_settings()
    try:
        loaded = load_profile(profile)
    except ProfileError as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(1) from exc
    providers = build_providers(settings)
    jd_text = jd.read_text(encoding="utf-8")

    async def on_step(step: str) -> None:
        typer.echo(f"  {step}...")

    try:
        result = asyncio.run(
            tailor(
                TailorRequest(jd_text=jd_text, track_id=track, feedback=feedback),
                loaded,
                providers.llm,
                providers.embedder,
                on_step=on_step,
            )
        )
    except LLMBudgetExceeded as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    package = result.package
    target = out / f"{slugify(package.job.company)}-{slugify(package.job.title)}"
    write_package(result, target)

    if no_pdf or not result.docx:
        typer.echo("PDF skipped")
    elif not soffice_available(settings.rhapto_soffice_binary):
        typer.echo(f"PDF skipped: LibreOffice ({settings.rhapto_soffice_binary}) not found")
    else:
        try:
            convert_docx_to_pdf(
                target / "resume.docx", target, binary=settings.rhapto_soffice_binary
            )
        except PdfRenderError as exc:
            typer.echo(f"PDF skipped: {exc}")

    report = package.guardrail_report
    typer.echo(f"wrote {target}")
    typer.echo(
        f"llm calls: {package.llm_calls}  guardrails: {'passed' if report.passed else 'BLOCKED'}"
    )
    for v in report.violations:
        typer.echo(f"  [{v.severity}] {v.rule} at {v.path}: {v.message}")
    if not report.passed:
        raise typer.Exit(EXIT_BLOCKED)


@profile_app.command("validate")
def profile_validate(
    path: Path = typer.Argument(Path("./profile"), help="Profile directory"),
) -> None:
    """Validate a profile directory against the schemas."""
    try:
        loaded = load_profile(path)
    except ProfileError as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"ok: {len(loaded.blocks)} blocks, {len(loaded.tracks)} tracks, {len(loaded.bases)} bases, "
        f"{len(loaded.guardrails)} guardrail rules, {len(loaded.answers)} answers"
    )
