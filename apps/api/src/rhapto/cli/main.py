from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import typer
from alembic.config import Config
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic import command
from rhapto.config import Settings, get_settings
from rhapto.db.session import make_engine, make_session_factory
from rhapto.engine.document import parse_docx
from rhapto.engine.pipeline import LLMBudgetExceeded, TailorResult, tailor
from rhapto.engine.providers.embeddings import EmbeddingProvider, FastEmbedProvider
from rhapto.engine.providers.fake import FakeEmbeddingProvider
from rhapto.engine.providers.llm import LLMProvider, MalformedOutputError
from rhapto.engine.providers.registry import PROVIDERS, build_llm, model_for, provider_ids
from rhapto.engine.render.pdf import PdfRenderError, convert_docx_to_pdf, soffice_available
from rhapto.engine.scoring import (
    best_track,
    bucket_for,
    location_preference_from_answers,
    location_tier,
    score_job,
    track_text,
)
from rhapto.engine.types import Profile, ProfileError, TailorRequest
from rhapto.profile.loader import load_profile
from rhapto.services.accounts import ensure_account
from rhapto.services.discovery.http import DiscoveryHttp
from rhapto.services.discovery.posting import Posting
from rhapto.services.discovery.sources import get_source
from rhapto.services.discovery.sources.base import SourceError
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


