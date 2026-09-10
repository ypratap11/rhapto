import logging
import uuid
from pathlib import Path
from typing import Any

import pytest
from helpers import bullet, demo_extract, demo_resume
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job, User
from rhapto.db.repositories import packages as package_repo
from rhapto.db.repositories import tasks as task_repo
from rhapto.db.repositories.jobs import create_job
from rhapto.engine.compose import AnswerItem, ComposeOutput
from rhapto.engine.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from rhapto.services import storage as storage_module
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.profile_sync import import_profile_dir
from rhapto.services.storage import PackageStorage
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
    return {
        "session_factory": session_factory,
        "llm": llm,
        "embedder": FakeEmbeddingProvider(),
        "event_bus": bus,
        "storage": storage,
        "soffice_binary": "soffice-missing",
        # FakeEmbeddingProvider is 64-dim; opt into reshaping rather than dropping the vector.
        "allow_dimension_mismatch": True,
    }


async def test_registry() -> None:
    assert set(TASKS) == {"tailor_job", "embed_blocks", "render_package_pdf"}
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
