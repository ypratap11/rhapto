import logging
import uuid
from pathlib import Path
from typing import Any

import pytest
from helpers import bullet, demo_extract, demo_resume
from helpers_docx import build_fixture_docx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.config import Settings
from rhapto.db.models import Job, User
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.jobs import create_job
from rhapto.engine.compose import AnswerItem, ComposeOutput
from rhapto.engine.providers.errors import ProviderAuthError
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.engine.tune import ProposedEdit, TuneOutput
from rhapto.services import storage as storage_module
from rhapto.services.documents import store_resume_document
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.llm import KEY_UNREADABLE_MESSAGE, LLMNotConfiguredError
from rhapto.services.profile_sync import import_profile_dir
from rhapto.services.secrets import KeyUnreadableError, SecretsError
from rhapto.services.storage import PackageStorage
from rhapto.worker import tasks as worker_tasks
from rhapto.worker.tasks import TASKS, embed_blocks, render_package_pdf, tailor_job

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")


def bad_output() -> dict[str, Any]:
    output = good_output()
    output["sections"][0]["entries"][0]["bullets"][1] = bullet(
        "Cut warehouse cost 25%.", "acme-migration"
    ).model_dump()
    return output


async def _setup(
    session_factory: async_sessionmaker[AsyncSession],
    user: User,
    demo_profile_dir: Path,
    track_id: str | None = None,
    mode: str = "blocks",
) -> tuple[uuid.UUID, uuid.UUID]:
    async with session_factory() as session:
        await import_profile_dir(session, user.id, demo_profile_dir)
        job = await create_job(session, user.id, jd_text=JD)
        task = await task_repo.create_task(
            session,
            user.id,
            "tailor_job",
            {
                "request": {
                    "job_id": str(job.id),
                    "track_id": track_id,
                    "feedback": None,
                    "parent_package_id": None,
                    "mode": mode,
                }
            },
        )
        await session.commit()
        return job.id, task.id


def _ctx(
    session_factory: async_sessionmaker[AsyncSession],
    llm: FakeLLMProvider,
    bus: InMemoryEventBus,
    storage: PackageStorage,
) -> dict[str, Any]:
    async def resolver(
        session: AsyncSession, settings: Settings, user_id: uuid.UUID
    ) -> FakeLLMProvider:
        return llm

    return {
        "session_factory": session_factory,
        "llm_resolver": resolver,
        "embedder": FakeEmbeddingProvider(),
        "event_bus": bus,
        "storage": storage,
        "soffice_binary": "soffice-missing",
        # FakeEmbeddingProvider is 64-dim; opt into reshaping rather than dropping the vector.
        "allow_dimension_mismatch": True,
    }


async def test_registry() -> None:
    assert set(TASKS) == {
        "tailor_job",
        "embed_blocks",
        "render_package_pdf",
        "poll_now",
        "poll_all_sources",
        "poll_user",
        "score_jobs",
        "rescore_jobs",
    }
    assert TASKS["tailor_job"] is tailor_job
    assert TASKS["render_package_pdf"] is render_package_pdf


async def test_tailor_job_success_path(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([demo_extract(), good_output()]), bus, storage),
        task_id=str(task_id),
    )

    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded" and task.finished_at is not None
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert (
            package is not None
            and package.status == "draft"
            and package.version == 1
            and package.llm_calls == 2
        )
        assert package.track_id == "data-pm" and "acme-migration" in package.selection_block_ids
        assert package.docx_path and Path(package.docx_path).exists() and package.pdf_path is None
        job = await session.get(Job, job_id)
        assert job is not None and job.company == "ExampleCo" and job.extracted_json is not None
    steps = [e["step"] for c, e in bus.published if e.get("event") == "progress"]
    assert steps == ["extract", "select", "compose", "validate", "render"]
    assert bus.published[-1][1]["event"] == "done" and bus.published[-1][1]["status"] == "draft"