def build_providers(
    settings: Settings, provider: str | None = None, model: str | None = None
) -> Providers:
    """The adapters for one CLI run. The CLI never reads the database: the key always comes from
    the environment, for whichever provider the flags (or RHAPTO_LLM_PROVIDER) name."""
    chosen = provider or settings.rhapto_llm_provider
    info = PROVIDERS.get(chosen)
    if info is None:
        raise typer.BadParameter(
            f"unknown provider {chosen!r}; choose from {', '.join(provider_ids())}"
        )
    # Settings field names are the env var names lowercased (ANTHROPIC_API_KEY → anthropic_api_key).
    api_key = str(getattr(settings, info.env_key.lower(), "") or "")
    if not api_key:
        raise typer.BadParameter(f"{info.env_key} is not set; put it in .env or the environment")
    # RHAPTO_LLM_MODEL names a model for RHAPTO_LLM_PROVIDER; `model_for` leaves it behind when
    # --provider points somewhere else rather than sending "claude-sonnet-5" to OpenAI, and fills in
    # the provider's default when neither the flag nor the env names one.
    return Providers(
        llm=build_llm(info.id, model_for(info.id, model or settings.rhapto_llm_model), api_key),
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
    document: Path | None = typer.Option(
        None,
        "--document",
        exists=True,
        dir_okay=False,
        help="Your resume .docx; switches on tune mode",
    ),
    mode: Literal["blocks", "tune"] | None = typer.Option(
        None, "--mode", help="blocks|tune (default: tune if --document is given, else blocks)"
    ),
    out: Path = typer.Option(
        Path("out"), "--out", help="Output root; a <company>-<role> folder is created"
    ),
    no_pdf: bool = typer.Option(False, "--no-pdf", help="Skip PDF conversion"),
    feedback: str | None = typer.Option(None, "--feedback", help="Regeneration feedback"),
    provider: str | None = typer.Option(
        None, "--provider", help="LLM provider (default: RHAPTO_LLM_PROVIDER)"
    ),
    model: str | None = typer.Option(
        None, "--model", help="Model id (default: the provider's default)"
    ),
) -> None:
    """Tailor a resume package for one job description."""
    if not jd.is_file():
        typer.echo(f"error: job description file not found: {jd}", err=True)
        raise typer.Exit(1)
    if mode == "tune" and document is None:
        raise typer.BadParameter("--mode tune requires --document")
    resolved_mode: Literal["blocks", "tune"] = mode or ("tune" if document else "blocks")
    settings = get_settings()
    try:
        loaded = load_profile(profile)
    except ProfileError as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(1) from exc
    try:
        providers = build_providers(settings, provider, model)
    except typer.BadParameter as exc:
        typer.echo(f"error: {exc.message}", err=True)
        raise typer.Exit(1) from exc
    jd_text = jd.read_text(encoding="utf-8")
    if resolved_mode == "tune":
        assert document is not None  # guaranteed by the --mode/--document check above
        data = document.read_bytes()
        try:
            source_document = parse_docx(data, document.name)
        except Exception as exc:  # python-docx raises several types for a corrupt file
            typer.echo(f"error: could not read {document}: is it a valid .docx?", err=True)
            raise typer.Exit(1) from exc
        request = TailorRequest(
            jd_text=jd_text,
            track_id=track,
            feedback=feedback,
            mode="tune",
            source_document=source_document,
            source_docx=data,
        )
    else:
        request = TailorRequest(jd_text=jd_text, track_id=track, feedback=feedback)

    async def on_step(step: str) -> None:
        typer.echo(f"  {step}...")

    try:
        result = asyncio.run(
            tailor(
                request,
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
        typer.echo("PDF skipped: no DOCX was rendered (guardrails failed; see the report)")
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

accounts_app = typer.Typer(no_args_is_help=True, help="Account maintenance.")
app.add_typer(accounts_app, name="accounts")


@accounts_app.command("set-email")
def accounts_set_email(
    old_email: str = typer.Argument(...), new_email: str = typer.Argument(...)
) -> None:
    """Rename an account's email -- run before flipping RHAPTO_AUTH_MODE to access, so the owner's
    bootstrapped account matches his Cloudflare Access email exactly."""
    settings = Settings()
    new_casefolded = new_email.casefold()

    async def rename() -> str:
        engine = make_engine(settings.database_url)
        try:
            async with make_session_factory(engine)() as session:
                from sqlalchemy import select as sa_select

                from rhapto.db.models import User

                user = await session.scalar(
                    sa_select(User).where(User.email == old_email.casefold())
                )
                if user is None:
                    return "not_found"
                taken = await session.scalar(
                    sa_select(User).where(User.email == new_casefolded, User.id != user.id)
                )
                if taken is not None:
                    return "taken"
                user.email = new_casefolded
                await session.commit()
                return "ok"
        finally:
            await engine.dispose()

    result = asyncio.run(rename())
    if result == "not_found":
        typer.echo(f"error: no account found with email {old_email!r}", err=True)
        raise typer.Exit(1)
    if result == "taken":
        typer.echo(f"error: {new_email!r} is already in use by another account", err=True)
        raise typer.Exit(1)
    typer.echo(f"renamed {old_email} -> {new_email}")


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
    # Construct a bare Settings() to read only database_url; this command is invoked during
    # Docker startup (rhapto db upgrade && uvicorn ...) before secrets are validated. The
    # rhapto_secret_key is only needed by the API and worker entrypoints, not by this
    # database maintenance step -- so it must not block a migration.
    settings = Settings()
    url = settings.database_url
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
            user = await ensure_account(session, email)
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
    # Construct a bare Settings() to read only database_url and rhapto_user_email (which
    # has a default); this command does not need rhapto_secret_key, which is only used by
    # the API and worker entrypoints.
    settings = Settings()
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
    # Construct a bare Settings() to read only database_url and rhapto_user_email (which
    # has a default); this command does not need rhapto_secret_key, which is only used by
    # the API and worker entrypoints.
    settings = Settings()
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


def build_discovery_http(settings: Settings) -> DiscoveryHttp:
    return DiscoveryHttp(
        user_agent=settings.rhapto_discovery_user_agent,
        base_override=settings.rhapto_discovery_base_override,
    )


def build_embedder(settings: Settings, kind: str) -> EmbeddingProvider:
    if kind == "fake":
        return FakeEmbeddingProvider(dimensions=384)
    return FastEmbedProvider(settings.rhapto_embedding_model)


async def _score_postings(
    profile: Profile, postings: list[tuple[str, Posting]], embedder: EmbeddingProvider
) -> list[dict[str, Any]]:
    tracks = profile.tracks
    vectors = await embedder.embed(
        [track_text(t) for t in tracks] + [f"{p.title}\n{p.jd_text}" for _, p in postings]
    )
    track_vectors = {t.id: v for t, v in zip(tracks, vectors[: len(tracks)], strict=True)}
    preference = location_preference_from_answers(profile.answers)
    rows: list[dict[str, Any]] = []
    for (source, posting), vector in zip(postings, vectors[len(tracks) :], strict=True):
        tier = location_tier(posting.location, preference)
        scores = score_job(
            posting.title,
            posting.jd_text,
            vector,
            tracks,
            track_vectors,
            tier,
            has_location_preference=bool(preference.terms),
        )
        best = best_track(scores, tracks)
        rows.append(
            {
                "source": source,
                "company": posting.company,
                "title": posting.title,
                "location": posting.location,
                "location_tier": tier,
                "url": posting.url,
                "fit": best.fit_score if best else 0,
                "track": best.track_id if best else None,
                "bucket": bucket_for(best, tracks, rescued=False),
            }
        )
    return sorted(rows, key=lambda r: -r["fit"])


@app.command(name="discover")
def discover_cmd(
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    source: str | None = typer.Option(None, "--source", help="Poll one source only"),
    board: str | None = typer.Option(None, "--board", help="Board slug for a single board source"),
    as_json: bool = typer.Option(False, "--json", help="Print a JSON array"),
    embedder_kind: str = typer.Option("fastembed", "--embedder", hidden=True),
) -> None:
    """Fetch the watchlist boards and enabled aggregators, score every posting, print them by fit.

    Nothing is stored.
    """
    settings = get_settings()
    try:
        loaded = load_profile(profile)
    except ProfileError as exc:
        typer.echo(f"profile error: {exc}", err=True)
        raise typer.Exit(1) from exc
    track_keywords = [k for t in loaded.tracks for k in t.keywords]
    specs: list[tuple[str, str | None, str | None, list[str]]] = []
    if source:
        specs.append((source, board, board, track_keywords if board is None else []))
    else:
        specs.extend((e.source, e.board, e.company, list(e.keywords)) for e in loaded.watchlist)
        specs.extend(
            (a.source, None, None, list(a.keywords) or track_keywords)
            for a in loaded.aggregators
            if a.enabled
        )
    http = build_discovery_http(settings)

    async def run() -> tuple[list[tuple[str, Posting]], list[str]]:
        found: list[tuple[str, Posting]] = []
        errors: list[str] = []
        try:
            for name, slug, company, keywords in specs:
                try:
                    for p in await get_source(name).fetch(http, board=slug, keywords=keywords):
                        found.append((name, p.model_copy(update={"company": company or p.company})))
                except SourceError as exc:
                    errors.append(f"{name}/{slug or '-'}: {exc}")
                except Exception as exc:  # a bug in one adapter must not take the others down
                    errors.append(f"{name}/{slug or '-'}: {type(exc).__name__}: {exc}")
        finally:
            await http.aclose()
        return found, errors

    found, errors = asyncio.run(run())
    for line in errors:
        typer.echo(f"error: {line}", err=True)
    rows = (
        asyncio.run(_score_postings(loaded, found, build_embedder(settings, embedder_kind)))
        if found
        else []
    )
    if as_json:
        typer.echo(json.dumps(rows, indent=1))
    else:
        for r in rows:
            typer.echo(
                f"{r['fit']:>3}  {r['track'] or '-':<14} {r['company']} | {r['title']} | "
                f"{r['location'] or '-'}  {r['url']}"
            )
        typer.echo(f"{len(rows)} postings from {len(specs) - len(errors)} of {len(specs)} sources")
    if specs and len(errors) == len(specs):
        raise typer.Exit(1)


@app.command(name="score")
def score_cmd(
    jd: Path = typer.Option(..., "--jd", help="Job description text file"),
    profile: Path = typer.Option(Path("./profile"), "--profile", help="Profile directory"),
    embedder_kind: str = typer.Option("fastembed", "--embedder", hidden=True),
) -> None:
    """Print the per-track fit breakdown for one job description."""
    settings = get_settings()
    loaded = load_profile(profile)
    text = jd.read_text(encoding="utf-8")
    embedder = build_embedder(settings, embedder_kind)

    async def run() -> None:
        vectors = await embedder.embed([track_text(t) for t in loaded.tracks] + [text])
        track_vectors = {t.id: v for t, v in zip(loaded.tracks, vectors[:-1], strict=True)}
        title = text.strip().splitlines()[0][:200] if text.strip() else None
        preference = location_preference_from_answers(loaded.answers)
        for s in score_job(
            title,
            text,
            vectors[-1],
            loaded.tracks,
            track_vectors,
            has_location_preference=bool(preference.terms),
        ):
            typer.echo(
                f"{s.track_id:<14} fit={s.fit_score:>3} semantic={s.semantic:>3} "
                f"keywords={s.keywords:>3} matched={', '.join(s.matched) or '-'}"
            )

    asyncio.run(run())
