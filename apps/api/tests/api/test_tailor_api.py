import asyncio
import json
from typing import Any

import httpx
import pytest
from helpers import demo_extract, demo_resume

from rhapto.engine.compose import ComposeOutput
from rhapto.services.eventbus import InMemoryEventBus

JD = "ExampleCo seeks a Data Platform Program Manager to lead our Snowflake migration. " * 3


def good_output() -> dict[str, Any]:
    resume = demo_resume()
    return ComposeOutput(
        summary=resume.summary,
        sections=resume.sections,
        cover_note="Dear team, " + "word " * 130,
        change_log="Emphasised migration.",
        answers={"why_this_company": "Data."},
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
async def test_tailor_runs_inline_and_task_succeeds(client: httpx.AsyncClient, fake_llm) -> None:  # type: ignore[no-untyped-def]
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