async def test_tailor_job_without_a_track_uses_the_job_s_best_scoring_track(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """A request with no track must follow the scorer, not the profile's file order.

    `Profile.get_track(None)` falls back to `tracks[0]`, so every tailor run that did not name a
    track was built on whichever track happens to be written first in tracks.yaml -- the fit score
    that picked a different one was computed, stored on the job, and then ignored.
    """
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        # Not the profile's first track, so falling back to tracks[0] cannot accidentally pass.
        job.best_track_id = "ai-pm"
        await session.commit()

    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([demo_extract(), good_output()]), bus, storage),
        task_id=str(task_id),
    )

    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded"
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert package is not None and package.track_id == "ai-pm"


async def test_tailor_job_reuses_the_stored_jd_extract(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """A job already carrying an extract must not pay to extract the same JD again.

    The first run stores `job.extracted_json`; every later run re-derived it from the unchanged
    `jd_text`, spending one of the three LLM calls and ~20s for a result already on the row. The
    fake provider below is primed with the composer output ONLY, so a second extract call would
    exhaust it and fail the task.
    """
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    async with session_factory() as session:
        job = await session.get(Job, job_id)
        assert job is not None
        job.extracted_json = demo_extract().model_dump(mode="json")
        await session.commit()

    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([good_output()]), bus, storage),
        task_id=str(task_id),
    )

    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded", task.error
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert package is not None and package.llm_calls == 1


async def test_tailor_job_blocked_still_creates_package(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir, track_id="ai-pm")
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(
            session_factory,
            FakeLLMProvider([demo_extract(), bad_output(), bad_output()]),
            bus,
            storage,
        ),
        task_id=str(task_id),
    )
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded"
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert (
            package is not None
            and package.status == "blocked"
            and package.llm_calls == 3
            and package.track_id == "ai-pm"
        )
    assert bus.published[-1][1] == {
        "event": "done",
        "package_id": task.result_ref,
        "status": "blocked",
    }


async def test_tailor_job_failure_marks_task_failed(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    _, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([]), bus, storage), task_id=str(task_id)
    )  # fake raises AssertionError
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert (
            task is not None
            and task.status == "failed"
            and "no scripted response" in (task.error or "")
        )
    assert bus.published[-1][1]["event"] == "error"


