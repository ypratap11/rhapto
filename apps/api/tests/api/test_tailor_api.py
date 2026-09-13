import asyncio
import json
from typing import Any

import httpx
import pytest
from helpers import demo_extract, demo_resume
from helpers_docx import build_fixture_docx

from rhapto.engine.compose import AnswerItem, ComposeOutput
from rhapto.engine.tune import ProposedEdit, TuneOutput
from rhapto.services.eventbus import InMemoryEventBus

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
    fake_llm.script(demo_extract(), good_output())
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


async def test_tailor_without_profile_marks_task_failed(client: httpx.AsyncClient) -> None:
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={})).json()
    assert task["status"] == "failed" and "no blocks" in task["error"]


@pytest.mark.usefixtures("imported_profile")
async def test_events_replays_finished_state_and_closes(
    client: httpx.AsyncClient, fake_llm
) -> None:  # type: ignore[no-untyped-def]
    fake_llm.script(demo_extract(), good_output())
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
    fake_llm.script(demo_extract(), good_output())
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
    fake_llm.script(demo_extract(), good_output())
    job_id = await _job(client)
    task = (await client.post(f"/api/v1/jobs/{job_id}/tailor", json={"mode": "blocks"})).json()
    assert task["status"] == "succeeded", task
    package = (await client.get(f"/api/v1/packages/{task['result_ref']}")).json()
    assert package["mode"] == "blocks" and package["edits"] == []
    assert package["source_document"] is None
