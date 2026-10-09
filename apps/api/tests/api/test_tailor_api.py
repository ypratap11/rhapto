import asyncio
import json
import uuid
from typing import Any

import httpx
import pytest
from helpers import default_tailor_script, demo_extract
from helpers_docx import build_fixture_docx
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from rhapto.db.models import Job
from rhapto.db.repositories.llm_settings import upsert_llm_settings
from rhapto.db.repositories.users import get_or_create_user
from rhapto.engine.compose import AnswerItem
from rhapto.engine.tune import ProposedEdit, TuneOutput
from rhapto.services.eventbus import InMemoryEventBus
from rhapto.services.storage import PackageStorage

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


async def _job(client: httpx.AsyncClient) -> str:
    response = await client.post("/api/v1/jobs", json={"jd_text": JD})
    assert response.status_code == 201
    return str(response.json()["id"])


def _events(raw: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for block in raw.strip().split("\n\n"):
        event, data = "", ""
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data += line[5:].strip()
        if event:
            out.append((event, json.loads(data)))
    return out


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_runs_inline_and_task_succeeds(
    client: httpx.AsyncClient, fake_llm, llm_resolver
) -> None:  # type: ignore[no-untyped-def]
    fake_llm.script(*default_tailor_script())
    job_id = await _job(client)
    accepted = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert accepted.status_code == 202, accepted.text
    task = accepted.json()
    assert task["type"] == "tailor_job" and task["status"] == "succeeded" and task["result_ref"]
    fetched = (await client.get(f"/api/v1/tasks/{task['id']}")).json()
    assert fetched["progress"]["step"] == "render" and fetched["finished_at"]
    job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert (
        job["latest_package"]["id"] == task["result_ref"]
        and job["latest_package"]["status"] == "draft"
    )
    assert (
        job["company"] == "ExampleCo"
        and job["extracted"]["title"] == "Data Platform Program Manager"
    )
    # The worker picked its provider per task rather than reading one off the ctx.
    assert len(llm_resolver.calls) == 1


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_is_409_when_the_stored_key_cannot_be_decrypted(
    client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    user_id: uuid.UUID,
) -> None:
    """A rotated server secret must not silently fall back to the environment's key: the user chose
    a provider, and they have to re-enter the key for it."""
    async with session_factory() as session:
        await get_or_create_user(session, "test@example.com")
        await upsert_llm_settings(
            session,
            user_id,
            provider="openai",
            model="gpt-5",
            api_key_encrypted="not-a-fernet-token",
        )
        await session.commit()
    job_id = await _job(client)
    response = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "llm_key_unreadable" and "Settings" in body["detail"]


@pytest.mark.usefixtures("imported_profile")
@pytest.mark.parametrize("env_llm_key", [""], indirect=True)
async def test_tailor_is_409_when_no_llm_is_configured(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    response = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["code"] == "llm_not_configured" and "Settings" in body["detail"]


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_validates_track_and_parent(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    assert (
        await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"track_id": "nope"})
    ).status_code == 422
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"parent_package_id": missing})
    ).status_code == 404
    assert (await client.post(f"/api/v1/jobs/{missing}/tailor", json={})).status_code == 404


