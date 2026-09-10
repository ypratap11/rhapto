from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from rhapto.db.models import Task


async def create_task(
    session: AsyncSession, user_id: uuid.UUID, type: str, progress: dict[str, Any]
) -> Task:
    task = Task(user_id=user_id, type=type, status="queued", progress_json=dict(progress))
    session.add(task)
    await session.flush()
    return task


async def get_task(session: AsyncSession, user_id: uuid.UUID, task_id: uuid.UUID) -> Task | None:
    result: Task | None = await session.scalar(
        select(Task).where(Task.user_id == user_id, Task.id == task_id)
    )
    return result


def mark_running(task: Task) -> None:
    task.status = "running"


def set_step(task: Task, step: str) -> None:
    task.progress_json = {**task.progress_json, "step": step}


def mark_succeeded(task: Task, result_ref: str) -> None:
    task.status = "succeeded"
    task.result_ref = result_ref
    task.finished_at = datetime.now(UTC)


def mark_failed(task: Task, error: str) -> None:
    task.status = "failed"
    task.error = error[:4000]
    task.finished_at = datetime.now(UTC)
