from __future__ import annotations

import asyncio
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import typer
from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from rhapto.config import Settings, get_settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.pipeline import LLMBudgetExceeded, TailorResult, tailor
from rhapto.engine.providers.anthropic import AnthropicProvider
from rhapto.engine.providers.embeddings import EmbeddingProvider, FastEmbedProvider
from rhapto.engine.providers.llm import LLMProvider, MalformedOutputError
from rhapto.engine.render.pdf import PdfRenderError, convert_docx_to_pdf, soffice_available
from rhapto.engine.types import Profile, ProfileError, TailorRequest
from rhapto.profile.loader import load_profile
from rhapto.services.profile_sync import export_profile_dir, import_profile_dir

app = typer.Typer(
    no_args_is_help=True, help="Rhapto: human-in-the-loop AI job application copilot."
)
profile_app = typer.Typer(no_args_is_help=True, help="Inspect and validate a profile directory.")
app.add_typer(profile_app, name="profile")

EXIT_BLOCKED = 3  # 1 is an error, 2 is a click/typer usage error


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
    jd: Path = typer.Option(..., "--jd", help="Job description text file"),
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    track: str | None = typer.Option(None, "--track", help="Track id (default: first track)"),
    out: Path = typer.Option(
        Path("out"), "--out", help="Output root; a <company>-<role> folder is created"
    ),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF conversion"),
    feedback: str | None = typer.Option(None, "--feedback", help="Regeneration feedback"),
) -> None:
    """Tailor a resume package for one job description."""
    if not jd.is_file():
        typer.echo(f"error: job description file not found: {jd}", err=True)
        raise typer.Exit(1)
    settings = get_settings()
    try:
        loaded = load_profile(profile)
    except ProfileError as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(1) from exc
    try:
        providers = build_providers(settings)
    except typer.BadParameter as exc:
        typer.echo(f"error: {exc.message}", err=True)
        raise typer.Exit(1) from exc
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
    except (LLMBudgetExceeded, MalformedOutputError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc

    package = result.package
    target = out / f"{slugify(package.job.company)}-{slugify(package.job.title)}"
    write_package(result, target)

    if not result.docx:
        typer.echo("PDF skipped: no DOCX was rendered (provenance violation; see guardrail report)")
    elif no_pdf:
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


db_app = typer.Typer(no_args_is_help=True, help="Database maintenance.")
app.add_typer(db_app, name="db")


def alembic_config() -> Config:
    """alembic.ini lives two directories above the package (apps/api) in a checkout and at /app in the image."""
    root = Path(__file__).resolve().parents[3]
    return Config(str(root / "alembic.ini"))


def run_migrations(database_url: str) -> None:
    os.environ["DATABASE_URL"] = database_url
    command.upgrade(alembic_config(), "head")


def mask_url(url: str) -> str:
    """Hide the password in a database URL so it is safe to print."""
    return re.sub(r"(//[^:/?#@]+):[^@]*@", r"\1:***@", url)


@db_app.command("upgrade")
def db_upgrade() -> None:
    """Apply database migrations."""
    url = get_settings().database_url
    try:
        run_migrations(url)
    except (OSError, SQLAlchemyError) as exc:
        typer.echo(
            f"error: cannot reach the database at {mask_url(url)}; "
            "run `docker compose up -d db redis`",
            err=True,
        )
        raise typer.Exit(1) from exc
    typer.echo("database is up to date")


async def _with_user(
    database_url: str,
    email: str,
    fn: Callable[[AsyncSession, uuid.UUID], Awaitable[Profile]],
) -> Profile:
    engine = make_engine(database_url)
    try:
        async with make_session_factory(engine)() as session:
            user = await get_or_create_user(session, email)
            result = await fn(session, user.id)
            await session.commit()
            return result
    finally:
        await engine.dispose()


@profile_app.command("import")
def profile_import(
    path: Path = typer.Argument(
        Path("./profile"), help="Profile directory to import (replaces the stored profile)"
    ),
) -> None:
    """Import a YAML profile directory into the database, replacing what is stored."""
    settings = get_settings()
    try:
        profile = asyncio.run(
            _with_user(
                settings.database_url,
                settings.rhapto_user_email,
                lambda s, uid: import_profile_dir(s, uid, path),
            )
        )
    except ProfileError as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"imported {len(profile.blocks)} blocks, {len(profile.tracks)} tracks for {settings.rhapto_user_email}"
    )


@profile_app.command("export")
def profile_export(
    path: Path = typer.Argument(Path("./profile"), help="Directory to write YAML files into"),
) -> None:
    """Export the stored profile to a YAML directory."""
    settings = get_settings()
    try:
        profile = asyncio.run(
            _with_user(
                settings.database_url,
                settings.rhapto_user_email,
                lambda s, uid: export_profile_dir(s, uid, path),
            )
        )
    except ProfileError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"exported {len(profile.blocks)} blocks to {path}")