async def test_tailor_without_profile_is_refused_up_front(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    response = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert response.status_code == 422


@pytest.mark.usefixtures("imported_profile")
async def test_events_replays_finished_state_and_closes(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    fake_llm.script(*default_tailor_script())
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    async with client.stream("GET", f"/api/v1/tasks/{task['id']}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = (await response.aread()).decode()
    events = _events(raw)
    assert events[0][0] == "state" and events[0][1]["status"] == "succeeded"
    assert len(events) == 1


async def test_events_streams_progress_for_running_task(
    client: httpx.AsyncClient, event_bus: InMemoryEventBus, session_factory, user_id
) -> None:  # type: ignore[no-untyped-def]
    from rhapto.db.repositories.tasks import create_task, mark_running

    async with session_factory() as session:
        task = await create_task(session, user_id, "tailor_job", {"request": {}})
        mark_running(task)
        await session.commit()
        task_id = str(task.id)

    async def publish_later() -> None:
        while event_bus.subscriber_count(f"task:{task_id}") == 0:
            await asyncio.sleep(0.01)
        await event_bus.publish(f"task:{task_id}", {"event": "progress", "step": "extract"})
        await event_bus.publish(
            f"task:{task_id}", {"event": "done", "package_id": "p", "status": "draft"}
        )

    publisher = asyncio.create_task(publish_later())
    async with client.stream("GET", f"/api/v1/tasks/{task_id}/events") as response:
        raw = (await asyncio.wait_for(response.aread(), timeout=5)).decode()
    await publisher
    events = _events(raw)
    assert [e for e, _ in events] == ["state", "progress", "done"]
    assert events[1][1]["step"] == "extract"


async def test_events_unknown_task_404(client: httpx.AsyncClient) -> None:
    assert (
        await client.get("/api/v1/tasks/00000000-0000-0000-0000-000000000000/events")
    ).status_code == 404


@pytest.mark.usefixtures("imported_profile")
async def test_repeated_streams_do_not_exhaust_the_pool(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    """Each stream must release its connection; 20 sequential streams outlast the 5+10 pool."""
    fake_llm.script(*default_tailor_script())
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    for _ in range(20):
        async with client.stream("GET", f"/api/v1/tasks/{task['id']}/events") as response:
            assert response.status_code == 200
            raw = (await asyncio.wait_for(response.aread(), timeout=5)).decode()
        events = _events(raw)
        assert [name for name, _ in events] == ["state"]
        assert events[0][1]["status"] == "succeeded"


# --- tune mode ---------------------------------------------------------------------------------

CLEAN_BULLET = "Led the Snowflake migration for 12 teams, reducing warehouse cost 30%."
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def tune_output() -> dict[str, Any]:
    return TuneOutput(
        edits=[ProposedEdit(paragraph_id="p9", text=CLEAN_BULLET, reason="mirrors the JD")],
        cover_note="I have led Snowflake migrations end to end for platform teams.",
        change_log="Emphasised the migration.",
        answers=[AnswerItem(key="why_this_company", value="Data.")],
    ).model_dump(mode="json")


async def _upload_document(client: httpx.AsyncClient) -> None:
    files = {"file": ("Maya_Chen_Resume.docx", build_fixture_docx(), DOCX_MIME)}
    response = await client.post("/api/v1/profile/resume-document", files=files)
    assert response.status_code == 201, response.text


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_defaults_to_tune_when_document_exists(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    await _upload_document(client)
    fake_llm.script(demo_extract(), tune_output())
    job_id = await _job(client)
    accepted = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert accepted.status_code == 202, accepted.text
    task = accepted.json()
    assert task["status"] == "succeeded", task
    package = (await client.get(f"/api/v1/packages/{task['result_ref']}")).json()
    assert package["mode"] == "tune" and package["status"] == "draft"
    assert [e["paragraph_id"] for e in package["edits"]] == ["p9"]
    assert package["edits"][0]["after"] == CLEAN_BULLET
    assert package["source_document"]["filename"] == "Maya_Chen_Resume.docx"
    assert package["resume"]["summary"][0]["source_block_id"].startswith("p")
    docx = await client.get(f"/api/v1/packages/{task['result_ref']}/files/resume.docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    listed = (await client.get("/api/v1/packages")).json()
    assert [item["mode"] for item in listed] == ["tune"]


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_refuses_tune_when_the_row_outlived_its_file(
    client: httpx.AsyncClient, storage: PackageStorage, user_id: uuid.UUID
) -> None:
    """The `resume_documents` row and the file on the volume can disagree, and only the file can be
    tailored. The dashboard checklist learned this after a row outlived its file for three days;
    this endpoint had not, so pressing Tailor enqueued a task that died in the worker with
    "no resume document stored" instead of saying so up front. Deleting the file while leaving the
    row is exactly the state the live deployment was found in.
    """
    await _upload_document(client)
    storage.delete_document(user_id)

    job_id = await _job(client)
    explicit = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"mode": "tune"})
    assert explicit.status_code == 422, explicit.text
    assert "resume document" in explicit.json()["detail"]


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_mode_tune_without_document_is_422(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    response = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"mode": "tune"})
    assert response.status_code == 422, response.text
    assert "resume document" in response.json()["detail"]


@pytest.mark.usefixtures("imported_profile")
async def test_tailor_mode_blocks_still_works_with_document(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    await _upload_document(client)
    fake_llm.script(*default_tailor_script())
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"mode": "blocks"})).json()
    assert task["status"] == "succeeded", task
    package = (await client.get(f"/api/v1/packages/{task['result_ref']}")).json()
    assert package["mode"] == "blocks" and package["edits"] == []
    assert package["source_document"] is None


async def _tune_run(client: httpx.AsyncClient, fake_llm: Any) -> tuple[str, dict[str, Any]]:
    await _upload_document(client)
    fake_llm.script(demo_extract(), tune_output())
    job_id = await _job(client)
    accepted = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert accepted.status_code == 202, accepted.text
    task = accepted.json()
    assert task["status"] == "succeeded", task
    package = (await client.get(f"/api/v1/packages/{task['result_ref']}")).json()
    return job_id, package


async def test_tune_tailor_completes_with_no_blocks_and_no_tracks(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    """The coach's fallback path: the import failed, the document is stored, nothing else is."""
    _, package = await _tune_run(client, fake_llm)
    assert package["mode"] == "tune" and package["status"] == "draft"
    assert package["track_id"] == ""


@pytest.mark.usefixtures("imported_profile")
async def test_tune_tailor_completes_with_no_tracks(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    for track_id in ("data-pm", "ai-pm"):
        assert (await client.delete(f"/api/v1/profile/tracks/{track_id}")).status_code == 204
    _, package = await _tune_run(client, fake_llm)
    assert package["status"] == "draft" and package["track_id"] == ""


@pytest.mark.usefixtures("imported_profile")
async def test_tune_tailor_survives_a_best_track_id_naming_a_deleted_track(
    client: httpx.AsyncClient,
    fake_llm,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:  # type: ignore[no-untyped-def]
    await _upload_document(client)
    job_id = await _job(client)
    async with session_factory() as session:
        await session.execute(
            update(Job).where(Job.id == uuid.UUID(job_id)).values(best_track_id="gone-track")
        )
        await session.commit()
    fake_llm.script(demo_extract(), tune_output())
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "succeeded", task
    package = (await client.get(f"/api/v1/packages/{task['result_ref']}")).json()
    assert package["status"] == "draft" and package["track_id"] == "data-pm"


async def test_tune_patch_works_with_no_library(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
    _, package = await _tune_run(client, fake_llm)
    body = {
        "edits": [
            {
                "paragraph_id": "p9",
                "after": "Led the Snowflake migration for 12 teams and cut warehouse cost 30%.",
            }
        ]
    }
    patched = await client.patch(f"/api/v1/packages/{package['id']}", json=body)
    assert patched.status_code in (200, 201), patched.text
    new = patched.json()
    assert new["version"] == package["version"] + 1 and new["track_id"] == ""


async def test_a_package_with_an_empty_track_id_regenerates(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    job_id, package = await _tune_run(client, fake_llm)
    fake_llm.script(tune_output())  # the stored extract is reused: one call
    body = {
        "feedback": "lean harder on the migration",
        "parent_package_id": package["id"],
        "track_id": None,
    }
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json=body)).json()
    assert task["status"] == "succeeded", task
    again = (await client.get(f"/api/v1/packages/{task['result_ref']}")).json()
    assert again["version"] == 2 and again["track_id"] == ""
    # And why the web maps "" to null: the API still rejects an unknown track named explicitly.
    rejected = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={**body, "track_id": ""})
    assert rejected.status_code == 422


async def test_blocks_mode_without_a_library_is_422_for_the_resolved_default_mode(
    client: httpx.AsyncClient,
) -> None:
    """No `mode` in the body and no stored document resolves to blocks, and this user has neither
    blocks nor tracks: a plain 422 now, not a 202 whose task dies in the worker."""
    job_id = await _job(client)
    response = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})
    assert response.status_code == 422, response.text
    assert "resume document" in response.json()["detail"]
    explicit = await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"mode": "blocks"})
    assert explicit.status_code == 422


@pytest.mark.parametrize("env_llm_key", [""], indirect=True)
async def test_blocks_mode_422_comes_before_the_key_check(client: httpx.AsyncClient) -> None:
    """House order: validation 422s first, `resolve_llm_config`'s 409 last. With no key anywhere and
    no library, the user hears about the missing library (422), not the missing key (409)."""
    job_id = await _job(client)
    assert (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).status_code == 422