async def test_tailor_job_fails_cleanly_when_no_llm_is_configured(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """A user with no provider key is a setup problem: the task fails with that message alone, no
    exception class prefix and no pipeline work."""
    _, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    ctx = _ctx(session_factory, FakeLLMProvider([]), bus, storage)

    async def refuse(session: Any, settings: Any, user_id: uuid.UUID) -> None:
        raise LLMNotConfiguredError

    ctx["llm_resolver"] = refuse
    await tailor_job(ctx, task_id=str(task_id))
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "failed"
        assert task.error == "No LLM configured. Add a key in Settings."
    assert bus.published[-1][1] == {
        "event": "error",
        "message": "No LLM configured. Add a key in Settings.",
    }


async def test_tailor_job_redacts_the_key_from_a_provider_failure(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    """The SDK quotes the submitted key in its message; the task row and the event carry the hint.

    `provider_secrets` is stubbed here (it is unit-tested against the real config path in
    test_resolve_llm.py); what this pins is that the worker actually runs both the stored error and
    the published one through `redact`.
    """
    _, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    ctx = _ctx(session_factory, FakeLLMProvider([]), bus, storage)

    async def secrets(session: Any, settings: Any, user_id: uuid.UUID) -> tuple[str, ...]:
        return ("sk-test-abcd1234",)

    async def reject(session: Any, settings: Any, user_id: uuid.UUID) -> None:
        raise ProviderAuthError("openai", "Incorrect API key provided: sk-test-abcd1234")

    monkeypatch.setattr(worker_tasks, "provider_secrets", secrets)
    ctx["llm_resolver"] = reject
    await tailor_job(ctx, task_id=str(task_id))
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "failed"
        assert task.error == "Incorrect API key provided: …1234"
    assert bus.published[-1][1]["message"] == "Incorrect API key provided: …1234"
    assert "sk-test" not in repr(bus.published)


async def test_tailor_job_reports_the_user_facing_message_for_an_unreadable_key(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """A task enqueued before the server secret rotated fails here, and the Jobs page is where the
    user reads why. `KeyUnreadableError` carries the operator's sentence, which names
    RHAPTO_SECRET_KEY and tells the user nothing they can do; both sinks get the API's wording."""
    _, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    ctx = _ctx(session_factory, FakeLLMProvider([]), bus, storage)

    async def rotated(session: Any, settings: Any, user_id: uuid.UUID) -> None:
        raise KeyUnreadableError("stored key cannot be decrypted; RHAPTO_SECRET_KEY changed")

    ctx["llm_resolver"] = rotated
    await tailor_job(ctx, task_id=str(task_id))
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "failed"
        assert task.error == KEY_UNREADABLE_MESSAGE
    assert bus.published[-1][1] == {"event": "error", "message": KEY_UNREADABLE_MESSAGE}
    assert "RHAPTO_SECRET_KEY" not in repr(bus.published)


async def test_tailor_job_keeps_the_operator_message_for_a_misconfigured_secret(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    """The other half of SecretsError is the operator's to fix and keeps its own hint, exactly as
    `api/errors.py` decides it."""
    _, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    ctx = _ctx(session_factory, FakeLLMProvider([]), bus, storage)

    async def misconfigured(session: Any, settings: Any, user_id: uuid.UUID) -> None:
        raise SecretsError("RHAPTO_SECRET_KEY is not a valid Fernet key; generate one with: ...")

    ctx["llm_resolver"] = misconfigured
    await tailor_job(ctx, task_id=str(task_id))
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.error is not None
        assert "not a valid Fernet key" in task.error


async def test_tailor_job_with_bad_task_id_publishes_error(session_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(_ctx(session_factory, FakeLLMProvider([]), bus, storage), task_id="not-a-uuid")
    assert bus.published[-1][0] == "task:not-a-uuid"
    assert bus.published[-1][1]["event"] == "error"


async def test_tailor_job_regeneration_increments_version(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([demo_extract(), good_output()]), bus, storage),
        task_id=str(task_id),
    )
    async with session_factory() as session:
        first = (await package_repo.list_packages_for_job(session, user.id, job_id))[0]
        task2 = await task_repo.create_task(
            session,
            user.id,
            "tailor_job",
            {
                "request": {
                    "job_id": str(job_id),
                    "track_id": None,
                    "feedback": "lean on migration",
                    "parent_package_id": str(first.id),
                }
            },
        )
        await session.commit()
    llm = FakeLLMProvider([demo_extract(), good_output()])
    await tailor_job(_ctx(session_factory, llm, bus, storage), task_id=str(task2.id))
    async with session_factory() as session:
        packages = await package_repo.list_packages_for_job(session, user.id, job_id)
        assert [p.version for p in packages] == [1, 2] and packages[1].parent_package_id == first.id
    assert "lean on migration" in llm.calls[1].messages[0].content


async def test_embed_blocks_stores_vectors(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    async with session_factory() as session:
        await import_profile_dir(session, user.id, demo_profile_dir)
        await session.commit()
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await embed_blocks(
        _ctx(session_factory, FakeLLMProvider([]), bus, storage),
        user_id=str(user.id),
        block_ids=["acme-migration", "ghost"],
    )
    async with session_factory() as session:
        from rhapto.db.repositories.profile import get_block

        row = await get_block(session, user.id, "acme-migration")
        assert row is not None and row.embedding is not None and len(list(row.embedding)) == 384
        other = await get_block(session, user.id, "cred-pmp")
        assert other is not None and other.embedding is None


async def test_render_package_pdf_sets_pdf_path(
    session_factory,
    user: User,
    demo_profile_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # type: ignore[no-untyped-def]
    job_id, task_id = await _setup(session_factory, user, demo_profile_dir)
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([demo_extract(), good_output()]), bus, storage),
        task_id=str(task_id),
    )
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.result_ref is not None
        package_id = task.result_ref

    def fake_convert(
        docx_path: Path, out_dir: Path, binary: str = "soffice", timeout: int = 180
    ) -> Path:
        pdf = out_dir / "resume.pdf"
        pdf.write_bytes(b"%PDF")
        return pdf

    monkeypatch.setattr(storage_module, "soffice_available", lambda binary: True)
    monkeypatch.setattr(storage_module, "convert_docx_to_pdf", fake_convert)

    await render_package_pdf(
        _ctx(session_factory, FakeLLMProvider([]), bus, storage), package_id=package_id
    )

    async with session_factory() as session:
        package = await package_repo.get_package(session, user.id, uuid.UUID(package_id))
        assert package is not None and package.pdf_path is not None
        assert Path(package.pdf_path).exists()


async def test_render_package_pdf_ignores_unknown_id(session_factory, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    bus, storage = InMemoryEventBus(), PackageStorage(tmp_path / "pkg")
    await render_package_pdf(
        _ctx(session_factory, FakeLLMProvider([]), bus, storage), package_id=str(uuid.uuid4())
    )


async def test_embed_blocks_drops_mismatched_vectors_by_default(
    session_factory,  # type: ignore[no-untyped-def]
    user: User,
    demo_profile_dir: Path,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A provider whose width is not EMBEDDING_DIMENSIONS means a misconfigured deployment:
    store nothing and say so loudly rather than silently reshaping the vector."""
    async with session_factory() as session:
        await import_profile_dir(session, user.id, demo_profile_dir)
        await session.commit()
    ctx = _ctx(session_factory, FakeLLMProvider([]), InMemoryEventBus(), PackageStorage(tmp_path))
    del ctx["allow_dimension_mismatch"]  # production default
    with caplog.at_level(logging.ERROR, logger="rhapto.worker"):
        await embed_blocks(ctx, user_id=str(user.id), block_ids=["acme-migration"])
    async with session_factory() as session:
        from rhapto.db.repositories.profile import get_block

        row = await get_block(session, user.id, "acme-migration")
        assert row is not None and row.embedding is None
    assert "expected 384" in caplog.text and "acme-migration" in caplog.text


async def test_embed_blocks_logs_and_returns_on_a_bad_user_id(
    session_factory,  # type: ignore[no-untyped-def]
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    ctx = _ctx(session_factory, FakeLLMProvider([]), InMemoryEventBus(), PackageStorage(tmp_path))
    with caplog.at_level(logging.ERROR, logger="rhapto.worker"):
        await embed_blocks(ctx, user_id="not-a-uuid", block_ids=["acme-migration"])
    assert "embed_blocks failed" in caplog.text


CLEAN_BULLET = "Led the Snowflake migration for 12 teams, reducing warehouse cost 30%."


def tune_output() -> dict[str, Any]:
    return TuneOutput(
        edits=[ProposedEdit(paragraph_id="p9", text=CLEAN_BULLET, reason="mirrors the JD")],
        cover_note="I have led Snowflake migrations end to end for platform teams.",
        change_log="Emphasised the migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")


async def test_tailor_job_tune_mode_loads_the_uploaded_document(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    storage = PackageStorage(tmp_path / "pkg")
    _, task_id = await _setup(session_factory, user, demo_profile_dir, mode="tune")
    async with session_factory() as session:
        await store_resume_document(
            session, storage, user.id, "Maya_Chen_Resume.docx", build_fixture_docx()
        )
        await session.commit()
    bus = InMemoryEventBus()
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([demo_extract(), tune_output()]), bus, storage),
        task_id=str(task_id),
    )
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "succeeded", task.error if task else None
        package = await package_repo.get_package(session, user.id, uuid.UUID(task.result_ref or ""))
        assert package is not None and package.mode == "tune" and package.status == "draft"
        assert [e["paragraph_id"] for e in package.edits_json or []] == ["p9"]
        assert package.source_document_json is not None
        assert package.selection_block_ids == []
        assert package.docx_path and Path(package.docx_path).exists()
    steps = [e["step"] for _, e in bus.published if e.get("event") == "progress"]
    assert steps == ["extract", "tune", "validate", "render"]


async def test_tailor_job_tune_mode_without_a_document_fails_the_task(
    session_factory, user: User, demo_profile_dir: Path, tmp_path: Path
) -> None:  # type: ignore[no-untyped-def]
    storage = PackageStorage(tmp_path / "pkg")
    _, task_id = await _setup(session_factory, user, demo_profile_dir, mode="tune")
    bus = InMemoryEventBus()
    await tailor_job(
        _ctx(session_factory, FakeLLMProvider([demo_extract(), tune_output()]), bus, storage),
        task_id=str(task_id),
    )
    async with session_factory() as session:
        task = await task_repo.get_task(session, user.id, task_id)
        assert task is not None and task.status == "failed"
        assert "resume document" in (task.error or "")
